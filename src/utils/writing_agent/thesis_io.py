from pathlib import Path
from .common_paths import THESIS_MD_PATH

def save_paragraph_to_file(section_title: str, paragraph: str, path: Path = THESIS_MD_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# My Thesis\n\n", encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    heading = f"**{section_title}**"

    idx = next((i for i, l in enumerate(lines) if l.strip() == heading), None)
    if idx is None:
        block = ["", heading, f"{section_title} – user draft below.", "", paragraph.strip(), ""]
        path.write_text("\n".join(lines + block) + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        return

    insert_pos = min(idx + 2, len(lines))
    indent_desc = ""
    if idx + 1 < len(lines):
        d = lines[idx + 1]
        indent_desc = d[:len(d) - len(d.lstrip(" "))]
    para_block = ["", indent_desc + paragraph.strip(), ""]
    new_text = "\n".join(lines[:insert_pos] + para_block + lines[insert_pos:])
    path.write_text(new_text, encoding="utf-8")
