# src/utils/style_store.py
from __future__ import annotations
import os, json

BASE_DIR = "data"
THESIS_DIR = os.path.join(BASE_DIR, "thesis")
CONFIG_DIR = os.path.join(THESIS_DIR, "config")
STYLE_FILE = os.path.join(CONFIG_DIR, "style.json")

_DEFAULT_STYLE = {
    "style_guide": "Academic, concise, precise terminology, formal tone, active voice where appropriate, hedging when evidence is limited.",
    "citation_style": "APA"
}

def _ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def ensure_style_file() -> dict:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(STYLE_FILE):
        with open(STYLE_FILE, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_STYLE, f, indent=2, ensure_ascii=False)
        return dict(_DEFAULT_STYLE)
    with open(STYLE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def get_style() -> dict:
    return ensure_style_file()

def update_style(changes: dict) -> dict:
    data = ensure_style_file()
    data.update({k: v for k, v in (changes or {}).items() if v is not None})
    with open(STYLE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data

def save_style(style: dict) -> str:
    _ensure_dirs()
    with open(STYLE_FILE, "w", encoding="utf-8") as f:
        json.dump(style, f, indent=2, ensure_ascii=False)
    return STYLE_FILE