import io
from pypdf import PdfReader

def extract_text_from_file(filename: str, content_bytes: bytes) -> str:
    """
    Extracts plain text from uploaded file bytes (PDF or plain text).
    """
    lower_name = filename.lower()
    
    if lower_name.endswith('.pdf'):
        try:
            reader = PdfReader(io.BytesIO(content_bytes))
            text_parts = []
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_parts.append(extracted)
            return "\n\n".join(text_parts).strip()
        except Exception as e:
            raise ValueError(f"Error al leer el archivo PDF: {str(e)}")
            
    # Default to text decoding (UTF-8, Latin-1 fallback)
    for encoding in ['utf-8', 'latin-1', 'cp1252']:
        try:
            return content_bytes.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
            
    return content_bytes.decode('utf-8', errors='ignore').strip()
