import os, shutil, re
from pathlib import Path
from .common_paths import GUARDRAILS_DIR, ALLOWED_EXTS, MAX_BYTES
GUARDRAILS_DIR.mkdir(parents=True, exist_ok=True)

def validate_upload(path_str: str) -> Path:
    s = path_str.strip().strip('"').strip("'")
    s = os.path.expanduser(s)
    p = Path(s)
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    if not p.exists() or not p.is_file():
        raise ValueError(f"File not found: {p}")
    if p.suffix.lower() not in ALLOWED_EXTS:
        raise ValueError("Unsupported file type")
    if p.stat().st_size > MAX_BYTES:
        raise ValueError("File too large")
    return p

def ingest_guardrail_file(src: Path) -> Path:
    dst = GUARDRAILS_DIR / src.name
    shutil.copy(src, dst)
    return dst

def compose_guardrails_text(limit_chars: int = 8000) -> str:
    texts = []
    for f in sorted(GUARDRAILS_DIR.glob("*")):
        if f.suffix.lower() in ALLOWED_EXTS and f.stat().st_size <= MAX_BYTES:
            texts.append(f.read_text(encoding="utf-8").strip())
    return "\n\n".join(t for t in texts if t)[:limit_chars]

def is_upload_command(text: str) -> str | None:
    txt = text.strip()
    m = re.search(r"upload\s*:\s*(.+)$", txt, flags=re.IGNORECASE|re.MULTILINE)
    if m: return m.group(1).strip()
    if re.match(r"^[A-Za-z]:\\[^:*?\"<>|\r\n]+$", txt): return txt
    if re.match(r"^(?:/|\./|\.\\)[^\r\n]+$", txt):       return txt
    return None
