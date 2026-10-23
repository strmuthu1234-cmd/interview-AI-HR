"""Secure validation of uploaded resume files (extension, size, magic bytes, structure)."""
import io
import zipfile

from django.conf import settings

ALLOWED = {"pdf", "docx"}


class FileRejected(Exception):
    pass


def validate_resume_file(uploaded):
    """Return (file_type, bytes). Raises FileRejected with a user-facing reason."""
    name = (uploaded.name or "").strip()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise FileRejected("Unsupported file type. Only PDF and DOCX resumes are accepted.")
    max_bytes = settings.MAX_RESUME_FILE_MB * 1024 * 1024
    if uploaded.size == 0:
        raise FileRejected("The file is empty.")
    if uploaded.size > max_bytes:
        raise FileRejected(f"File is larger than {settings.MAX_RESUME_FILE_MB} MB.")
    uploaded.seek(0)
    data = uploaded.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise FileRejected(f"File is larger than {settings.MAX_RESUME_FILE_MB} MB.")

    if ext == "pdf":
        if not data.startswith(b"%PDF-"):
            raise FileRejected("File content is not a valid PDF (extension does not match content).")
        if b"/JavaScript" in data or b"/JS " in data or b"/Launch" in data:
            raise FileRejected("PDF contains active content (JavaScript/launch actions) and was rejected.")
    else:
        if not data.startswith(b"PK"):
            raise FileRejected("File content is not a valid DOCX (extension does not match content).")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
                if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                    raise FileRejected("File is not a valid Word (.docx) document.")
                if any(n.endswith("vbaProject.bin") for n in names):
                    raise FileRejected("Document contains macros and was rejected.")
                total = sum(i.file_size for i in zf.infolist())
                if total > 100 * 1024 * 1024:  # zip-bomb guard
                    raise FileRejected("Document expands to an unreasonable size and was rejected.")
        except zipfile.BadZipFile:
            raise FileRejected("File is corrupted or not a valid DOCX.")
    return ext, data
