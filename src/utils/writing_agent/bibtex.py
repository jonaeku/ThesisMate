import re
from .common_paths import BIB_PATH

def _entries() -> list[dict]:
    if not BIB_PATH.exists():
        return []
    txt = BIB_PATH.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"@[\w]+\{([^,]+),([\s\S]*?)\n\}", txt):
        body = m.group(2)
        def f(name: str) -> str:
            fm = re.search(rf"{name}\s*=\s*[{{\"]([^}}\"]+)[}}\"]", body, flags=re.IGNORECASE)
            return fm.group(1).strip() if fm else ""
        out.append({"author": f("author"), "year": f("year"), "title": f("title")})
    return out

def select_cites(citation_style: str, limit: int = 2) -> list[str]:
    cites = []
    for e in _entries():
        first = (e["author"].split(" and ")[0].split(",")[0] or "Unknown")
        year = e["year"] or "n.d."
        if citation_style.upper() == "APA": cites.append(f"({first}, {year})")
        elif citation_style.upper() == "MLA": cites.append(f"({first} {year})")
        else: cites.append(f"[{first} {year}]")
        if len(cites) >= limit: break
    return cites
