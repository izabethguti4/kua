import uvicorn
import os
import sys

if __name__ == "__main__":
    # Ensure current working directory is on python path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        
    # Force UTF-8 encoding for Windows console output
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("=" * 60)
    print("[*] Iniciando Kua - Estudio Inteligente & Examen Oral con IA")
    print("[*] Servidor disponible en: http://127.0.0.1:8000")
    print("=" * 60)

    
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
