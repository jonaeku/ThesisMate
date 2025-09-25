import json
import os
import re
from typing import List, Optional, Tuple, Dict, Iterable, Union
from src.models.models import OutlineSection, Paper, ConversationState, WritingStyleConfig, GuardrailsConfig, DraftPassage, ThesisOutline


def ensure_data_dir():
    """Create data directory if it doesn't exist"""
    os.makedirs("data", exist_ok=True)

def save_papers(papers: List[Paper], filename: str = "data/papers.json"):
    """Save papers to JSON file"""
    ensure_data_dir()
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump([paper.model_dump() for paper in papers], f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving papers: {e}")
        return False

def load_papers(filename: str = "data/papers.json") -> List[Paper]:
    """Load papers from JSON file"""
    if not os.path.exists(filename):
        return []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [Paper(**item) for item in data]
    except Exception as e:
        print(f"Error loading papers: {e}")
        return []

def save_conversation_state(state: ConversationState, filename: str = "data/conversation.json"):
    """Save conversation state so Topic Scout remembers the chat"""
    ensure_data_dir()
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(state.model_dump(), f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving conversation: {e}")
        return False

def load_conversation_state(filename: str = "data/conversation.json") -> Optional[ConversationState]:
    """Load conversation state so Topic Scout can continue the chat"""
    if not os.path.exists(filename):
        return ConversationState()  # Return empty state if no file
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return ConversationState(**data)
    except Exception as e:
        print(f"Error loading conversation: {e}")
        return ConversationState()

def export_bibtex(papers: List[Paper]) -> str:
    """Export papers to BibTeX format"""
    bibtex_entries = []
    for paper in papers:
        if paper.bibtex:
            bibtex_entries.append(paper.bibtex)
    
    return "\n\n".join(bibtex_entries)


# ----- Structure Agent -----

THESIS_OUTLINE_DIR = os.path.join("data", "thesis", "outline")

def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def _strip_leading_enumeration(text: str) -> str:
    """
    Entfernt führende Nummerierungen wie:
    - "1.0 ", "1.1 ", "2.3.4 ", optional gefolgt von :, -, . oder )
    - "Chapter 1: " etc.
    """
    t = (text or "").strip()
    # "Chapter 1: " / "Kapitel 1: "
    t = re.sub(r"^(?:chapter|kapitel)\s+\d+\s*[:.\-)\]]\s*", "", t, flags=re.IGNORECASE)
    # "1.2.3: " oder "1.2 " oder "1) " etc.
    t = re.sub(r"^\d+(?:\.\d+)*\s*[:.\-)\]]\s*", "", t)
    # "1.2 " (nur leer nach Nummern)
    t = re.sub(r"^\d+(?:\.\d+)*\s+", "", t)
    return _normalize_ws(t)

def ensure_thesis_outline_dir() -> None:
    """Create thesis outline directory if it doesn't exist."""
    os.makedirs(THESIS_OUTLINE_DIR, exist_ok=True)

def _slugify(text: str) -> str:
    """Filesystem-safe slug; toleriert Unicode, entfernt Sonderzeichen sinnvoll."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "thesis"


def outline_to_markdown(outline: OutlineSection, topic: Optional[str] = None) -> str:
    """
    Serialisiert OutlineSection → Markdown mit Nummerierung:
    - Hauptkapitel:  ## 1.0 Title
    - Unterkapitel:  ### 1.1 Subtitle
    Entfernt vorhandene Nummern aus den Titeln, um Duplikate zu verhindern.
    """
    lines: List[str] = []

    if topic:
        lines.append(f"# 🧭 Outline für: *{topic}*")
        lines.append("")

    chapters = outline.subsections or []
    for i, chapter in enumerate(chapters, 1):
        main_title = _strip_leading_enumeration(chapter.title) or f"Chapter {i}"
        lines.append(f"## {i}.0 {main_title}")

        for j, sub in enumerate((chapter.subsections or []), 1):
            sub_title = _strip_leading_enumeration(sub.title) or f"Section {i}.{j}"
            lines.append(f"### {i}.{j} {sub_title}")

        lines.append("")

    #lines.append("---")
    #lines.append("💡 *Hinweis: Kapitel können weiter ausformuliert oder an neue Research-Ergebnisse angepasst werden.*")

    md = "\n".join(lines).rstrip() + "\n"
    return md

# ganz unten neben outline_to_markdown hinzufügen
def outline_to_markdown_chat_compact(outline: OutlineSection, topic: Optional[str] = None) -> str:
    """
    Kompakte Darstellung für Chat:
    - Kapitel fett als normale Textzeile (keine # Headings)
    - Unterkapitel als einfache Zeilen mit Nummerierung
    """
    lines = []
    if topic:
        lines.append(f"🧭 **Outline für:** *{topic}*")
        lines.append("")

    chapters = outline.subsections or []
    for i, chapter in enumerate(chapters, 1):
        # führende Nummern aus Titel entfernen
        from .storage import _strip_leading_enumeration  # falls oben nicht im gleichen Modul
        main_title = _strip_leading_enumeration(chapter.title) or f"Chapter {i}"
        lines.append(f"**{i}.0 {main_title}**")
        for j, sub in enumerate((chapter.subsections or []), 1):
            sub_title = _strip_leading_enumeration(sub.title) or f"Section {i}.{j}"
            lines.append(f"{i}.{j} {sub_title}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"



def save_outline(
    outline: OutlineSection,
    topic: Optional[str] = None,
    base_dir: str = THESIS_OUTLINE_DIR,
    stem: Optional[str] = None,
) -> Dict[str, str]:
    ensure_thesis_outline_dir()
    if stem:
        base_name = _slugify(stem)
    elif topic:
        base_name = _slugify(topic)
    else:
        base_name = "thesis"

    json_path = os.path.join(base_dir, f"{base_name}.json")
    md_path = os.path.join(base_dir, f"{base_name}.md")

    # JSON speichern
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(outline.model_dump(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving outline JSON: {e}")

    # Markdown speichern (neu: mit Titel und Nummerierung)
    try:
        md = outline_to_markdown(outline, topic=topic)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)
    except Exception as e:
        print(f"Error saving outline Markdown: {e}")

    return {"json": json_path, "md": md_path}


def load_latest_outline(base_dir: str = THESIS_OUTLINE_DIR) -> Optional[OutlineSection]:
    if not os.path.exists(base_dir):
        return None
    try:
        files = [f for f in os.listdir(base_dir) if f.endswith(".json")]
        if not files:
            return None
        files.sort(reverse=True)  # timestamp vorne → lexikographisch = zeitlich
        latest = os.path.join(base_dir, files[0])
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)
            return OutlineSection(**data)
    except Exception as e:
        print(f"Error loading latest outline: {e}")
        return None

def load_outline_for_topic(topic: str, base_dir: str = THESIS_OUTLINE_DIR) -> Optional[OutlineSection]:
    """
    Lädt die neueste Outline-JSON, deren Dateiname auf den Topic-Slug passt.
    """
    if not topic:
        return load_latest_outline(base_dir)
    if not os.path.exists(base_dir):
        return None
    try:
        slug = _slugify(topic)
        files = [f for f in os.listdir(base_dir) if f.endswith(".json") and f.split("_", 1)[-1].startswith(slug)]
        if not files:
            # Fallback: beste Übereinstimmung (contains)
            files = [f for f in os.listdir(base_dir) if f.endswith(".json") and slug in f]
            if not files:
                return None
        files.sort(reverse=True)
        path = os.path.join(base_dir, files[0])
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return OutlineSection(**data)
    except Exception as e:
        print(f"Error loading outline for topic '{topic}': {e}")
        return None

# ----- Writing Agent -----

BASE_DIR = "data"
THESIS_DIR = os.path.join(BASE_DIR, "thesis")
CONFIG_DIR = os.path.join(THESIS_DIR, "config")
CHAPTER_DIR = os.path.join(THESIS_DIR, "chapter")
BIB_DIR = os.path.join(THESIS_DIR, "bib")
GUARDRAILS_DIR = os.path.join(THESIS_DIR, "guardrails")  

def _ensure_dirs():
    for d in [BASE_DIR, THESIS_DIR, CONFIG_DIR, CHAPTER_DIR, BIB_DIR, GUARDRAILS_DIR]:
        os.makedirs(d, exist_ok=True)

_slug_rx = re.compile(r"[^\w\s-]", flags=re.UNICODE)
def slugify(text: str) -> str:
    t = (text or "").strip().lower()
    t = _slug_rx.sub("", t)
    t = re.sub(r"[\s_-]+", "-", t)
    return re.sub(r"^-+|-+$", "", t) or "untitled"



# ---- Config: Style & Guardrails ----

def save_writing_style(style: WritingStyleConfig, filename: str = os.path.join(CONFIG_DIR, "writing_style.json")) -> str:
   _ensure_dirs()
   with open(filename, "w", encoding="utf-8") as f:
       json.dump(style.model_dump(), f, indent=2, ensure_ascii=False)
   return filename

def load_writing_style(filename: str = os.path.join(CONFIG_DIR, "writing_style.json")) -> Optional[WritingStyleConfig]:
   if not os.path.exists(filename):
       return None
   with open(filename, "r", encoding="utf-8") as f:
       data = json.load(f)
   return WritingStyleConfig(**data)

def save_guardrails(gr: GuardrailsConfig, filename: str = os.path.join(CONFIG_DIR, "guardrails.json")) -> str:
#    _ensure_dirs()
   with open(filename, "w", encoding="utf-8") as f:
       json.dump(gr.model_dump(), f, indent=2, ensure_ascii=False)
   return filename

def load_guardrails(filename: str = os.path.join(CONFIG_DIR, "guardrails.json")) -> Optional[GuardrailsConfig]:
   if not os.path.exists(filename):
       return None
   with open(filename, "r", encoding="utf-8") as f:
       data = json.load(f)
   return GuardrailsConfig(**data)

# ---- Save drafted passages into chapter folders ----

def make_chapter_dir_name(chapter_index: int, chapter_title: str) -> str:
    """Erzeugt '04_experimental-design-and-results-for-ai-in-healthcare'"""
    clean_title = _strip_leading_enumeration(chapter_title)     # <<< wichtig
    slug = _slugify(clean_title)
    return f"{chapter_index:02d}_{slug}"

def _section_file_name(ch_idx: int, sec_idx: Optional[int], title: Optional[str]) -> str:
    if sec_idx:
        base = f"{ch_idx}.{sec_idx}_{slugify(title or '') or 'section'}"
    else:
        base = f"{ch_idx}.0_{slugify(title or '') or 'chapter'}"
    return f"{base}.md"

def resolve_chapter_folder(outline: ThesisOutline, ch_index: int) -> str:
    _ensure_dirs()
    chapter_title = outline.chapters[ch_index-1].title if (outline and 1 <= ch_index <= len(outline.chapters)) else f"Chapter {ch_index}"
    folder = make_chapter_dir_name(chapter_index=ch_index, chapter_title=chapter_title)
    path = os.path.join(CHAPTER_DIR, folder)
    os.makedirs(path, exist_ok=True)
    return path

# src/utils/storage.py
from typing import Literal
import os, re

def save_passage(
    outline: ThesisOutline,
    passage: DraftPassage,
    merge_strategy: Literal["append","overwrite","version","revise"]="append"
) -> Dict[str, str]:
    folder = resolve_chapter_folder(outline, passage.chapter_index)
    fname = _section_file_name(passage.chapter_index, passage.section_index, passage.title)
    path = os.path.join(folder, fname)

    header = [
        f"<!-- chapter_index: {passage.chapter_index} -->",
        f"<!-- section_index: {passage.section_index or ''} -->",
        f"<!-- title: {passage.title or ''} -->",
        f"<!-- citations: {', '.join(passage.citations or [])} -->",
        "",
    ]
    new_block = passage.content_markdown.strip() + "\n"

    exists = os.path.exists(path)

    if merge_strategy == "overwrite" or not exists:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(header))
            f.write(new_block)
        return {"path": path, "folder": folder, "file": fname}

    if merge_strategy == "append":
        # Header nur beim ersten Mal
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n\n" + new_block)
        return {"path": path, "folder": folder, "file": fname}

    if merge_strategy == "version":
        base, ext = os.path.splitext(fname)
        k = 2
        while True:
            cand = os.path.join(folder, f"{base}_v{k}{ext}")
            if not os.path.exists(cand):
                with open(cand, "w", encoding="utf-8") as f:
                    f.write("\n".join(header))
                    f.write(new_block)
                return {"path": cand, "folder": folder, "file": os.path.basename(cand)}
            k += 1

    if merge_strategy == "revise":
        # sehr einfache „Merge“-Variante: bestehenden Text einlesen und beide Blöcke kombinieren
        with open(path, "r", encoding="utf-8") as f:
            old = f.read().strip()
        # Header beibehalten, nur Body ersetzen durch alten + neuen Absatz
        parts = old.split("-->\n", 3)  # Header beibehalten
        if len(parts) >= 2:
            header_text = old[:old.find(parts[-1])]
            body = old[len(header_text):].strip()
            merged = body + "\n\n" + new_block
            with open(path, "w", encoding="utf-8") as f:
                f.write(header_text)
                f.write(merged)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(header))
                f.write(new_block)
        return {"path": path, "folder": folder, "file": fname}
# Fallback
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n\n" + new_block)
    return {"path": path, "folder": folder, "file": fname}

# --- guardrails ---
_filename_rx = re.compile(r"[^A-Za-z0-9._-]+")
def _safe_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "upload.bin"
    # Pfadteile entfernen (Windows/macOS)
    name = os.path.basename(name)
    # Unerlaubte Zeichen ersetzen
    name = _filename_rx.sub("_", name)
    return name[:200] or "upload.bin"


def save_guardrail_files(
    files: Iterable[Union[Tuple[str, bytes], dict]],
    allowed_ext: Optional[List[str]] = None,
    max_mb: int = 25
) -> List[str]:
    """
    Speichert Dateien in data/thesis/guardrails.

    :param files: Iterable von (filename, content_bytes) ODER dicts {"name": str, "content": bytes}
    :param allowed_ext: z.B. ['.pdf', '.docx', '.md', '.txt'] oder None = alles
    :param max_mb: maximale Größe je Datei
    :return: Liste der Zielpfade
    """
    _ensure_dirs()

    saved_paths: List[str] = []
    max_bytes = max_mb * 1024 * 1024
    allowed = [e.lower() for e in (allowed_ext or [])]

    for item in files:
        # --- flexible Eingabe ---
        if isinstance(item, tuple):
            orig_name, blob = item
        elif isinstance(item, dict):
            orig_name = item.get("name")
            blob = item.get("content")
        else:
            # unbekanntes Format
            continue

        if not orig_name:
            continue

        # Bytes sicherstellen (optional Dateipfad akzeptieren)
        if blob is None:
            continue
        if not isinstance(blob, (bytes, bytearray)):
            if isinstance(blob, str) and os.path.exists(blob):
                with open(blob, "rb") as f:
                    blob = f.read()
            else:
                continue

        if len(blob) > max_bytes:
            raise ValueError(f"File '{orig_name}' exceeds size limit of {max_mb} MB")

        fname = _safe_filename(orig_name)
        ext = os.path.splitext(fname)[1].lower()
        if allowed and ext not in allowed:
            raise ValueError(f"Extension '{ext}' not allowed for '{orig_name}'")

        # Kollisionen vermeiden
        out_path = os.path.join(GUARDRAILS_DIR, fname)
        base, ext2 = os.path.splitext(out_path)
        idx = 1
        while os.path.exists(out_path):
            out_path = f"{base}__{idx}{ext2}"
            idx += 1

        with open(out_path, "wb") as f:
            f.write(blob)

        saved_paths.append(out_path)

    return saved_paths

# --- NEU: Auflisten (für UI/Debug) ---
def list_guardrail_files() -> List[str]:
    _ensure_dirs()
    try:
        return sorted(
            [os.path.join(GUARDRAILS_DIR, f) for f in os.listdir(GUARDRAILS_DIR)]
        )
    except FileNotFoundError:
        return []