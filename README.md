# 🌊 Kua — Estudio Inteligente & Examen Oral con IA

**Kua** es una plataforma web de estudio diario que combina flashcards con repetición espaciada (SM-2), quizzes interactivos, un foro de comunidad y su diferenciador central: **un simulador de exámenes orales con inteligencia artificial**.

---

## 🎨 Novedades de la Versión 2.0 (Kua)

1. **Rediseño Total: Nombre y Color Celeste Marino**
   - Nombre de la aplicación: **Kua**.
   - Color principal: **Celeste Marino** (`#0083B0` / degradado oceánico `#0083B0` a `#00B4DB`).
   - Tipografía creativa y moderna: **Outfit** + **Plus Jakarta Sans** (geometría limpia, altamente legible).
   - Botones redondeados, micro-patrón náutico y barra de navegación inferior estilizada.

2. **Nuevo Flujo de Examen Oral con Conteo Visual Automático**
   - Al pulsar *"Comenzar Respuesta Oral"*, se despliega una **cuenta regresiva visual (3, 2, 1, ¡Habla ahora!)** con animación emergente.
   - Al finalizar el conteo, el micrófono se activa **automáticamente** sin necesidad de pulsar otro botón.
   - El visualizador de ondas y el cronómetro registran la respuesta en vivo.
   - Al detener, la IA transcribe palabra por palabra y entrega el informe formativo.

3. **Transcripción Literal con Detección de Muletillas**
   - Prompt explícito para **gemini-3.5-transcribe** exigiendo no limpiar ni omitir muletillas (*"eh"*, *"este"*, *"ah"*, *"o sea"*, *"bueno"*, *"mmm"*, *"tipo"*, etc.) ni pausas.
   - Mapeo heurístico complementario que resalta cada muletilla en la transcripción con etiquetas visuales y calcula el conteo exacto para el estudiante.

4. **Funciones de Comunidad & Foro**
   - Nueva pantalla **"Foro"** accesible desde la navegación inferior.
   - Registro de perfil de estudiante (`users` con nombre, correo y biografía).
   - Los estudiantes pueden subir y compartir sus apuntes (PDF o texto).
   - Al publicar en el foro, **la IA de Kua procesa automáticamente los apuntes y genera un mazo completo** (flashcards, quiz y preguntas orales) que cualquier usuario puede estudiar de inmediato con 1 clic.
   - Contador de "Me gusta" (Likes) para las mejores contribuciones de la comunidad.

---

## 🏗️ Stack Tecnológico

| Capa | Tecnologías |
|---|---|
| **Backend** | Python 3.12+, **FastAPI**, Uvicorn, SQLite3 |
| **Frontend** | HTML5, **Alpine.js** (CDN), **Tailwind CSS** (CDN), **Chart.js** (CDN), **Lucide Icons** (CDN) |
| **Inteligencia Artificial** | **Google Gemini API** (`gemini-3.8-flash` para evaluación y mazos; `gemini-3.5-transcribe` para audio; `gemini-3.8-flash-tts` para voz) |
| **Algoritmo de Memoria** | **SuperMemo 2 (SM-2)** |

---

## 🚀 Puesta en Marcha

El servidor ya se encuentra en ejecución:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

Para reiniciar manualmente en cualquier momento:
```powershell
python run.py
```

Para correr las pruebas unitarias:
```powershell
python test_app.py
```
*(11 pruebas automatizadas pasando con éxito).*
