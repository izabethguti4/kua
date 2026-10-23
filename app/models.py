from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class UserRegister(BaseModel):
    display_name: str = Field(..., description="Nombre completo")
    username: str = Field(..., description="Nombre de usuario (@handle)")
    email: str = Field(..., description="Correo electrónico")
    password: str = Field(..., description="Contraseña")
    university: Optional[str] = Field(None, description="Universidad o institución")
    career: Optional[str] = Field(None, description="Carrera o especialidad")
    semester: Optional[str] = Field(None, description="Semestre o año")

class UserLogin(BaseModel):
    username_or_email: str = Field(..., description="Nombre de usuario o correo")
    password: str = Field(..., description="Contraseña")

class UserProfileUpdate(BaseModel):
    display_name: str
    email: Optional[str] = None
    bio: Optional[str] = None
    university: Optional[str] = None
    career: Optional[str] = None
    semester: Optional[str] = None
    banner_color: Optional[str] = None

class DeckCreate(BaseModel):
    name: str = Field(..., description="Nombre del mazo")
    color: Optional[str] = Field("#0083B0", description="Color representativo")
    notes_text: Optional[str] = Field(None, description="Apuntes asociados")
    subject: Optional[str] = Field("General", description="Materia o asignatura")
    difficulty: Optional[str] = Field("Medio", description="Nivel de dificultad (Fácil, Medio, Difícil)")
    is_public: Optional[bool] = Field(False, description="Compartir públicamente en el foro")

class DeckPrivacyToggle(BaseModel):
    is_public: bool = Field(..., description="True para compartir en foro, False para privado")

class DeckFolderUpdate(BaseModel):
    folder_id: Optional[int] = None

class OralExamRequest(BaseModel):
    question_count: int = Field(6, ge=3, le=15)
    difficulty: Literal["Fácil", "Medio", "Difícil"] = "Medio"

class TextDeckGenerateRequest(BaseModel):
    name: Optional[str] = None
    notes_text: str
    subject: Optional[str] = "General"
    difficulty: Optional[str] = "Medio"
    flashcards_count: Optional[int] = 10
    quiz_count: Optional[int] = 5
    oral_count: Optional[int] = 3
    is_public: Optional[bool] = False
    folder_id: Optional[int] = None

class FlashcardCreate(BaseModel):
    deck_id: int
    question: str
    answer: str

class FlashcardReview(BaseModel):
    grade: int = Field(..., ge=1, le=5, description="Calificación SM-2 de 1 a 5")

class QuizAttemptSubmit(BaseModel):
    deck_id: int
    score: int
    total_questions: int

class SettingsUpdate(BaseModel):
    gemini_api_key: str

class ForumPostCreate(BaseModel):
    title: str = Field(..., description="Título de la publicación")
    description: Optional[str] = Field(None, description="Descripción o resumen")
    subject: Optional[str] = Field("General", description="Materia o asignatura")
    notes_text: str = Field(..., description="Apuntes compartidos con la comunidad")
    deck_id: Optional[int] = None

class ForumCommentCreate(BaseModel):
    comment_text: str = Field(..., min_length=1, description="Texto del comentario")

class QuokkaFeedAction(BaseModel):
    fruit_type: Optional[str] = "fruta"

class AwardFruitRequest(BaseModel):
    session_type: str = Field(..., description="flashcards, quiz, or oral")
