import json, re
from typing import Optional
from langchain_core.messages import AIMessage
from .common_paths import STYLE_PATH

def load_style(default_guide: str, default_citation: str) -> tuple[str, str]:
    if STYLE_PATH.exists():
        data = json.loads(STYLE_PATH.read_text(encoding="utf-8"))
        return data.get("style_guide", default_guide), data.get("citation_style", default_citation)
    return default_guide, default_citation

def save_style(style_guide: str, citation_style: str) -> None:
    STYLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STYLE_PATH.write_text(
        json.dumps({"style_guide": style_guide.strip(), "citation_style": citation_style}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def handle_style_command(agent, txt: str) -> Optional[AIMessage]:
    """
    Prüft, ob txt ein Style-Kommando ist.
    Ruft bei Bedarf agent.set_citation_style / set_style_guide / learn_style_from_sample.
    Gibt eine AIMessage bei Treffer zurück, sonst None.
    """
    # show style
    if re.match(r"^\s*show\s+style\s*$", txt, flags=re.IGNORECASE):
        return AIMessage(content=f"Style: {agent.citation_style}\nStyle guide:\n{agent.style_guide}")

    # style: APA|MLA|Chicago
    m_style = re.match(r"^\s*style\s*:\s*(APA|MLA|Chicago)\s*$", txt, flags=re.IGNORECASE)
    if m_style:
        agent.set_citation_style(m_style.group(1).upper())
        return AIMessage(content=f"Zitierstil gespeichert: {agent.citation_style}")

    # style_guide: <regeln>
    m_sg = re.match(r"^\s*style_guide\s*:\s*(.+)$", txt, flags=re.IGNORECASE | re.DOTALL)
    if m_sg:
        agent.set_style_guide(m_sg.group(1).strip())
        return AIMessage(content="Style-Guide gespeichert.")

    # learn style: <beispieltext>
    m_ls = re.match(r"^\s*learn\s*style\s*:\s*(.+)$", txt, flags=re.IGNORECASE | re.DOTALL)
    if m_ls:
        agent.learn_style_from_sample(m_ls.group(1).strip())
        return AIMessage(content="Style aus Beispiel übernommen und gespeichert.")

    return None