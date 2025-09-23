import re
from typing import Optional, Tuple, List
from langchain_core.messages import BaseMessage, HumanMessage

def parse_writing_input(text: str) -> Tuple[Optional[str], Optional[str], Optional[List[str]]]:
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    if not lines: return None, None, None
    m = re.match(r"^\s*(\d+(?:\.\d+)*)\s+(.+)$", lines[0])
    section_title = lines[0].strip() if not m else f"{m.group(1)} {m.group(2).strip()}"
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    km = re.match(r"^keywords\s*:\s*(.+)$", body, flags=re.IGNORECASE)
    if km:
        kws = [k.strip() for k in km.group(1).split(",") if k.strip()]
        return section_title, None, kws
    return section_title, (body or None), None

def scan_style_command(messages: list[BaseMessage]) -> Optional[str]:
    for msg in reversed(messages[-5:]):
        if isinstance(msg, HumanMessage):
            m = re.search(r"style\s*:\s*(APA|MLA|Chicago)", msg.content, flags=re.IGNORECASE)
            if m: return m.group(1).upper()
    return None
