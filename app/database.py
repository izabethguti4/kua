import os
import json
import hashlib
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "kua.db")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    from psycopg2 import IntegrityError
    from psycopg2.extras import DictCursor
else:
    import sqlite3
    IntegrityError = sqlite3.IntegrityError


def _postgres_placeholders(sql: str) -> str:
    """Translate SQLite qmark parameters while leaving quoted question marks alone."""
    result = []
    quote = None
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote:
            result.append(char)
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    result.append(sql[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
            result.append(char)
        elif char == "?":
            result.append("%s")
        else:
            result.append(char)
        index += 1
    return "".join(result)


class DatabaseCursor:
    """Small DB-API compatibility wrapper for existing SQLite-style queries."""
    _serial_tables = {
        "users", "folders", "decks", "flashcards", "quiz_questions",
        "oral_questions", "oral_sessions", "oral_answers", "quiz_attempts",
        "forum_posts", "forum_comments", "forum_likes",
    }

    def __init__(self, connection):
        self.connection = connection
        self.raw = connection.raw.cursor(cursor_factory=DictCursor) if connection.is_postgres else connection.raw.cursor()
        self._lastrowid = None

    def execute(self, sql, params=()):
        self._lastrowid = None
        if self.connection.is_postgres:
            stripped = sql.strip()
            if re.match(r"PRAGMA\s+foreign_keys", stripped, re.I):
                return self
            table_info = re.match(r"PRAGMA\s+table_info\((\w+)\)", stripped, re.I)
            if table_info:
                self.raw.execute(
                    "SELECT column_name AS name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position;",
                    (table_info.group(1),),
                )
                return self

            sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "SERIAL PRIMARY KEY", sql, flags=re.I)
            sql = re.sub(r"datetime\(\s*'now'\s*\)", "CURRENT_TIMESTAMP", sql, flags=re.I)
            sql = _postgres_placeholders(sql)

            insert = re.match(r"\s*INSERT\s+INTO\s+(\w+)", sql, re.I)
            if insert and insert.group(1).lower() in self._serial_tables and not re.search(r"\bRETURNING\b", sql, re.I):
                sql = sql.rstrip().rstrip(";") + " RETURNING id"
                self.raw.execute(sql, params or ())
                row = self.raw.fetchone()
                self._lastrowid = row[0] if row else None
                return self

        self.raw.execute(sql, params or ())
        if not self.connection.is_postgres:
            self._lastrowid = self.raw.lastrowid
        return self

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self.raw.rowcount

    def fetchone(self):
        return self.raw.fetchone()

    def fetchall(self):
        return self.raw.fetchall()

    def close(self):
        self.raw.close()


class DatabaseConnection:
    def __init__(self, raw, is_postgres):
        self.raw = raw
        self.is_postgres = is_postgres

    def cursor(self):
        return DatabaseCursor(self)

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

def get_db():
    if USE_POSTGRES:
        database_url = DATABASE_URL
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        return DatabaseConnection(psycopg2.connect(database_url), True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return DatabaseConnection(conn, False)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 1. Users table (with handle, university, career, semester, password, quokka pet stats)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        display_name TEXT NOT NULL,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password_hash TEXT,
        university TEXT,
        career TEXT,
        semester TEXT,
        bio TEXT,
        avatar_color TEXT DEFAULT '#0083B0',
        fruits_count INTEGER DEFAULT 5,
        quokka_happiness INTEGER DEFAULT 85,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Run migrations for existing users table columns if needed
    cursor.execute("PRAGMA table_info(users);")
    existing_user_cols = [col["name"] for col in cursor.fetchall()]
    user_cols_to_add = {
        "username": "TEXT",
        "password_hash": "TEXT",
        "university": "TEXT",
        "career": "TEXT",
        "semester": "TEXT",
        "avatar_color": "TEXT DEFAULT '#0083B0'",
        "fruits_count": "INTEGER DEFAULT 5",
        "quokka_happiness": "INTEGER DEFAULT 85",
        "profile_image": "TEXT",
        "banner_color": "TEXT DEFAULT '#0083B0'"
    }
    for col_name, col_type in user_cols_to_add.items():
        if col_name not in existing_user_cols:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")
            except Exception as e:
                print(f"Migration note for users.{col_name}: {e}")

    # 2. Folders for organizing each user's decks.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        color TEXT NOT NULL DEFAULT '#0083B0',
        image_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE (user_id, name)
    );
    """)

    cursor.execute("PRAGMA table_info(folders);")
    existing_folder_cols = [col["name"] for col in cursor.fetchall()]
    for col_name, col_type in {"color": "TEXT NOT NULL DEFAULT '#0083B0'", "image_path": "TEXT"}.items():
        if col_name not in existing_folder_cols:
            cursor.execute(f"ALTER TABLE folders ADD COLUMN {col_name} {col_type};")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auth_sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 3. Decks table (with is_public column)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS decks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        name TEXT NOT NULL,
        source_filename TEXT,
        notes_text TEXT,
        subject TEXT,
        difficulty TEXT DEFAULT 'Medio',
        is_public INTEGER DEFAULT 0,
        color TEXT DEFAULT '#0083B0',
        cloned_from_id INTEGER,
        folder_id INTEGER,
        is_exam_only INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE SET NULL
    );
    """)

    cursor.execute("PRAGMA table_info(decks);")
    existing_deck_cols = [col["name"] for col in cursor.fetchall()]
    deck_cols_to_add = {
        "subject": "TEXT",
        "difficulty": "TEXT DEFAULT 'Medio'",
        "is_public": "INTEGER DEFAULT 0",
        "cloned_from_id": "INTEGER",
        "folder_id": "INTEGER REFERENCES folders(id) ON DELETE SET NULL",
        "is_exam_only": "INTEGER NOT NULL DEFAULT 0"
    }
    for col_name, col_type in deck_cols_to_add.items():
        if col_name not in existing_deck_cols:
            try:
                cursor.execute(f"ALTER TABLE decks ADD COLUMN {col_name} {col_type};")
            except Exception as e:
                print(f"Migration note for decks.{col_name}: {e}")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decks_folder_id ON decks(folder_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_folders_user_id ON folders(user_id);")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS generation_jobs (
        job_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        deck_id INTEGER,
        status TEXT NOT NULL DEFAULT 'queued',
        message TEXT NOT NULL DEFAULT 'Generando mazo...',
        error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE SET NULL
    );
    """)
    
    # 3. Flashcards with SM-2
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS flashcards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_id INTEGER,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        easiness_factor REAL DEFAULT 2.5,
        interval_days INTEGER DEFAULT 0,
        repetitions INTEGER DEFAULT 0,
        next_review_at TIMESTAMP,
        last_reviewed_at TIMESTAMP,
        FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
    );
    """)
    
    # 4. Quiz
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS quiz_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_id INTEGER,
        question TEXT NOT NULL,
        options_json TEXT NOT NULL,
        correct_index INTEGER NOT NULL,
        FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
    );
    """)
    
    # 5. Preguntas orales
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS oral_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_id INTEGER,
        question_text TEXT NOT NULL,
        concept TEXT,
        key_points_json TEXT,
        FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
    );
    """)
    
    # 6. Sesiones orales
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS oral_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_id INTEGER,
        user_id INTEGER DEFAULT 1,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        overall_score INTEGER,
        FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("PRAGMA table_info(oral_sessions);")
    existing_oral_cols = [col["name"] for col in cursor.fetchall()]
    if "user_id" not in existing_oral_cols:
        try:
            cursor.execute("ALTER TABLE oral_sessions ADD COLUMN user_id INTEGER DEFAULT 1;")
        except Exception:
            pass
    
    # 7. Respuestas orales con métricas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS oral_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        question_id INTEGER,
        transcript TEXT,
        score INTEGER,
        clarity_score INTEGER,
        filler_word_count INTEGER,
        pause_count INTEGER,
        feedback TEXT,
        key_points_mentioned_json TEXT,
        key_points_missed_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES oral_sessions(id) ON DELETE CASCADE
    );
    """)

    # 8. Quiz Attempts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_id INTEGER,
        user_id INTEGER DEFAULT 1,
        score INTEGER,
        total_questions INTEGER,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("PRAGMA table_info(quiz_attempts);")
    existing_quiz_cols = [col["name"] for col in cursor.fetchall()]
    if "user_id" not in existing_quiz_cols:
        try:
            cursor.execute("ALTER TABLE quiz_attempts ADD COLUMN user_id INTEGER DEFAULT 1;")
        except Exception:
            pass

    # 9. Forum Posts (Feed tipo Instagram)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS forum_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        deck_id INTEGER,
        title TEXT NOT NULL,
        description TEXT,
        subject TEXT,
        source_filename TEXT,
        notes_text TEXT,
        likes_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE SET NULL
    );
    """)

    cursor.execute("PRAGMA table_info(forum_posts);")
    existing_post_cols = [col["name"] for col in cursor.fetchall()]
    if "subject" not in existing_post_cols:
        try:
            cursor.execute("ALTER TABLE forum_posts ADD COLUMN subject TEXT;")
        except Exception:
            pass

    # 10. Forum Comments (Comentarios estilo Instagram)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS forum_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        comment_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES forum_posts(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 11. Forum Likes (Para evitar likes duplicados por usuario)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS forum_likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(post_id, user_id)
    );
    """)
    
    conn.commit()
    conn.close()
    
    seed_initial_data()
    if USE_POSTGRES:
        _synchronize_postgres_sequences()


def _synchronize_postgres_sequences():
    # Seed data assigns fixed IDs, so advance each serial sequence before user inserts.
    serial_tables = (
        "users", "folders", "decks", "flashcards", "quiz_questions",
        "oral_questions", "oral_sessions", "oral_answers", "quiz_attempts",
        "forum_posts", "forum_comments", "forum_likes",
    )
    conn = get_db()
    cursor = conn.cursor()
    for table in serial_tables:
        cursor.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1), "
            f"EXISTS (SELECT 1 FROM {table}));"
        )
    conn.commit()
    conn.close()

def seed_initial_data():
    conn = get_db()
    cursor = conn.cursor()
    
    # Seed default users with university handles
    cursor.execute("SELECT COUNT(*) FROM users;")
    user_count = cursor.fetchone()[0]
    
    default_pw_hash = hash_password("kua123")

    if user_count == 0:
        cursor.execute("""
            INSERT INTO users (id, display_name, username, email, password_hash, university, career, semester, bio, fruits_count, quokka_happiness)
            VALUES 
            (1, 'Estudiante Kua', 'estudiante_kua', 'demo@kua.edu', ?, 'Universidad Nacional', 'Ingeniería de Sistemas', '7mo Semestre', 'Amante del estudio activo, la oratoria y los quokkas.', 8, 90),
            (2, 'Dra. Sofía Mendoza', 'sofi_med', 'sofia@kua.edu', ?, 'Facultad de Medicina', 'Medicina Humana', '5to Semestre', 'Compartiendo resúmenes de fisiología y biología celular.', 12, 100),
            (3, 'Carlos Arismendi', 'carlos_dev', 'carlos@kua.edu', ?, 'Instituto Tecnológico', 'Ciencias de la Computación', '6to Semestre', 'Apuntes de arquitectura, SO y redes.', 5, 80);
        """, (default_pw_hash, default_pw_hash, default_pw_hash))
    else:
        # Ensure default users have usernames and profile information
        cursor.execute("UPDATE users SET username = 'estudiante_kua', university = COALESCE(university, 'Universidad Nacional'), career = COALESCE(career, 'Ingeniería de Sistemas'), semester = COALESCE(semester, '7mo Semestre'), fruits_count = COALESCE(fruits_count, 8), quokka_happiness = COALESCE(quokka_happiness, 90) WHERE id = 1 AND (username IS NULL OR username = '');")
        cursor.execute("UPDATE users SET username = 'sofi_med', university = COALESCE(university, 'Facultad de Medicina'), career = COALESCE(career, 'Medicina Humana'), semester = COALESCE(semester, '5to Semestre'), fruits_count = COALESCE(fruits_count, 12), quokka_happiness = COALESCE(quokka_happiness, 100) WHERE id = 2 AND (username IS NULL OR username = '');")
        cursor.execute("UPDATE users SET username = 'carlos_dev', university = COALESCE(university, 'Instituto Tecnológico'), career = COALESCE(career, 'Ciencias de la Computación'), semester = COALESCE(semester, '6to Semestre'), fruits_count = COALESCE(fruits_count, 5), quokka_happiness = COALESCE(quokka_happiness, 80) WHERE id = 3 AND (username IS NULL OR username = '');")
        
        # Ensure doctor user exists if id 2 was deleted
        cursor.execute("SELECT id FROM users WHERE username = 'sofi_med';")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (display_name, username, email, password_hash, university, career, semester, bio, fruits_count, quokka_happiness)
                VALUES ('Dra. Sofía Mendoza', 'sofi_med', 'sofia@kua.edu', ?, 'Facultad de Medicina', 'Medicina Humana', '5to Semestre', 'Compartiendo resúmenes de fisiología y biología celular.', 12, 100);
            """, (default_pw_hash,))

        cursor.execute("SELECT id FROM users WHERE username = 'carlos_dev';")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (display_name, username, email, password_hash, university, career, semester, bio, fruits_count, quokka_happiness)
                VALUES ('Carlos Arismendi', 'carlos_dev', 'carlos@kua.edu', ?, 'Instituto Tecnológico', 'Ciencias de la Computación', '6to Semestre', 'Apuntes de arquitectura, SO y redes.', 5, 80);
            """, (default_pw_hash,))

    # Seed Decks if none exist
    cursor.execute("SELECT COUNT(*) FROM decks;")
    deck_count = cursor.fetchone()[0]

    so_notes = (
        "Sistemas Operativos: Memoria Virtual y Paginación.\n"
        "La memoria virtual es una técnica que permite a los procesos acceder a un espacio de direcciones "
        "contiguo y mayor que la memoria RAM física real. Se implementa mediante paginación o segmentación. "
        "En la paginación, la memoria lógica se divide en páginas de tamaño fijo y la memoria física en marcos (frames). "
        "La tabla de páginas (Page Table) mapea cada página lógica a un marco físico. "
        "Cuando un proceso intenta acceder a una página que no está cargada en RAM, la MMU genera una interrupción "
        "llamada fallo de página (Page Fault). El sistema operativo suspende el proceso, busca la página en el disco "
        "(área de swap o paginación), la carga en un marco libre y actualiza la tabla de páginas. "
        "El TLB (Translation Lookaside Buffer) es una memoria caché de alta velocidad que almacena las traducciones "
        "más recientes para evitar consultar la tabla de páginas en RAM en cada acceso a memoria."
    )

    bio_notes = (
        "Biología Celular: Mitosis y Ciclo Celular.\n"
        "El ciclo celular comprende la interfase (fases G1, S, G2) y la fase M (mitosis y citocinesis). "
        "Durante la fase S se replica el ADN. La mitosis es la división del núcleo celular y consta de 4 etapas: "
        "1. Profase: la cromatina se condensa en cromosomas visibles, desaparece el nucléolo y se forma el huso mitótico. "
        "2. Metafase: los cromosomas se alinean en la placa ecuatorial guiados por los microtúbulos del huso. "
        "3. Anafase: las cromátidas hermanas se separan y migran hacia polos opuestos de la célula. "
        "4. Telofase: se reorganizan las envolturas nucleares alrededor de cada conjunto de cromosomas y los cromosomas se descondensan. "
        "Finalmente ocurre la citocinesis, que es la división del citoplasma resultando en dos células hijas genéticamente idénticas."
    )

    now_iso = datetime.now().isoformat()

    if deck_count == 0:
        # Deck 1 (Public in Forum)
        cursor.execute("""
            INSERT INTO decks (user_id, name, source_filename, notes_text, subject, difficulty, is_public, color)
            VALUES (1, 'Sistemas Operativos: Memoria Virtual', 'apuntes_sistemas_operativos.txt', ?, 'Sistemas Operativos', 'Medio', 1, '#0083B0');
        """, (so_notes,))
        so_deck_id = cursor.lastrowid

        so_flashcards = [
            ("¿Qué es la memoria virtual y cuál es su principal ventaja?",
             "Es una técnica que simula mayor memoria física de la existente en RAM, aislando los procesos y ofreciendo un espacio de direcciones contiguo."),
            ("¿Qué diferencia hay entre una página y un marco (frame)?",
             "Una página es un bloque de memoria lógica/virtual, mientras que un marco (frame) es un bloque de memoria física en RAM, ambos de tamaño idéntico."),
            ("¿Qué ocurre exactamente cuando se produce un Fallo de Página (Page Fault)?",
             "La MMU genera una interrupción, el SO interviene, busca la página en el disco de intercambio (swap), la carga en un marco libre de RAM y actualiza la tabla de páginas."),
            ("¿Cuál es la función del TLB (Translation Lookaside Buffer)?",
             "Es una caché ultrarrápida en el procesador que guarda las traducciones recientes de direcciones virtuales a físicas, acelerando drásticamente el acceso a memoria.")
        ]
        for q, a in so_flashcards:
            cursor.execute("""
                INSERT INTO flashcards (deck_id, question, answer, easiness_factor, interval_days, repetitions, next_review_at, last_reviewed_at)
                VALUES (?, ?, ?, 2.5, 0, 0, ?, ?);
            """, (so_deck_id, q, a, now_iso, now_iso))

        so_quizzes = [
            ("¿Qué componente de hardware se encarga de traducir direcciones virtuales a físicas?",
             json.dumps(["MMU (Memory Management Unit)", "ALU (Arithmetic Logic Unit)", "DMA Controller", "Controlador PCI"]), 0),
            ("Un Fallo de Página (Page Fault) se produce cuando:",
             json.dumps([
                 "La página solicitada no está actualmente presente en la memoria RAM física",
                 "El procesador se queda sin registros disponibles",
                 "Un puntero es nulo en tiempo de compilación",
                 "El bus del sistema se desconecta"
             ]), 0),
            ("¿Por qué el TLB mejora el rendimiento del sistema?",
             json.dumps([
                 "Porque evita consultar dos veces la memoria RAM para cada instrucción",
                 "Porque aumenta automáticamente la frecuencia de reloj del procesador",
                 "Porque comprime las páginas en el disco",
                 "Porque sustituye a la memoria RAM por completo"
             ]), 0)
        ]
        for q, opts, corr in so_quizzes:
            cursor.execute("""
                INSERT INTO quiz_questions (deck_id, question, options_json, correct_index)
                VALUES (?, ?, ?, ?);
            """, (so_deck_id, q, opts, corr))

        so_orals = [
            ("Explica con tus palabras cómo funciona la memoria virtual y qué papel cumple la tabla de páginas.",
             "Memoria Virtual y Paginación",
             json.dumps([
                 "Espacio de direcciones virtuales vs físicos",
                 "División en páginas lógicas y marcos (frames) físicos",
                 "Función de la tabla de páginas como mapa de traducción",
                 "Aislamiento y protección entre procesos"
             ])),
            ("Describe paso a paso qué sucede en el sistema operativo cuando ocurre un fallo de página (page fault).",
             "Manejo de Page Fault por el Sistema Operativo",
             json.dumps([
                 "Detección del bit de presencia por la MMU e interrupción",
                 "Intervención del sistema operativo y verificación de validez",
                 "Lectura de la página desde el almacenamiento secundario (swap)",
                 "Carga en un marco libre y actualización de la tabla de páginas",
                 "Reanudación de la instrucción del proceso"
             ]))
        ]
        for q, concept, kp in so_orals:
            cursor.execute("""
                INSERT INTO oral_questions (deck_id, question_text, concept, key_points_json)
                VALUES (?, ?, ?, ?);
            """, (so_deck_id, q, concept, kp))

        # Deck 2: Biología Celular (Owner: Sofía, Public)
        cursor.execute("SELECT id FROM users WHERE username = 'sofi_med';")
        sofi_row = cursor.fetchone()
        sofi_id = sofi_row[0] if sofi_row else 2

        cursor.execute("""
            INSERT INTO decks (user_id, name, source_filename, notes_text, subject, difficulty, is_public, color)
            VALUES (?, 'Biología Celular: Mitosis y Ciclo Celular', 'apuntes_biologia.txt', ?, 'Biología Celular', 'Fácil', 1, '#00B4DB');
        """, (sofi_id, bio_notes))
        bio_deck_id = cursor.lastrowid

        bio_flashcards = [
            ("¿Cuáles son las 4 fases principales de la mitosis en orden?",
             "Profase, Metafase, Anafase y Telofase."),
            ("¿En qué fase del ciclo celular se duplica el material genético (ADN)?",
             "En la fase S (Síntesis) de la Interfase."),
            ("¿Qué evento crucial caracteriza a la Anafase?",
             "La separación de las cromátidas hermanas hacia los polos opuestos de la célula."),
            ("¿Qué es la citocinesis?",
             "La división física del citoplasma que culmina en dos células hijas independientes.")
        ]
        for q, a in bio_flashcards:
            cursor.execute("""
                INSERT INTO flashcards (deck_id, question, answer, easiness_factor, interval_days, repetitions, next_review_at, last_reviewed_at)
                VALUES (?, ?, ?, 2.5, 0, 0, ?, ?);
            """, (bio_deck_id, q, a, now_iso, now_iso))

        bio_quizzes = [
            ("¿Durante qué fase de la mitosis los cromosomas se alinean en el centro de la célula?",
             json.dumps(["Metafase", "Profase", "Telofase", "Citocinesis"]), 0),
            ("El huso mitótico está compuesto principalmente por:",
             json.dumps(["Microtúbulos", "Filamentos de actina", "Ribosomas", "Lípidos"]), 0)
        ]
        for q, opts, corr in bio_quizzes:
            cursor.execute("""
                INSERT INTO quiz_questions (deck_id, question, options_json, correct_index)
                VALUES (?, ?, ?, ?);
            """, (bio_deck_id, q, opts, corr))

        bio_orals = [
            ("Explica las cuatro etapas de la mitosis y qué ocurre en cada una de ellas.",
             "Fases de la Mitosis",
             json.dumps([
                 "Profase: condensación de cromatina y formación del huso",
                 "Metafase: alineación en placa ecuatorial",
                 "Anafase: separación de cromátidas hermanas",
                 "Telofase y citocinesis: descondensación y división citoplasmática"
             ]))
        ]
        for q, concept, kp in bio_orals:
            cursor.execute("""
                INSERT INTO oral_questions (deck_id, question_text, concept, key_points_json)
                VALUES (?, ?, ?, ?);
            """, (bio_deck_id, q, concept, kp))

        # Seed forum posts for public decks
        cursor.execute("""
            INSERT INTO forum_posts (user_id, deck_id, title, description, subject, source_filename, notes_text, likes_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            1,
            so_deck_id,
            "Resumen de Memoria Virtual y Paginación (SO)",
            "Guía rápida para el parcial de arquitectura. Incluye fallo de página, tablas multinivel y caché TLB.",
            "Sistemas Operativos",
            "apuntes_sistemas_operativos.txt",
            so_notes,
            24
        ))
        so_post_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO forum_posts (user_id, deck_id, title, description, subject, source_filename, notes_text, likes_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            sofi_id,
            bio_deck_id,
            "Mitosis y Ciclo Celular paso a paso 🔬",
            "Fases completas de la división celular para Medicina. ¡Incluye tarjetas listas para memorizar!",
            "Biología Celular",
            "apuntes_biologia.txt",
            bio_notes,
            47
        ))
        bio_post_id = cursor.lastrowid

        # Seed Instagram-like comments
        cursor.execute("""
            INSERT INTO forum_comments (post_id, user_id, comment_text)
            VALUES 
            (?, ?, '¡Excelente mazo! Las preguntas orales me ayudaron muchísimo a preparar la defensa.'),
            (?, ?, 'Muy claro el concepto del fallo de página, gracias por compartirlo 🙌'),
            (?, 1, '¡Mucho éxito a todos los que rinden esta semana!');
        """, (so_post_id, sofi_id, so_post_id, 3, bio_post_id))

    # Ensure public decks have forum posts and is_public flag consistent
    cursor.execute("UPDATE decks SET is_public = 1 WHERE id IN (1, 2);")
    cursor.execute("UPDATE decks SET user_id = 2 WHERE id = 2;")
    cursor.execute("UPDATE forum_posts SET user_id = 2 WHERE deck_id = 2;")

    conn.commit()
    conn.close()
