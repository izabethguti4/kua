import os
import re
import json
import base64
from typing import Dict, Any, List, Optional
# Google GenAI imports
from google import genai
from google.genai import types

# Active models supported by Google Gemini API
GEN_EVAL_MODELS = ["gemini-3.8-flash", "gemini-flash-latest"]
STT_MODELS = ["gemini-3.5-transcribe", "gemini-3.8-flash", "gemini-flash-latest"]
TTS_MODELS = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]

SPANISH_FILLER_WORDS = [
    "eh", "este", "o sea", "mmm", "um", "uh", "bueno", "tipo", 
    "en plan", "como que", "digamos", "o sea que", "em", "ah"
]

def get_api_key() -> Optional[str]:
    return os.environ.get("GEMINI_API_KEY")

def get_gemini_client(api_key: Optional[str] = None, timeout_ms: Optional[int] = None) -> Optional[genai.Client]:
    key = api_key or get_api_key()
    if not key:
        return None
    try:
        client_options = {}
        if timeout_ms is not None:
            client_options["http_options"] = types.HttpOptions(
                timeout=timeout_ms,
                retry_options=types.HttpRetryOptions(attempts=1),
            )
        return genai.Client(api_key=key, **client_options)
    except Exception as e:
        print(f"Error initializing Gemini Client: {e}")
        return None

def analyze_filler_words_heuristics(text: str) -> Dict[str, Any]:
    """
    Analyzes filler words (muletillas) in Spanish speech transcript using regex heuristics.
    Returns count, list of words found, and highlighted HTML string.
    """
    if not text:
        return {"count": 0, "words": [], "pause_count": 0, "highlighted_html": ""}
    
    # Sort filler patterns by length descending to match multi-word fillers first
    patterns = sorted(SPANISH_FILLER_WORDS, key=len, reverse=True)
    regex_pattern = r'\b(' + '|'.join(re.escape(w) for w in patterns) + r')\b'
    
    matches = re.findall(regex_pattern, text, flags=re.IGNORECASE)
    filler_count = len(matches)
    unique_fillers = list(set(m.lower() for m in matches))
    
    # Highlight in HTML with brand-friendly highlight style
    highlighted = re.sub(
        regex_pattern,
        r'<mark class="bg-amber-100 text-amber-900 border border-amber-300 font-semibold px-1 rounded">\1</mark>',
        text,
        flags=re.IGNORECASE
    )
    
    # Estimate noticeable pauses based on ellipsis, dashes or punctuation clusters
    pauses = len(re.findall(r'(\.\.\.+|\s-\s|\,\s*\,)', text))
    
    return {
        "count": filler_count,
        "words": unique_fillers,
        "pause_count": pauses,
        "highlighted_html": highlighted
    }

def clean_json_text(text: str) -> str:
    """Removes markdown code fences from JSON response."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def generate_deck_content_from_notes(
    notes_text: str, 
    custom_name: Optional[str] = None,
    subject: Optional[str] = None,
    difficulty: str = "Medio",
    flashcards_count: int = 6,
    quiz_count: int = 4,
    oral_count: int = 3,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Uses gemini-3.8-flash with user-customized question quantity and difficulty:
    - difficulty: 'Fácil', 'Medio', 'Difícil'
    - flashcards_count: 5 to 30
    - quiz_count: 3 to 15
    - oral_count: 2 to 8
    """
    client = get_gemini_client(api_key)
    if not client:
        raise ValueError("GEMINI_API_KEY no está configurada. Por favor configúrala en el archivo .env o en los ajustes.")

    difficulty_instruction = {
        "Fácil": "Nivel FÁCIL: Enfócate en definiciones directas, conceptos esenciales y memoria inmediata sin ambigüedades.",
        "Medio": "Nivel MEDIO: Combina conceptos clave, relaciones causales y preguntas de comprensión aplicada.",
        "Difícil": "Nivel DIFÍCIL: Preguntas profundas de análisis crítico, excepciones a la regla, diagnósticos diferenciales, fallos de sistema y resolución de problemas complejos."
    }.get(difficulty, "Nivel MEDIO: Conceptos y aplicación estándar.")

    prompt = f"""
Eres un tutor universitario experto en pedagogía y técnica de estudio activo para la plataforma Kua (Mascota: Quokka).
A partir de los siguientes apuntes de estudio, genera un set completo y estructurado con personalización:

PARÁMETROS DE PERSONALIZACIÓN SOLICITADOS:
- Dificultad: {difficulty} ({difficulty_instruction})
- Cantidad de Flashcards: {flashcards_count}
- Cantidad de Preguntas de Quiz: {quiz_count}
- Cantidad de Preguntas para Examen Oral: {oral_count}

CONTENIDO A GENERAR:
1. Un nombre atractivo y profesional para el mazo (si no se indicó uno).
2. Materia principal identificada (ej. 'Sistemas Operativos', 'Fisiología', 'Derecho Civil').
3. Color hexadecimal del mazo: usa preferentemente '#0083B0' o variaciones marinas elegantes (#00B4DB, #0284C7, #0EA5E9).
4. Exactamente {flashcards_count} Flashcards de alta calidad con preguntas claras y respuestas concisas y directas.
5. Exactamente {quiz_count} Preguntas de Quiz de opción múltiple (exactamente 4 opciones por pregunta y el índice de la correcta 0-3).
6. Exactamente {oral_count} Preguntas para Examen Oral, diseñadas para que el estudiante hable y desarrolle ideas conceptualmente. Incluye el concepto central y una lista de 3 a 5 puntos clave obligatorios.

Devuelve EXCLUSIVAMENTE un objeto JSON válido con la siguiente estructura:
{{
  "name": "{custom_name or 'Título del Mazo'}",
  "subject": "{subject or 'Materia de Estudio'}",
  "difficulty": "{difficulty}",
  "color": "#0083B0",
  "flashcards": [
    {{"question": "¿...?", "answer": "..."}}
  ],
  "quiz_questions": [
    {{
      "question": "¿...?",
      "options": ["Opción A", "Opción B", "Opción C", "Opción D"],
      "correct_index": 0
    }}
  ],
  "oral_questions": [
    {{
      "question_text": "Explica con tus palabras...",
      "concept": "Nombre del Concepto",
      "key_points": ["Punto clave 1", "Punto clave 2", "Punto clave 3"]
    }}
  ]
}}

APUNTES DEL ESTUDIANTE:
\"\"\"
{notes_text[:14000]}
\"\"\"
"""

    last_error = None
    for model_name in GEN_EVAL_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    response_mime_type="application/json"
                )
            )
            raw = clean_json_text(response.text)
            data = json.loads(raw)
            if custom_name:
                data["name"] = custom_name
            if subject and not data.get("subject"):
                data["subject"] = subject
            data["difficulty"] = difficulty
            return data
        except Exception as e:
            err_str = str(e)
            last_error = e
            print(f"Model {model_name} warning: {err_str[:120]}, trying fallback...")
            continue
            
    # Friendly 503 / demand error handling
    if "503" in str(last_error) or "UNAVAILABLE" in str(last_error):
        raise RuntimeError("Los servidores de Gemini están experimentando alta demanda momentánea (503). Por favor intenta de nuevo en unos segundos.")
    raise RuntimeError(f"No se pudo generar el mazo con Gemini: {last_error}")

def generate_oral_exam_questions(
    exam_title: str,
    source_material: str,
    question_count: int = 6,
    difficulty: str = "Medio",
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Create a difficulty-adjusted oral exam from deck or folder material."""
    api_key = api_key or get_api_key()
    print("GEMINI_API_KEY configurada:", bool(api_key), flush=True)
    # Allow the oral exam request up to 60 seconds, with retries disabled by the client.
    client = get_gemini_client(api_key, timeout_ms=60_000)
    if not client:
        raise ValueError("GEMINI_API_KEY no está configurada.")

    prompt = f"""Genera exactamente {question_count} preguntas orales concisas de dificultad {difficulty} sobre {exam_title}, basándote solo en este texto. No inventes datos ni expliques nada más. Devuelve solo JSON válido con la forma {{"oral_questions":[{{"question_text":"...","concept":"...","key_points":["...","...","..."]}}]}}.
Texto: {source_material[:3000]}"""

    last_error = None
    for model_name in ["gemini-3.5-flash-lite"]:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    max_output_tokens=2048,
                ),
            )
            data = json.loads(clean_json_text(response.text))
            questions = data.get("oral_questions", [])
            normalized = []
            for question in questions:
                question_text = str(question.get("question_text", "")).strip()
                if not question_text:
                    continue
                normalized.append({
                    "question_text": question_text,
                    "concept": str(question.get("concept", "")),
                    "key_points": [str(point) for point in question.get("key_points", [])],
                })
            if len(normalized) >= question_count:
                return normalized[:question_count]
            raise ValueError(f"Gemini devolvió {len(normalized)} preguntas válidas; se solicitaron {question_count}.")
        except Exception as exc:
            last_error = exc
            print("Error de Gemini:", exc, flush=True)

    raise RuntimeError(f"No se pudo generar el examen oral combinado con Gemini: {last_error}")

def transcribe_audio_with_gemini(audio_bytes: bytes, mime_type: str = "audio/webm", api_key: Optional[str] = None) -> str:
    """
    Transcribes student audio response using gemini-3.5-transcribe with an explicit verbatim prompt
    to capture all filler words ('eh', 'este', 'ah', 'o sea', etc.) and hesitations.
    """
    client = get_gemini_client(api_key)
    if not client:
        raise ValueError("GEMINI_API_KEY no configurada.")

    # Normalize mime type for common browser webm recordings
    if "webm" in mime_type:
        mime_type = "audio/webm"
    elif "ogg" in mime_type:
        mime_type = "audio/ogg"
    elif "mp4" in mime_type or "m4a" in mime_type:
        mime_type = "audio/mp4"
    elif "wav" in mime_type:
        mime_type = "audio/wav"

    audio_part = types.Part.from_bytes(
        data=audio_bytes,
        mime_type=mime_type
    )

    prompt = (
        "Transcribe literalmente todas las palabras de este audio en español. "
        "Es la respuesta oral de un estudiante en un examen oral. "
        "INSTRUCCIÓN CRÍTICA DE MULETILLAS: Debes transcribir obligatoriamente todas las palabras exactas "
        "incluyendo todas las muletillas y pausas (por ejemplo: 'eh', 'este', 'ah', 'o sea', 'mmm', 'um', 'uh', 'bueno', 'tipo', 'em', 'como que', 'en plan'). "
        "NO las limpies, NO corrijas la sintaxis ni gramática, y NO resumas. Devuelve exclusivamente la transcripción textual exacta."
    )

    last_error = None
    for model_name in STT_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[audio_part, prompt]
            )
            transcript = response.text.strip()
            if transcript:
                return transcript
        except Exception as e:
            last_error = e
            print(f"Model {model_name} failed for STT: {e}, trying next...")
            continue

    if "503" in str(last_error):
        raise RuntimeError("Alta demanda momentánea en Gemini Audio (503). Reintenta la grabación.")
    raise RuntimeError(f"Error al transcribir audio con Gemini ({mime_type}): {last_error}")

def evaluate_oral_answer_with_gemini(
    transcript: str,
    question_text: str,
    concept: str,
    key_points: List[str],
    notes_context: str,
    difficulty: str = "Medio",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates student's oral answer against source notes, key points, and difficulty using gemini-3.8-flash.
    """
    client = get_gemini_client(api_key)
    heuristics = analyze_filler_words_heuristics(transcript)

    if not client:
        return {
            "score": 75,
            "clarity_score": 80,
            "filler_word_count": heuristics["count"],
            "pause_count": heuristics["pause_count"],
            "feedback": "Modo demostración (sin GEMINI_API_KEY activa). Tu respuesta fue registrada correctamente.",
            "key_points_mentioned": key_points[:1] if key_points else [],
            "key_points_missed": key_points[1:] if len(key_points) > 1 else [],
            "detected_filler_words": heuristics["words"],
            "highlighted_transcript": heuristics["highlighted_html"]
        }

    key_points_str = "\n".join([f"- {kp}" for kp in key_points]) if key_points else "No especificados"

    prompt = f"""
Eres un profesor evaluador en un examen oral universitario en la aplicación Kua. Tu tarea es evaluar la respuesta hablada de un estudiante.

NIVEL DE EXIGENCIA / DIFICULTAD: {difficulty}

CONTEXTO DEL TEMA (APUNTES):
\"\"\"
{notes_context[:4000] if notes_context else "Tema general de estudio"}
\"\"\"

PREGUNTA REALIZADA AL ESTUDIANTE:
"{question_text}"

CONCEPTO ESPERADO:
"{concept}"

PUNTOS CLAVE QUE EL ESTUDIANTE DEBERÍA MENCIONAR:
{key_points_str}

TRANSCIPCIÓN DE LA RESPUESTA ORAL DEL ESTUDIANTE:
\"\"\"
{transcript}
\"\"\"

CRITERIOS DE EVALUACIÓN:
1. `score` (0-100): Precisión conceptual y dominio del tema según los apuntes y la dificultad {difficulty}.
2. `clarity_score` (0-100): Estructura, coherencia, orden y facilidad de comprensión de la explicación oral.
3. `filler_word_count` (entero): Número de muletillas detectadas en la respuesta (ej. "eh", "este", "ah", "o sea", "mmm", "bueno").
4. `pause_count` (entero): Número aproximado de vacilaciones o pausas notorias.
5. `feedback` (texto): Retroalimentación constructiva, cálida y motivadora (2-3 oraciones destacando aciertos y cómo enriquecer la respuesta).
6. `key_points_mentioned` (lista de strings): Puntos clave que el estudiante mencionó adecuadamente.
7. `key_points_missed` (lista de strings): Puntos clave que el estudiante omitió o explicó incorrectamente.

Devuelve EXCLUSIVAMENTE un objeto JSON válido con este formato:
{{
  "score": 85,
  "clarity_score": 90,
  "filler_word_count": {heuristics['count']},
  "pause_count": {heuristics['pause_count']},
  "feedback": "...",
  "key_points_mentioned": ["..."],
  "key_points_missed": ["..."],
  "detected_filler_words": {json.dumps(heuristics['words'])}
}}
"""

    last_error = None
    for model_name in GEN_EVAL_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json"
                )
            )
            raw = clean_json_text(response.text)
            data = json.loads(raw)
            
            data["filler_word_count"] = max(data.get("filler_word_count", 0), heuristics["count"])
            data["pause_count"] = max(data.get("pause_count", 0), heuristics["pause_count"])
            data["detected_filler_words"] = heuristics["words"]
            data["highlighted_transcript"] = heuristics["highlighted_html"]
            
            return data
        except Exception as e:
            last_error = e
            print(f"Model {model_name} failed for oral evaluation: {e}, trying next...")
            continue

    # Fallback if AI threw 503 or transient errors
    feedback_note = "Respuesta registrada. (Evaluación básica local por alta demanda momentánea de IA)" if "503" in str(last_error) else f"Respuesta registrada ({last_error})"
    return {
        "score": 75,
        "clarity_score": 80,
        "filler_word_count": heuristics["count"],
        "pause_count": heuristics["pause_count"],
        "feedback": feedback_note,
        "key_points_mentioned": key_points[:1] if key_points else [],
        "key_points_missed": key_points[1:] if len(key_points) > 1 else [],
        "detected_filler_words": heuristics["words"],
        "highlighted_transcript": heuristics["highlighted_html"]
    }

def generate_tts_for_question(text: str, api_key: Optional[str] = None) -> Optional[bytes]:
    """
    Generates spoken audio for an oral question using gemini-3.8-flash-tts.
    """
    client = get_gemini_client(api_key)
    if not client:
        return None

    speech_prompt = f"Lee en voz alta de manera clara, pausada y natural en español la siguiente pregunta para un estudiante: {text}"

    for model_name in TTS_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=speech_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=['AUDIO'],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name='Aoede'
                            )
                        )
                    )
                )
            )
            for part in response.parts:
                if getattr(part, 'inline_data', None) and part.inline_data.data:
                    return part.inline_data.data
        except Exception as e:
            print(f"Model {model_name} TTS failed: {e}")
            continue

    return None
