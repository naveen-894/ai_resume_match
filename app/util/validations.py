import os
from fastapi import UploadFile, HTTPException

MAX_RESUME_SIZE_MB = 2
MAX_JD_SIZE_MB = 1
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt"}


def validate_file(file: UploadFile, file_type: str):
    """
    Validate uploaded JD or Resume file.
    """
    ext = file.filename.split(".")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type for {file_type}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    file_size = 0
    if hasattr(file.file, "seek") and hasattr(file.file, "tell"):
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)
    size_mb = file_size / (1024 * 1024)

    max_limit = MAX_RESUME_SIZE_MB if file_type == "resume" else MAX_JD_SIZE_MB
    if size_mb > max_limit:
        raise HTTPException(
            status_code=400,
            detail=f"{file_type.capitalize()} file too large (max {max_limit} MB)"
        )


def clean_text(text: str) -> str:
    """
    Clean extracted text — remove extra spaces, special chars, etc.
    """
    text = text.replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    return text
