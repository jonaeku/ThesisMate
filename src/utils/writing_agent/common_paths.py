from pathlib import Path

THESIS_DIR = Path("./thesis")
THESIS_MD_PATH = THESIS_DIR / "my_thesis.md"
STYLE_PATH = THESIS_DIR / "style.json"
BIB_PATH = THESIS_DIR / "references.bib"
GUARDRAILS_DIR = THESIS_DIR / "guardrails"

ALLOWED_EXTS = {".md", ".txt"}
MAX_BYTES = 2_000_000
