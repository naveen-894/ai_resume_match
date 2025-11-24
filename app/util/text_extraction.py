import textract
from PyPDF2 import PdfReader
from fastapi import UploadFile

async def extract_text_from_file(file: UploadFile) -> str:
    """
    Extract text from uploaded file (.pdf, .docx, .txt)
    """
    filename = file.filename.lower()
    if filename.endswith(".pdf"):
        reader = PdfReader(file.file)
        return " ".join(page.extract_text() or "" for page in reader.pages)
    elif filename.endswith((".doc", ".docx")):
        text = textract.process(file.file)
        return text.decode("utf-8", errors="ignore")
    elif filename.endswith(".txt"):
        return (await file.read()).decode("utf-8", errors="ignore")
    else:
        return ""