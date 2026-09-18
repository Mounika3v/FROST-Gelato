from __future__ import annotations
from pathlib import Path
import re
from functools import lru_cache

from src.catalog import all_products, normalize

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "data" / "frost_catalog.pdf"


@lru_cache(maxsize=1)
def load_pdf_text() -> str:
    if not PDF_PATH.exists():
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(PDF_PATH))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        return ""


def retrieve_pdf(query: str, limit: int = 5) -> str:
    """Hybrid lexical retrieval over the FROST PDF, cached for the session.

    Product-name matches receive a strong boost; ingredient/category terms are
    also considered. This keeps RAG local and cheap while giving Gemini focused
    source passages instead of dumping the whole PDF into every request.
    """
    text = load_pdf_text()
    if not text:
        return ""
    chunks = [c.strip() for c in re.split(r"\n\s*\n|(?=Code\s*:)", text) if c.strip()]
    query_norm = normalize(query)
    tokens = {t for t in re.findall(r"[a-z0-9]+", query_norm) if len(t) >= 3}
    products = all_products()
    scored = []
    for chunk in chunks:
        words = set(re.findall(r"[a-z0-9]+", chunk.lower()))
        score = len(tokens & words)
        chunk_norm = normalize(chunk)
        for product in products:
            product_name = normalize(product["Product"])
            if product_name and product_name in query_norm and product_name in chunk_norm:
                score += 1000
                break
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return "\n\n".join(c for _, c in scored[:limit])
