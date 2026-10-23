import os
import json
import sqlite3
import shutil
import secrets
import re
import uuid
from typing import Optional, List
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, UploadFile, File, Form, Header, HTTPException, Depends, Query
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from dotenv import set_key

from app.database import get_db, init_db, hash_password
from app.models import (
    DeckCreate, DeckPrivacyToggle, FlashcardCreate, FlashcardReview,
    QuizAttemptSubmit, SettingsUpdate, TextDeckGenerateRequest,
    ForumPostCreate, ForumCommentCreate, UserProfileUpdate,
    UserRegister, UserLogin, QuokkaFeedAction, AwardFruitRequest,
    DeckFolderUpdate, OralExamRequest
)
from app.services.sm2_service import calculate_sm2
from app.services.notes_parser import extract_text_from_file
from app.services.gemini_service import (
    get_api_key, generate_deck_content_from_notes,
    transcribe_audio_with_gemini, evaluate_oral_answer_with_gemini,
    generate_tts_for_question, analyze_filler_words_heuristics,
    generate_oral_exam_questions
)

app = FastAPI(title="Kua API", description="AI Study, Active Recall & Oral Examination Platform with Quokka Mascot")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Ensure static directories exist
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "css"), exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "js"), exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/")
def read_root():
    index_file = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_file):
        response = FileResponse(index_file)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return {"message": "Kua backend is running. index.html not yet initialized."}

# ==================== CONFIG & STATUS ====================

@app.get("/api/status")
def get_system_status():
    key = get_api_key()
    masked_key = f"{key[:4]}...{key[-4:]}" if key and len(key) > 8 else ("Configurada" if key else None)
    return {
        "status": "online",
        "has_gemini_api_key": bool(key),
        "masked_key": masked_key,
        "app_name": "Kua",
        "mascot": "Quokka",
        "primary_color": "#0083B0",
        "version": "2.1.0"
    }

@app.post("/api/settings")
def update_settings(payload: SettingsUpdate):
    key = payload.gemini_api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="La API Key no puede estar vacía.")
    
    os.environ["GEMINI_API_KEY"] = key
    env_path = os.path.join(os.path.dirname(BASE_DIR), ".env")
    try:
        set_key(env_path, "GEMINI_API_KEY", key)
    except Exception:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"GEMINI_API_KEY={key}\n")
            
    return {"message": "Configuración guardada exitosamente", "has_gemini_api_key": True}

# ==================== AUTHENTICATION & USERS ====================

def _issue_session(cursor, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    cursor.execute("INSERT INTO auth_sessions (token, user_id) VALUES (?, ?);", (token, user_id))
    return token

def _read_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[7:].strip() or None

@app.post("/api/auth/register")
def register_user(payload: UserRegister):
    conn = get_db()
    cursor = conn.cursor()
    
    clean_username = payload.username.strip().lower().replace("@", "")
    clean_email = payload.email.strip().lower()
    
    # Check if username or email exists
    cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?;", (clean_username, clean_email))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="El nombre de usuario o correo ya está registrado.")
    
    pwd_hash = hash_password(payload.password)
    cursor.execute("""
        INSERT INTO users (display_name, username, email, password_hash, university, career, semester, fruits_count, quokka_happiness)
        VALUES (?, ?, ?, ?, ?, ?, ?, 6, 85);
    """, (
        payload.display_name.strip(),
        clean_username,
        clean_email,
        pwd_hash,
        payload.university.strip() if payload.university else None,
        payload.career.strip() if payload.career else None,
        payload.semester.strip() if payload.semester else None
    ))
    user_id = cursor.lastrowid
    session_token = _issue_session(cursor, user_id)
    conn.commit()
    
    cursor.execute("SELECT id, display_name, username, email, university, career, semester, fruits_count, quokka_happiness, avatar_color, bio, profile_image, banner_color FROM users WHERE id = ?;", (user_id,))
    user = dict(cursor.fetchone())
    conn.close()
    
    return {"message": "Registro completado con éxito", "user": user, "session_token": session_token}

@app.post("/api/auth/login")
def login_user(payload: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    
    identifier = payload.username_or_email.strip().lower().replace("@", "")
    pwd_hash = hash_password(payload.password)
    
    cursor.execute("""
        SELECT id, display_name, username, email, password_hash, university, career, semester, fruits_count, quokka_happiness, avatar_color, bio, profile_image, banner_color
        FROM users 
        WHERE username = ? OR email = ?;
    """, (identifier, identifier))
    user_row = cursor.fetchone()
    if not user_row or user_row["password_hash"] != pwd_hash:
        conn.close()
        raise HTTPException(status_code=401, detail="Credenciales incorrectas. Verifica tu usuario/correo y contraseña.")
    
    user = dict(user_row)
    del user["password_hash"]
    session_token = _issue_session(cursor, user["id"])
    conn.commit()
    conn.close()
    return {"message": "Inicio de sesión exitoso", "user": user, "session_token": session_token}

@app.post("/api/auth/demo/{user_id}")
def login_demo_user(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, display_name, username, email, university, career, semester, fruits_count, quokka_happiness, avatar_color, bio, profile_image, banner_color FROM users WHERE id = ?;", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario demo no encontrado.")
    session_token = _issue_session(cursor, user_id)
    conn.commit()
    conn.close()
    return {"user": dict(user), "session_token": session_token}

@app.get("/api/auth/session")
def get_auth_session(authorization: Optional[str] = Header(None)):
    token = _read_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Sesión no válida.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.display_name, u.username, u.email, u.university, u.career,
               u.semester, u.fruits_count, u.quokka_happiness, u.avatar_color, u.bio,
               u.profile_image, u.banner_color
        FROM auth_sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token = ?;
    """, (token,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Sesión vencida o cerrada.")
    return {"user": dict(user)}

@app.post("/api/auth/logout")
def logout_user(authorization: Optional[str] = Header(None)):
    token = _read_bearer_token(authorization)
    if token:
        conn = get_db()
        conn.execute("DELETE FROM auth_sessions WHERE token = ?;", (token,))
        conn.commit()
        conn.close()
    return {"message": "Sesión cerrada correctamente."}

@app.get("/api/auth/me")
def get_current_user(user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, display_name, username, email, university, career, semester, fruits_count, quokka_happiness, avatar_color, bio, profile_image, banner_color, created_at FROM users WHERE id = ?;", (user_id,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        return {"id": 1, "display_name": "Estudiante Kua", "username": "estudiante_kua", "email": "demo@kua.edu", "university": "Universidad Nacional", "career": "Ingeniería", "fruits_count": 5, "quokka_happiness": 85}
    return dict(user)

@app.get("/api/users/{user_id}/public")
def get_user_public_profile(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, display_name, username, university, career, semester, bio, avatar_color, created_at,
               (SELECT COUNT(*) FROM decks WHERE user_id = u.id AND is_public = 1) as public_decks_count,
               (SELECT COUNT(*) FROM forum_posts WHERE user_id = u.id) as forum_posts_count
        FROM users u
        WHERE u.id = ?;
    """, (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
    profile = dict(user)
    
    # Public decks by this user
    cursor.execute("""
        SELECT id, name, subject, difficulty, color, created_at,
               (SELECT COUNT(*) FROM flashcards WHERE deck_id = d.id) as flashcards_count,
               (SELECT COUNT(*) FROM quiz_questions WHERE deck_id = d.id) as quiz_count,
               (SELECT COUNT(*) FROM oral_questions WHERE deck_id = d.id) as oral_count
        FROM decks d
        WHERE user_id = ? AND is_public = 1
        ORDER BY created_at DESC;
    """, (user_id,))
    profile["public_decks"] = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return profile

@app.post("/api/user/profile")
def update_user_profile(payload: UserProfileUpdate, user_id: int = Query(1)):
    if payload.banner_color and not re.fullmatch(r"#[0-9A-Fa-f]{6}", payload.banner_color):
        raise HTTPException(status_code=400, detail="El color del banner debe ser un código hexadecimal válido.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET display_name = ?, email = COALESCE(?, email), bio = ?,
            university = COALESCE(?, university), career = COALESCE(?, career),
            semester = COALESCE(?, semester), banner_color = COALESCE(?, banner_color)
        WHERE id = ?;
    """, (payload.display_name, payload.email, payload.bio, payload.university,
          payload.career, payload.semester, payload.banner_color, user_id))
    conn.commit()
    cursor.execute("SELECT id, display_name, email, bio, university, career, semester, profile_image, banner_color FROM users WHERE id = ?;", (user_id,))
    user_row = cursor.fetchone()
    conn.close()
    if not user_row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    user = dict(user_row)
    return {"message": "Perfil actualizado exitosamente", "user": user}

@app.post("/api/users/{user_id}/avatar")
async def upload_user_avatar(user_id: int, file: UploadFile = File(...), authorization: Optional[str] = Header(None)):
    token = _read_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Inicia sesión para cambiar tu foto de perfil.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM auth_sessions WHERE token = ?;", (token,))
    session = cursor.fetchone()
    conn.close()
    if not session or session["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="La sesión no corresponde a esta cuenta.")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen.")
    contents = await file.read(5 * 1024 * 1024 + 1)
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="La imagen no puede superar 5 MB.")
    extension_by_type = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
    extension = extension_by_type.get(file.content_type.lower())
    if not extension:
        raise HTTPException(status_code=400, detail="Formato de imagen no compatible. Usa JPG, PNG, WEBP o GIF.")

    upload_dir = os.path.join(STATIC_DIR, "uploads", "avatars")
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    filepath = os.path.join(upload_dir, filename)
    with open(filepath, "wb") as image_file:
        image_file.write(contents)
    image_url = f"/static/uploads/avatars/{filename}"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET profile_image = ? WHERE id = ?;", (image_url, user_id))
    if cursor.rowcount == 0:
        conn.close()
        os.remove(filepath)
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    conn.commit()
    conn.close()
    return {"profile_image": image_url}

# ==================== QUOKKA PET & GAMIFICATION ====================

@app.get("/api/quokka/status")
def get_quokka_status(user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT fruits_count, quokka_happiness, display_name FROM users WHERE id = ?;", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    fruits = row["fruits_count"] if row and row["fruits_count"] is not None else 5
    happiness = row["quokka_happiness"] if row and row["quokka_happiness"] is not None else 85
    
    if happiness >= 90:
        mood = "¡Eufórico y lleno de energía! 🎉"
    elif happiness >= 70:
        mood = "Muy alegre y listo para estudiar 🌿"
    elif happiness >= 40:
        mood = "Un poco pensativo, le vendría bien una fruta 🍎"
    else:
        mood = "Hambriento, ¡haz una sesión de estudio para alimentarlo! 🍓"
        
    return {
        "fruits_count": fruits,
        "quokka_happiness": happiness,
        "mood": mood,
        "mascot_name": "Koko el Quokka"
    }

@app.post("/api/quokka/feed")
def feed_quokka(payload: QuokkaFeedAction, user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT fruits_count, quokka_happiness FROM users WHERE id = ?;", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
    fruits = row["fruits_count"] or 0
    happiness = row["quokka_happiness"] or 70
    
    if fruits <= 0:
        conn.close()
        raise HTTPException(status_code=400, detail="¡No tienes frutas! Completa una sesión de flashcards, quiz o examen oral para ganar frutas.")
        
    new_fruits = fruits - 1
    new_happiness = min(100, happiness + 10)
    
    cursor.execute("""
        UPDATE users 
        SET fruits_count = ?, quokka_happiness = ?
        WHERE id = ?;
    """, (new_fruits, new_happiness, user_id))
    conn.commit()
    conn.close()
    
    return {
        "message": "¡Ñam ñam! A tu Quokka le encantó la fruta y ahora está súper feliz 🍓✨",
        "fruits_count": new_fruits,
        "quokka_happiness": new_happiness,
        "is_happy": True
    }

@app.post("/api/quokka/award-fruit")
def award_fruit_to_user(payload: AwardFruitRequest, user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    
    # Session rewards: oral gives 2 fruits, others give 1
    fruits_to_add = 2 if payload.session_type == "oral" else 1
    happiness_to_add = 10 if payload.session_type == "oral" else 5
    
    cursor.execute("""
        UPDATE users
        SET fruits_count = COALESCE(fruits_count, 0) + ?,
            quokka_happiness = MIN(100, COALESCE(quokka_happiness, 75) + ?)
        WHERE id = ?;
    """, (fruits_to_add, happiness_to_add, user_id))
    
    cursor.execute("SELECT fruits_count, quokka_happiness FROM users WHERE id = ?;", (user_id,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()
    
    return {
        "message": f"¡Sesión de {payload.session_type} completada! Ganaste {fruits_to_add} fruta(s) para tu Quokka 🍎",
        "fruits_awarded": fruits_to_add,
        "fruits_count": row["fruits_count"],
        "quokka_happiness": row["quokka_happiness"]
    }

# ==================== DECKS & PRIVACY ====================

@app.get("/api/folders")
def list_folders(user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.id, f.user_id, f.name, f.color, f.image_path, f.created_at,
               COUNT(d.id) AS deck_count
        FROM folders f
        LEFT JOIN decks d ON d.folder_id = f.id AND COALESCE(d.is_exam_only, 0) = 0
        WHERE f.user_id = ?
        GROUP BY f.id
        ORDER BY f.name COLLATE NOCASE ASC;
    """, (user_id,))
    folders = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return folders

def _folder_image_path(image: Optional[UploadFile]) -> Optional[str]:
    if image is None or not image.filename:
        return None
    extensions = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
    extension = extensions.get(image.content_type or "")
    if not extension:
        raise HTTPException(status_code=400, detail="La foto debe ser JPG, PNG, WEBP o GIF.")
    image_bytes = image.file.read(5 * 1024 * 1024 + 1)
    if len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="La foto no puede superar 5 MB.")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="El archivo de imagen está vacío.")
    relative_dir = os.path.join("uploads", "folders")
    absolute_dir = os.path.join(STATIC_DIR, relative_dir)
    os.makedirs(absolute_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    with open(os.path.join(absolute_dir, filename), "wb") as output:
        output.write(image_bytes)
    return f"/static/{relative_dir.replace(os.sep, '/')}/{filename}"

def _validate_folder_color(color: str) -> str:
    normalized = color.strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", normalized):
        raise HTTPException(status_code=400, detail="El color debe ser un valor hexadecimal de seis caracteres.")
    return normalized

def _validate_folder_owner(cursor, folder_id: Optional[int], user_id: int) -> None:
    if folder_id is None:
        return
    cursor.execute("SELECT id FROM folders WHERE id = ? AND user_id = ?;", (folder_id, user_id))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Carpeta no encontrada para este usuario.")

@app.post("/api/folders")
def create_folder(
    name: str = Form(...),
    color: str = Form("#0083B0"),
    image: Optional[UploadFile] = File(None),
    user_id: int = Query(1),
):
    folder_name = name.strip()
    if not folder_name:
        raise HTTPException(status_code=400, detail="El nombre de la carpeta no puede estar vacío.")
    if len(folder_name) > 80:
        raise HTTPException(status_code=400, detail="El nombre de la carpeta no puede superar 80 caracteres.")
    folder_color = _validate_folder_color(color)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE id = ?;", (user_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    try:
        image_path = _folder_image_path(image)
        cursor.execute("INSERT INTO folders (user_id, name, color, image_path) VALUES (?, ?, ?, ?);", (user_id, folder_name, folder_color, image_path))
        folder_id = cursor.lastrowid
        conn.commit()
    except HTTPException:
        conn.close()
        raise
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="Ya existe una carpeta con ese nombre.")

    cursor.execute("SELECT id, user_id, name, color, image_path, created_at FROM folders WHERE id = ?;", (folder_id,))
    folder = dict(cursor.fetchone())
    folder["deck_count"] = 0
    conn.close()
    return folder

@app.patch("/api/folders/{folder_id}")
def update_folder(
    folder_id: int,
    name: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    user_id: int = Query(1),
):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM folders WHERE id = ? AND user_id = ?;", (folder_id, user_id))
    current = cursor.fetchone()
    if not current:
        conn.close()
        raise HTTPException(status_code=404, detail="Carpeta no encontrada.")

    folder_name = (name.strip() if name is not None else current["name"])
    if not folder_name:
        conn.close()
        raise HTTPException(status_code=400, detail="El nombre de la carpeta no puede estar vacío.")
    if len(folder_name) > 80:
        conn.close()
        raise HTTPException(status_code=400, detail="El nombre de la carpeta no puede superar 80 caracteres.")
    try:
        folder_color = _validate_folder_color(color) if color is not None else current["color"]
    except HTTPException:
        conn.close()
        raise
    try:
        image_path = _folder_image_path(image) if image is not None else current["image_path"]
        cursor.execute("UPDATE folders SET name = ?, color = ?, image_path = ? WHERE id = ?;", (folder_name, folder_color, image_path, folder_id))
        conn.commit()
    except HTTPException:
        conn.close()
        raise
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="Ya existe una carpeta con ese nombre.")
    cursor.execute("""
        SELECT f.id, f.user_id, f.name, f.color, f.image_path, f.created_at,
               (SELECT COUNT(*) FROM decks d WHERE d.folder_id = f.id AND COALESCE(d.is_exam_only, 0) = 0) AS deck_count
        FROM folders f WHERE f.id = ?;
    """, (folder_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated

@app.patch("/api/decks/{deck_id}/folder")
def move_deck_to_folder(
    deck_id: int,
    payload: DeckFolderUpdate,
    user_id: int = Query(1),
):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM decks WHERE id = ? AND user_id = ? AND COALESCE(is_exam_only, 0) = 0;",
        (deck_id, user_id),
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Mazo no encontrado.")

    if payload.folder_id is not None:
        cursor.execute("SELECT id FROM folders WHERE id = ? AND user_id = ?;", (payload.folder_id, user_id))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Carpeta no encontrada para este usuario.")

    cursor.execute("UPDATE decks SET folder_id = ? WHERE id = ?;", (payload.folder_id, deck_id))
    conn.commit()
    conn.close()
    return {"deck_id": deck_id, "folder_id": payload.folder_id, "message": "Mazo movido correctamente."}

@app.post("/api/folders/{folder_id}/oral-exam")
def create_folder_oral_exam(folder_id: int, payload: OralExamRequest, user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM folders WHERE id = ? AND user_id = ?;", (folder_id, user_id))
    folder = cursor.fetchone()
    if not folder:
        conn.close()
        raise HTTPException(status_code=404, detail="Carpeta no encontrada.")

    cursor.execute("""
        SELECT id, name, notes_text
        FROM decks
        WHERE folder_id = ? AND user_id = ? AND COALESCE(is_exam_only, 0) = 0
        ORDER BY id ASC;
    """, (folder_id, user_id))
    decks = [dict(row) for row in cursor.fetchall()]
    if not decks:
        conn.close()
        raise HTTPException(status_code=400, detail="Agrega al menos un mazo a la carpeta para generar un examen.")

    source_parts = []
    for deck in decks:
        cursor.execute("SELECT question_text, concept, key_points_json FROM oral_questions WHERE deck_id = ? ORDER BY id ASC;", (deck["id"],))
        oral_questions = [dict(row) for row in cursor.fetchall()]
        source_parts.append(f"MAZO: {deck['name']}\nAPUNTES:\n{deck.get('notes_text') or '(sin apuntes guardados)'}")
        if oral_questions:
            formatted_questions = []
            for question in oral_questions:
                key_points = json.loads(question["key_points_json"]) if question["key_points_json"] else []
                formatted_questions.append(
                    f"- {question['question_text']} | Concepto: {question['concept'] or ''} | Puntos clave: {', '.join(key_points)}"
                )
            source_parts.append("PREGUNTAS ORALES EXISTENTES:\n" + "\n".join(formatted_questions))

    source_material = "\n\n".join(source_parts)
    question_count = payload.question_count
    conn.close()

    try:
        oral_questions = generate_oral_exam_questions(
            folder["name"], source_material, question_count=question_count,
            difficulty=payload.difficulty
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini no pudo generar el examen combinado: {exc}")

    conn = get_db()
    cursor = conn.cursor()
    exam_name = f"Examen Oral de la Carpeta: {folder['name']}"
    cursor.execute("""
        INSERT INTO decks (user_id, name, source_filename, notes_text, subject, difficulty, is_public, color, is_exam_only)
        VALUES (?, ?, ?, ?, ?, ?, 0, '#0083B0', 1);
    """, (user_id, exam_name, f"folder_exam_{folder_id}", source_material, folder["name"], payload.difficulty))
    exam_deck_id = cursor.lastrowid

    for question in oral_questions:
        cursor.execute("""
            INSERT INTO oral_questions (deck_id, question_text, concept, key_points_json)
            VALUES (?, ?, ?, ?);
        """, (
            exam_deck_id,
            question["question_text"],
            question.get("concept", ""),
            json.dumps(question.get("key_points", [])),
        ))

    conn.commit()
    conn.close()
    return {
        "deck": {"id": exam_deck_id, "name": exam_name, "folder_id": folder_id},
        "question_count": len(oral_questions),
    }

@app.post("/api/decks/{deck_id}/oral-exam")
def create_deck_oral_exam(deck_id: int, payload: OralExamRequest, user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, subject, notes_text FROM decks WHERE id = ? AND user_id = ?;", (deck_id, user_id))
    deck = cursor.fetchone()
    if not deck:
        conn.close()
        raise HTTPException(status_code=404, detail="Mazo no encontrado.")
    cursor.execute("SELECT question_text, concept, key_points_json FROM oral_questions WHERE deck_id = ? ORDER BY id ASC;", (deck_id,))
    existing_questions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    source_parts = [f"MAZO: {deck['name']}\nAPUNTES:\n{deck['notes_text'] or '(sin apuntes guardados)'}"]
    if existing_questions:
        source_parts.append("PREGUNTAS ORALES DE REFERENCIA:\n" + "\n".join(
            f"- {q['question_text']} | Concepto: {q['concept'] or ''} | Puntos clave: {', '.join(json.loads(q['key_points_json']) if q['key_points_json'] else [])}"
            for q in existing_questions
        ))
    source_material = "\n\n".join(source_parts)
    if not deck["notes_text"] and not existing_questions:
        raise HTTPException(status_code=400, detail="Este mazo no contiene material para generar un examen oral.")

    try:
        oral_questions = generate_oral_exam_questions(
            deck["name"], source_material,
            question_count=payload.question_count,
            difficulty=payload.difficulty,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini no pudo generar el examen oral: {exc}")

    exam_name = f"Examen Oral: {deck['name']}"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO decks (user_id, name, source_filename, notes_text, subject, difficulty, is_public, color, is_exam_only)
        VALUES (?, ?, ?, ?, ?, ?, 0, '#0083B0', 1);
    """, (user_id, exam_name, f"deck_exam_{deck_id}", source_material, deck["subject"], payload.difficulty))
    exam_deck_id = cursor.lastrowid
    for question in oral_questions:
        cursor.execute("""
            INSERT INTO oral_questions (deck_id, question_text, concept, key_points_json)
            VALUES (?, ?, ?, ?);
        """, (exam_deck_id, question["question_text"], question.get("concept", ""), json.dumps(question.get("key_points", []))))
    conn.commit()
    conn.close()
    return {"deck": {"id": exam_deck_id, "name": exam_name}, "question_count": len(oral_questions)}

@app.get("/api/decks")
def list_decks(user_id: Optional[int] = None):
    conn = get_db()
    cursor = conn.cursor()
    
    query = """
        SELECT d.*, u.username as owner_username, u.display_name as owner_name,
            (SELECT COUNT(*) FROM flashcards WHERE deck_id = d.id) as flashcards_count,
            (SELECT COUNT(*) FROM quiz_questions WHERE deck_id = d.id) as quiz_count,
            (SELECT COUNT(*) FROM oral_questions WHERE deck_id = d.id) as oral_count,
            (SELECT COUNT(*) FROM flashcards WHERE deck_id = d.id AND repetitions >= 2) as mastered_cards_count,
            (SELECT AVG(overall_score) FROM oral_sessions WHERE deck_id = d.id AND completed_at IS NOT NULL) as avg_oral_score
        FROM decks d
        LEFT JOIN users u ON d.user_id = u.id
        WHERE COALESCE(d.is_exam_only, 0) = 0
          AND NOT EXISTS (
              SELECT 1 FROM generation_jobs j
              WHERE j.deck_id = d.id AND j.status IN ('queued', 'running')
          )
    """
    params = []
    if user_id:
        query += " AND d.user_id = ? "
        params.append(user_id)
        
    query += " ORDER BY d.created_at DESC;"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    decks = []
    for r in rows:
        d = dict(r)
        d["is_public"] = bool(d.get("is_public", 0))
        d["avg_oral_score"] = round(d["avg_oral_score"], 1) if d["avg_oral_score"] else None
        decks.append(d)
    conn.close()
    return decks

@app.get("/api/decks/{deck_id}")
def get_deck_detail(deck_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.*, u.username as owner_username, u.display_name as owner_name 
        FROM decks d 
        LEFT JOIN users u ON d.user_id = u.id
        WHERE d.id = ?;
    """, (deck_id,))
    deck = cursor.fetchone()
    if not deck:
        conn.close()
        raise HTTPException(status_code=404, detail="Mazo no encontrado")
        
    deck_data = dict(deck)
    deck_data["is_public"] = bool(deck_data.get("is_public", 0))
    
    # Flashcards
    cursor.execute("SELECT * FROM flashcards WHERE deck_id = ? ORDER BY id ASC;", (deck_id,))
    deck_data["flashcards"] = [dict(c) for c in cursor.fetchall()]
    
    # Quiz questions
    cursor.execute("SELECT * FROM quiz_questions WHERE deck_id = ? ORDER BY id ASC;", (deck_id,))
    quizzes = []
    for q in cursor.fetchall():
        qd = dict(q)
        qd["options"] = json.loads(qd["options_json"])
        quizzes.append(qd)
    deck_data["quiz_questions"] = quizzes
    
    # Oral questions
    cursor.execute("SELECT * FROM oral_questions WHERE deck_id = ? ORDER BY id ASC;", (deck_id,))
    orals = []
    for o in cursor.fetchall():
        od = dict(o)
        od["key_points"] = json.loads(od["key_points_json"]) if od["key_points_json"] else []
        orals.append(od)
    deck_data["oral_questions"] = orals
    
    conn.close()
    return deck_data

@app.delete("/api/decks/{deck_id}")
def delete_deck(deck_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM decks WHERE id = ?;", (deck_id,))
    cursor.execute("DELETE FROM forum_posts WHERE deck_id = ?;", (deck_id,))
    conn.commit()
    conn.close()
    return {"message": "Mazo eliminado exitosamente"}

@app.post("/api/decks/{deck_id}/privacy")
def toggle_deck_privacy(deck_id: int, payload: DeckPrivacyToggle, user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM decks WHERE id = ?;", (deck_id,))
    deck = cursor.fetchone()
    if not deck:
        conn.close()
        raise HTTPException(status_code=404, detail="Mazo no encontrado")
        
    is_pub_val = 1 if payload.is_public else 0
    cursor.execute("UPDATE decks SET is_public = ? WHERE id = ?;", (is_pub_val, deck_id))
    
    if payload.is_public:
        # Check if already in forum_posts
        cursor.execute("SELECT id FROM forum_posts WHERE deck_id = ?;", (deck_id,))
        existing_post = cursor.fetchone()
        if not existing_post:
            deck_d = dict(deck)
            cursor.execute("""
                INSERT INTO forum_posts (user_id, deck_id, title, description, subject, notes_text, likes_count)
                VALUES (?, ?, ?, ?, ?, ?, 0);
            """, (
                deck_d["user_id"] or user_id,
                deck_id,
                deck_d["name"],
                f"Mazo de estudio sobre {deck_d.get('subject') or deck_d['name']}. Dificultad: {deck_d.get('difficulty') or 'Medio'}",
                deck_d.get("subject") or "General",
                deck_d.get("notes_text") or "Apuntes del mazo"
            ))
    else:
        # Hide from forum feed by deleting post or disassociating
        cursor.execute("DELETE FROM forum_posts WHERE deck_id = ?;", (deck_id,))
        
    conn.commit()
    conn.close()
    
    status_msg = "Mazo publicado en el Foro público 🌐" if payload.is_public else "Mazo marcado como privado 🔒 (oculto del Foro)"
    return {
        "deck_id": deck_id,
        "is_public": payload.is_public,
        "message": status_msg
    }

@app.post("/api/decks/{deck_id}/clone")
def clone_deck_to_my_library(deck_id: int, user_id: int = Query(1)):
    """
    Creates an independent copy of another user's public deck in the current user's library.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM decks WHERE id = ?;", (deck_id,))
    source_deck = cursor.fetchone()
    if not source_deck:
        conn.close()
        raise HTTPException(status_code=404, detail="Mazo no encontrado para clonar")
        
    s = dict(source_deck)
    clone_name = f"{s['name']} (Copia)"
    
    # 1. Insert new deck with user_id, is_public=0
    cursor.execute("""
        INSERT INTO decks (user_id, name, source_filename, notes_text, subject, difficulty, is_public, color, cloned_from_id)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?);
    """, (
        user_id,
        clone_name,
        s.get("source_filename"),
        s.get("notes_text"),
        s.get("subject") or "General",
        s.get("difficulty") or "Medio",
        s.get("color") or "#0083B0",
        deck_id
    ))
    new_deck_id = cursor.lastrowid
    
    now_iso = datetime.now().isoformat()
    # 2. Copy flashcards
    cursor.execute("SELECT question, answer FROM flashcards WHERE deck_id = ?;", (deck_id,))
    for fc in cursor.fetchall():
        cursor.execute("""
            INSERT INTO flashcards (deck_id, question, answer, easiness_factor, interval_days, repetitions, next_review_at, last_reviewed_at)
            VALUES (?, ?, ?, 2.5, 0, 0, ?, ?);
        """, (new_deck_id, fc["question"], fc["answer"], now_iso, now_iso))
        
    # 3. Copy quiz questions
    cursor.execute("SELECT question, options_json, correct_index FROM quiz_questions WHERE deck_id = ?;", (deck_id,))
    for qq in cursor.fetchall():
        cursor.execute("""
            INSERT INTO quiz_questions (deck_id, question, options_json, correct_index)
            VALUES (?, ?, ?, ?);
        """, (new_deck_id, qq["question"], qq["options_json"], qq["correct_index"]))
        
    # 4. Copy oral questions
    cursor.execute("SELECT question_text, concept, key_points_json FROM oral_questions WHERE deck_id = ?;", (deck_id,))
    for oq in cursor.fetchall():
        cursor.execute("""
            INSERT INTO oral_questions (deck_id, question_text, concept, key_points_json)
            VALUES (?, ?, ?, ?);
        """, (new_deck_id, oq["question_text"], oq["concept"], oq["key_points_json"]))
        
    conn.commit()
    conn.close()
    
    return {
        "message": f"¡Mazo '{s['name']}' guardado como copia en tu biblioteca personal!",
        "new_deck_id": new_deck_id,
        "name": clone_name
    }

# ==================== GENERATION WITH CUSTOMIZATION ====================

def _run_deck_generation_job(
    job_id: str, deck_id: int, user_id: int, notes_for_model: str,
    custom_name: Optional[str], subject: Optional[str], difficulty: str,
    flashcards_count: int, quiz_count: int, oral_count: int,
    is_public: bool, source_filename: str,
    previous_flashcard_questions: List[str], previous_quiz_questions: List[str],
) -> None:
    conn = get_db()
    conn.execute("UPDATE generation_jobs SET status = 'running', message = 'Completando el mazo...', updated_at = CURRENT_TIMESTAMP WHERE job_id = ?;", (job_id,))
    conn.commit()
    conn.close()
    try:
        generated = generate_deck_content_from_notes(
            notes_for_model, custom_name=custom_name, subject=subject,
            difficulty=difficulty, flashcards_count=flashcards_count,
            quiz_count=quiz_count, oral_count=oral_count,
            exclude_flashcard_questions=previous_flashcard_questions,
            exclude_quiz_questions=previous_quiz_questions,
        )
        conn = get_db()
        cursor = conn.cursor()
        final_name = generated.get("name") or custom_name or "Mazo de Estudio Kua"
        final_subject = generated.get("subject") or subject or "General"
        cursor.execute("UPDATE decks SET name = ?, subject = ?, difficulty = ?, color = ? WHERE id = ?;", (
            final_name, final_subject, difficulty, generated.get("color") or "#0083B0", deck_id
        ))
        now_iso = datetime.now().isoformat()
        for card in generated.get("flashcards", [])[:flashcards_count]:
            cursor.execute("""
                INSERT INTO flashcards (deck_id, question, answer, easiness_factor, interval_days, repetitions, next_review_at, last_reviewed_at)
                VALUES (?, ?, ?, 2.5, 0, 0, ?, ?);
            """, (deck_id, card["question"], card["answer"], now_iso, now_iso))
        for question in generated.get("quiz_questions", [])[:quiz_count]:
            cursor.execute("""
                INSERT INTO quiz_questions (deck_id, question, options_json, correct_index)
                VALUES (?, ?, ?, ?);
            """, (deck_id, question["question"], json.dumps(question["options"]), question.get("correct_index", 0)))
        for question in generated.get("oral_questions", [])[:oral_count]:
            cursor.execute("""
                INSERT INTO oral_questions (deck_id, question_text, concept, key_points_json)
                VALUES (?, ?, ?, ?);
            """, (deck_id, question["question_text"], question.get("concept", ""), json.dumps(question.get("key_points", []))))
        if is_public:
            cursor.execute("""
                INSERT INTO forum_posts (user_id, deck_id, title, description, subject, source_filename, notes_text, likes_count)
                SELECT ?, ?, ?, ?, ?, ?, notes_text, 0 FROM decks WHERE id = ?;
            """, (user_id, deck_id, final_name, f"Apuntes de {final_subject}. Dificultad: {difficulty}", final_subject, source_filename, deck_id))
        cursor.execute("UPDATE generation_jobs SET status = 'completed', message = 'Mazo listo.', updated_at = CURRENT_TIMESTAMP WHERE job_id = ?;", (job_id,))
        conn.commit()
        conn.close()
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE generation_jobs SET status = 'failed', message = 'El mazo conserva el contenido inicial; no se pudo completar el resto.', error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?;
        """, (str(exc)[:1000], job_id))
        conn.commit()
        conn.close()
        print(f"Error generating deck job {job_id}: {exc}")

def _queue_deck_generation(
    background_tasks: BackgroundTasks, user_id: int, source_filename: str,
    full_notes: str, notes_for_model: str, custom_name: Optional[str],
    subject: Optional[str], difficulty: str, flashcards_count: int,
    quiz_count: int, oral_count: int, is_public: bool,
    folder_id: Optional[int],
) -> dict:
    job_id = uuid.uuid4().hex
    initial_name = custom_name or "Mazo en generación"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO decks (user_id, name, source_filename, notes_text, subject, difficulty, is_public, color, folder_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, '#0083B0', ?);
    """, (user_id, initial_name, source_filename, full_notes, subject or "General", difficulty, int(is_public), folder_id))
    deck_id = cursor.lastrowid
    cursor.execute("""
        INSERT INTO generation_jobs (job_id, user_id, deck_id, status, message)
        VALUES (?, ?, ?, 'queued', 'Generando mazo...');
    """, (job_id, user_id, deck_id))
    conn.commit()
    conn.close()
    try:
        initial_flashcards = min(flashcards_count, 5)
        initial_quizzes = min(quiz_count, 5)
        initial_content = generate_deck_content_from_notes(
            notes_for_model, custom_name=custom_name, subject=subject,
            difficulty=difficulty, flashcards_count=initial_flashcards,
            quiz_count=initial_quizzes, oral_count=0,
        )

        conn = get_db()
        cursor = conn.cursor()
        now_iso = datetime.now().isoformat()
        final_name = initial_content.get("name") or custom_name or "Mazo de Estudio Kua"
        final_subject = initial_content.get("subject") or subject or "General"
        saved_flashcards = initial_content.get("flashcards", [])[:initial_flashcards]
        saved_quizzes = initial_content.get("quiz_questions", [])[:initial_quizzes]
        cursor.execute("UPDATE decks SET name = ?, subject = ?, color = ? WHERE id = ?;", (
            final_name, final_subject, initial_content.get("color") or "#0083B0", deck_id
        ))
        for card in saved_flashcards:
            cursor.execute("""
                INSERT INTO flashcards (deck_id, question, answer, easiness_factor, interval_days, repetitions, next_review_at, last_reviewed_at)
                VALUES (?, ?, ?, 2.5, 0, 0, ?, ?);
            """, (deck_id, card["question"], card["answer"], now_iso, now_iso))
        for question in saved_quizzes:
            cursor.execute("""
                INSERT INTO quiz_questions (deck_id, question, options_json, correct_index)
                VALUES (?, ?, ?, ?);
            """, (deck_id, question["question"], json.dumps(question["options"]), question.get("correct_index", 0)))
        remaining_flashcards = max(0, flashcards_count - len(saved_flashcards))
        remaining_quizzes = max(0, quiz_count - len(saved_quizzes))
        conn.execute("""
            UPDATE generation_jobs SET status = 'running', message = 'Primeras tarjetas listas; completando el mazo...', updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?;
        """, (job_id,))
        conn.commit()
        conn.close()
    except Exception as exc:
        conn = get_db()
        conn.execute("DELETE FROM decks WHERE id = ?;", (deck_id,))
        conn.execute("DELETE FROM generation_jobs WHERE job_id = ?;", (job_id,))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=502, detail=f"No se pudo generar el contenido inicial: {str(exc)[:300]}")

    background_tasks.add_task(
        _run_deck_generation_job, job_id, deck_id, user_id, notes_for_model,
        custom_name, subject, difficulty, remaining_flashcards, remaining_quizzes,
        oral_count, is_public, source_filename,
        [card.get("question", "") for card in saved_flashcards],
        [question.get("question", "") for question in saved_quizzes],
    )
    return {
        "job_id": job_id, "deck_id": deck_id, "name": final_name,
        "status": "running", "message": "Primeras tarjetas listas; completando el mazo..."
    }

@app.get("/api/generation-jobs/{job_id}")
def get_generation_job(job_id: str, user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT j.job_id, j.deck_id, j.status, j.message, j.error, d.name
        FROM generation_jobs j LEFT JOIN decks d ON d.id = j.deck_id
        WHERE j.job_id = ? AND j.user_id = ?;
    """, (job_id, user_id))
    job = cursor.fetchone()
    conn.close()
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo de generación no encontrado.")
    return dict(job)

@app.post("/api/decks/generate-from-file")
async def generate_deck_from_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    custom_name: Optional[str] = Form(None),
    subject: Optional[str] = Form("General"),
    difficulty: Optional[str] = Form("Medio"),
    flashcards_count: Optional[int] = Form(8),
    quiz_count: Optional[int] = Form(4),
    oral_count: Optional[int] = Form(3),
    is_public: Optional[bool] = Form(False),
    folder_id: Optional[int] = Form(None),
    user_id: Optional[int] = Form(1),
):
    try:
        content_bytes = await file.read()
        extracted_text = extract_text_from_file(file.filename, content_bytes)
        if not extracted_text or len(extracted_text.strip()) < 30:
            raise HTTPException(status_code=400, detail="El archivo contiene muy poco texto para generar contenido de estudio.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error leyendo archivo: {exc}")

    owner_id = user_id or 1
    folder_conn = get_db()
    try:
        _validate_folder_owner(folder_conn.cursor(), folder_id, owner_id)
    finally:
        folder_conn.close()

    filename = file.filename or "apuntes.pdf"
    notes_for_model = extracted_text[:4000] if filename.lower().endswith(".pdf") else extracted_text
    return await run_in_threadpool(
        _queue_deck_generation,
        background_tasks, owner_id, filename, extracted_text, notes_for_model,
        custom_name, subject, difficulty or "Medio",
        max(5, min(flashcards_count or 8, 30)),
        max(3, min(quiz_count or 4, 15)), max(2, min(oral_count or 3, 8)),
        bool(is_public), folder_id,
    )

@app.post("/api/decks/generate-from-text")
def generate_deck_from_text(background_tasks: BackgroundTasks, payload: TextDeckGenerateRequest, user_id: int = Query(1)):
    text = payload.notes_text.strip()
    if len(text) < 30:
        raise HTTPException(status_code=400, detail="El texto es muy corto para generar material de estudio.")

    folder_conn = get_db()
    try:
        _validate_folder_owner(folder_conn.cursor(), payload.folder_id, user_id)
    finally:
        folder_conn.close()

    return _queue_deck_generation(
        background_tasks, user_id, "texto_manual.txt", text, text,
        payload.name, payload.subject, payload.difficulty or "Medio",
        max(5, min(payload.flashcards_count or 8, 30)),
        max(3, min(payload.quiz_count or 4, 15)),
        max(2, min(payload.oral_count or 3, 8)),
        bool(payload.is_public), payload.folder_id,
    )

# ==================== FLASHCARDS (SM-2) ====================

@app.get("/api/decks/{deck_id}/flashcards")
def get_deck_flashcards(deck_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM flashcards 
        WHERE deck_id = ? 
        ORDER BY CASE WHEN next_review_at <= datetime('now') THEN 0 ELSE 1 END, id ASC;
    """, (deck_id,))
    cards = [dict(c) for c in cursor.fetchall()]
    conn.close()
    return cards

@app.post("/api/flashcards/{card_id}/review")
def review_flashcard(card_id: int, payload: FlashcardReview):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM flashcards WHERE id = ?;", (card_id,))
    card = cursor.fetchone()
    if not card:
        conn.close()
        raise HTTPException(status_code=404, detail="Flashcard no encontrada")
        
    card_dict = dict(card)
    new_rep, new_ef, new_interval, next_review_iso = calculate_sm2(
        grade=payload.grade,
        repetitions=card_dict["repetitions"],
        easiness_factor=card_dict["easiness_factor"],
        interval_days=card_dict["interval_days"]
    )
    
    cursor.execute("""
        UPDATE flashcards
        SET repetitions = ?,
            easiness_factor = ?,
            interval_days = ?,
            next_review_at = ?,
            last_reviewed_at = datetime('now')
        WHERE id = ?;
    """, (new_rep, new_ef, new_interval, next_review_iso, card_id))
    
    conn.commit()
    conn.close()
    
    return {
        "id": card_id,
        "grade": payload.grade,
        "repetitions": new_rep,
        "easiness_factor": new_ef,
        "interval_days": new_interval,
        "next_review_at": next_review_iso
    }

# ==================== QUIZ ====================

@app.get("/api/decks/{deck_id}/quiz")
def get_deck_quiz(deck_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM quiz_questions WHERE deck_id = ? ORDER BY id ASC;", (deck_id,))
    quizzes = []
    for q in cursor.fetchall():
        qd = dict(q)
        qd["options"] = json.loads(qd["options_json"])
        quizzes.append(qd)
    conn.close()
    return quizzes

@app.post("/api/quiz/attempt")
def record_quiz_attempt(payload: QuizAttemptSubmit, user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO quiz_attempts (deck_id, user_id, score, total_questions)
        VALUES (?, ?, ?, ?);
    """, (payload.deck_id, user_id, payload.score, payload.total_questions))
    conn.commit()
    conn.close()
    return {"message": "Intento de quiz guardado"}

# ==================== ORAL EXAM ====================

@app.get("/api/decks/{deck_id}/oral-questions")
def get_deck_oral_questions(deck_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM oral_questions WHERE deck_id = ? ORDER BY id ASC;", (deck_id,))
    questions = []
    for o in cursor.fetchall():
        od = dict(o)
        od["key_points"] = json.loads(od["key_points_json"]) if od["key_points_json"] else []
        questions.append(od)
    conn.close()
    return questions

@app.post("/api/oral/tts")
def tts_oral_question(payload: dict):
    text = payload.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Texto vacío")
        
    audio_bytes = generate_tts_for_question(text)
    if not audio_bytes:
        return JSONResponse(status_code=204, content={"message": "TTS no disponible"})
        
    return Response(content=audio_bytes, media_type="audio/wav")

@app.post("/api/oral/sessions/start")
def start_oral_session(payload: dict, user_id: int = Query(1)):
    deck_id = payload.get("deck_id")
    if not deck_id:
        raise HTTPException(status_code=400, detail="deck_id requerido")
        
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO oral_sessions (deck_id, user_id, started_at)
        VALUES (?, ?, datetime('now'));
    """, (deck_id, user_id))
    session_id = cursor.lastrowid
    
    cursor.execute("SELECT * FROM oral_questions WHERE deck_id = ? ORDER BY id ASC;", (deck_id,))
    questions = []
    for o in cursor.fetchall():
        od = dict(o)
        od["key_points"] = json.loads(od["key_points_json"]) if od["key_points_json"] else []
        questions.append(od)
        
    conn.commit()
    conn.close()
    
    return {
        "session_id": session_id,
        "deck_id": deck_id,
        "questions": questions
    }

@app.post("/api/oral/sessions/{session_id}/answer/{question_id}")
async def submit_oral_answer(
    session_id: int,
    question_id: int,
    audio: UploadFile = File(...)
):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.*, d.notes_text 
        FROM oral_sessions s
        JOIN decks d ON s.deck_id = d.id
        WHERE s.id = ?;
    """, (session_id,))
    session = cursor.fetchone()
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Sesión oral no encontrada")
        
    notes_context = session["notes_text"] or ""
    
    cursor.execute("SELECT * FROM oral_questions WHERE id = ?;", (question_id,))
    q_row = cursor.fetchone()
    if not q_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Pregunta oral no encontrada")
        
    question_text = q_row["question_text"]
    concept = q_row["concept"] or ""
    key_points = json.loads(q_row["key_points_json"]) if q_row["key_points_json"] else []
    
    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/webm"
    
    # STT Transcription with explicit verbatim filler words instruction
    try:
        transcript = transcribe_audio_with_gemini(audio_bytes, mime_type=mime_type)
    except Exception as e:
        print(f"STT Error: {e}")
        transcript = f"Respuesta oral registrada. ({str(e)})"

    # Evaluation with gemini-3.8-flash
    evaluation = evaluate_oral_answer_with_gemini(
        transcript=transcript,
        question_text=question_text,
        concept=concept,
        key_points=key_points,
        notes_context=notes_context
    )
    
    cursor.execute("""
        INSERT INTO oral_answers (
            session_id, question_id, transcript, score, clarity_score,
            filler_word_count, pause_count, feedback,
            key_points_mentioned_json, key_points_missed_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        session_id,
        question_id,
        transcript,
        evaluation["score"],
        evaluation["clarity_score"],
        evaluation["filler_word_count"],
        evaluation["pause_count"],
        evaluation["feedback"],
        json.dumps(evaluation.get("key_points_mentioned", [])),
        json.dumps(evaluation.get("key_points_missed", []))
    ))
    answer_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {
        "answer_id": answer_id,
        "transcript": transcript,
        "highlighted_transcript": evaluation.get("highlighted_transcript") or transcript,
        "score": evaluation["score"],
        "clarity_score": evaluation["clarity_score"],
        "filler_word_count": evaluation["filler_word_count"],
        "pause_count": evaluation["pause_count"],
        "feedback": evaluation["feedback"],
        "key_points_mentioned": evaluation.get("key_points_mentioned", []),
        "key_points_missed": evaluation.get("key_points_missed", []),
        "detected_filler_words": evaluation.get("detected_filler_words", [])
    }

@app.post("/api/oral/sessions/{session_id}/complete")
def complete_oral_session(session_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT AVG(score) as avg_score, AVG(clarity_score) as avg_clarity, 
               SUM(filler_word_count) as total_fillers, COUNT(*) as answer_count
        FROM oral_answers
        WHERE session_id = ?;
    """, (session_id,))
    stats = cursor.fetchone()
    
    overall_score = round(stats["avg_score"] or 0)
    
    cursor.execute("""
        UPDATE oral_sessions
        SET completed_at = datetime('now'),
            overall_score = ?
        WHERE id = ?;
    """, (overall_score, session_id))
    
    conn.commit()
    conn.close()
    
    return {
        "session_id": session_id,
        "overall_score": overall_score,
        "avg_clarity": round(stats["avg_clarity"] or 0),
        "total_fillers": stats["total_fillers"] or 0,
        "answer_count": stats["answer_count"]
    }

# ==================== INSTAGRAM-STYLE FORUM FEED ====================

@app.get("/api/forum/feed")
@app.get("/api/forum/posts")
def get_forum_feed(current_user_id: Optional[int] = Query(1)):
    """
    CRITICAL REQUIREMENT:
    El foro SOLO debe mostrar los apuntes/mazos que los usuarios hayan marcado explícitamente como "Públicos".
    (d.is_public = 1)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.*, 
               u.id as author_id, u.display_name as author_name, u.username as author_username,
               u.university as author_university, u.career as author_career, u.semester as author_semester,
               u.avatar_color as author_avatar_color,
               d.name as deck_name, d.difficulty as deck_difficulty, d.color as deck_color, d.is_public,
               (SELECT COUNT(*) FROM flashcards WHERE deck_id = p.deck_id) as flashcards_count,
               (SELECT COUNT(*) FROM quiz_questions WHERE deck_id = p.deck_id) as quiz_count,
               (SELECT COUNT(*) FROM oral_questions WHERE deck_id = p.deck_id) as oral_count,
               (SELECT COUNT(*) FROM forum_comments WHERE post_id = p.id) as comments_count,
               EXISTS(SELECT 1 FROM forum_likes WHERE post_id = p.id AND user_id = ?) as user_has_liked
        FROM forum_posts p
        JOIN decks d ON p.deck_id = d.id
        JOIN users u ON p.user_id = u.id
        WHERE d.is_public = 1
        ORDER BY p.created_at DESC;
    """, (current_user_id or 1,))
    
    post_rows = cursor.fetchall()
    feed = []
    
    for r in post_rows:
        item = dict(r)
        item["user_has_liked"] = bool(item.get("user_has_liked", 0))
        
        # Fetch up to 5 latest comments for Instagram card
        cursor.execute("""
            SELECT c.id, c.comment_text, c.created_at,
                   u.id as commenter_id, u.display_name as commenter_name, u.username as commenter_username
            FROM forum_comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.post_id = ?
            ORDER BY c.created_at ASC;
        """, (item["id"],))
        item["comments"] = [dict(c) for c in cursor.fetchall()]
        feed.append(item)
        
    conn.close()
    return feed

@app.post("/api/forum/posts/{post_id}/comments")
def add_forum_comment(post_id: int, payload: ForumCommentCreate, user_id: int = Query(1)):
    text = payload.comment_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="El comentario no puede estar vacío.")
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO forum_comments (post_id, user_id, comment_text)
        VALUES (?, ?, ?);
    """, (post_id, user_id, text))
    comment_id = cursor.lastrowid
    
    cursor.execute("""
        SELECT c.id, c.comment_text, c.created_at,
               u.id as commenter_id, u.display_name as commenter_name, u.username as commenter_username
        FROM forum_comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.id = ?;
    """, (comment_id,))
    new_comment = dict(cursor.fetchone())
    conn.commit()
    conn.close()
    
    return {"message": "Comentario publicado", "comment": new_comment}

@app.post("/api/forum/posts/{post_id}/like")
def toggle_like_post(post_id: int, user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM forum_likes WHERE post_id = ? AND user_id = ?;", (post_id, user_id))
    existing_like = cursor.fetchone()
    
    if existing_like:
        cursor.execute("DELETE FROM forum_likes WHERE post_id = ? AND user_id = ?;", (post_id, user_id))
        cursor.execute("UPDATE forum_posts SET likes_count = MAX(0, likes_count - 1) WHERE id = ?;", (post_id,))
        liked = False
    else:
        cursor.execute("INSERT INTO forum_likes (post_id, user_id) VALUES (?, ?);", (post_id, user_id))
        cursor.execute("UPDATE forum_posts SET likes_count = likes_count + 1 WHERE id = ?;", (post_id,))
        liked = True
        
    cursor.execute("SELECT likes_count FROM forum_posts WHERE id = ?;", (post_id,))
    row = cursor.fetchone()
    likes = row[0] if row else 0
    
    conn.commit()
    conn.close()
    
    return {"post_id": post_id, "likes_count": likes, "liked": liked}

# ==================== DASHBOARD & PROGRESS ====================

@app.get("/api/dashboard/stats")
def get_dashboard_stats(user_id: int = Query(1)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM decks WHERE user_id = ?;", (user_id,))
    total_decks = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM flashcards f
        JOIN decks d ON f.deck_id = d.id
        WHERE d.user_id = ?;
    """, (user_id,))
    total_cards = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM flashcards f
        JOIN decks d ON f.deck_id = d.id
        WHERE d.user_id = ? AND f.repetitions >= 2;
    """, (user_id,))
    mastered_cards = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM flashcards f
        JOIN decks d ON f.deck_id = d.id
        WHERE d.user_id = ? AND (f.next_review_at <= datetime('now') OR f.repetitions = 0);
    """, (user_id,))
    cards_due_today = cursor.fetchone()[0]
    
    learning_cards = max(0, total_cards - mastered_cards)
    
    cursor.execute("""
        SELECT COUNT(*), AVG(CAST(score AS FLOAT) / total_questions * 100) 
        FROM quiz_attempts 
        WHERE user_id = ?;
    """, (user_id,))
    quiz_row = cursor.fetchone()
    total_quizzes = quiz_row[0] or 0
    avg_quiz_score = round(quiz_row[1] or 0)
    
    cursor.execute("""
        SELECT COUNT(*), AVG(overall_score)
        FROM oral_sessions 
        WHERE user_id = ? AND completed_at IS NOT NULL;
    """, (user_id,))
    oral_sess_row = cursor.fetchone()
    total_oral_sessions = oral_sess_row[0] or 0
    avg_oral_score = round(oral_sess_row[1] or 0)
    
    cursor.execute("""
        SELECT AVG(a.clarity_score), AVG(a.filler_word_count), SUM(a.filler_word_count)
        FROM oral_answers a
        JOIN oral_sessions s ON a.session_id = s.id
        WHERE s.user_id = ?;
    """, (user_id,))
    oral_ans_row = cursor.fetchone()
    avg_clarity = round(oral_ans_row[0] or 0)
    avg_fillers_per_ans = round(oral_ans_row[1] or 0, 1)
    total_fillers = oral_ans_row[2] or 0
    
    cursor.execute("""
        SELECT s.id, s.completed_at, s.overall_score, d.name as deck_name,
               (SELECT AVG(clarity_score) FROM oral_answers WHERE session_id = s.id) as session_clarity,
               (SELECT SUM(filler_word_count) FROM oral_answers WHERE session_id = s.id) as session_fillers
        FROM oral_sessions s
        JOIN decks d ON s.deck_id = d.id
        WHERE s.user_id = ? AND s.completed_at IS NOT NULL
        ORDER BY s.completed_at ASC
        LIMIT 10;
    """, (user_id,))
    timeline_rows = cursor.fetchall()
    timeline = []
    for r in timeline_rows:
        td = dict(r)
        td["session_clarity"] = round(td["session_clarity"] or 0)
        timeline.append(td)
        
    cursor.execute("""
        SELECT a.*, q.question_text, d.name as deck_name
        FROM oral_answers a
        JOIN oral_questions q ON a.question_id = q.id
        JOIN oral_sessions s ON a.session_id = s.id
        JOIN decks d ON s.deck_id = d.id
        WHERE s.user_id = ?
        ORDER BY a.created_at DESC
        LIMIT 6;
    """, (user_id,))
    recent_answers = []
    for r in cursor.fetchall():
        ad = dict(r)
        ad["key_points_mentioned"] = json.loads(ad["key_points_mentioned_json"]) if ad["key_points_mentioned_json"] else []
        ad["key_points_missed"] = json.loads(ad["key_points_missed_json"]) if ad["key_points_missed_json"] else []
        recent_answers.append(ad)
        
    cursor.execute("SELECT fruits_count, quokka_happiness FROM users WHERE id = ?;", (user_id,))
    user_quokka = cursor.fetchone()
    fruits_count = user_quokka["fruits_count"] if user_quokka else 5
    quokka_happiness = user_quokka["quokka_happiness"] if user_quokka else 85
        
    conn.close()
    
    return {
        "total_decks": total_decks,
        "total_cards": total_cards,
        "mastered_cards": mastered_cards,
        "learning_cards": learning_cards,
        "cards_due_today": cards_due_today,
        "total_quizzes": total_quizzes,
        "avg_quiz_score": avg_quiz_score,
        "total_oral_sessions": total_oral_sessions,
        "avg_oral_score": avg_oral_score,
        "avg_clarity": avg_clarity,
        "avg_fillers_per_ans": avg_fillers_per_ans,
        "total_fillers": total_fillers,
        "fruits_count": fruits_count,
        "quokka_happiness": quokka_happiness,
        "timeline": timeline,
        "recent_answers": recent_answers
    }
