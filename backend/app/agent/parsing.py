"""Turn uploaded files (PDF, Word, plain text) into text chunks the agent can cite."""

from __future__ import annotations

import io
import re

ALLOWED = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class ParseError(ValueError):
    pass


def extension(filename: str) -> str:
    m = re.search(r"\.[A-Za-z0-9]+$", filename or "")
    return m.group(0).lower() if m else ""


def extract_text(filename: str, data: bytes) -> str:
    ext = extension(filename)
    if ext == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(p.extract_text() or "") for p in reader.pages]
        except Exception as e:  # pypdf raises many types
            raise ParseError(f"could not read PDF: {e}") from e
        return "\n\n".join(pages)
    if ext == ".docx":
        import docx

        try:
            d = docx.Document(io.BytesIO(data))
        except Exception as e:
            raise ParseError(f"could not read Word file: {e}") from e
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    if ext in (".txt", ".md"):
        for enc in ("utf-8", "utf-16", "cp1251", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
    raise ParseError(f"unsupported file type: {ext or 'unknown'}")


def chunk_text(text: str, target: int = 1400, overlap: int = 150) -> list[str]:
    """Split on paragraph boundaries into ~target-character chunks."""
    text = re.sub(r"[ \t]+", " ", text)
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[A-Z0-9#•\-])", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        if len(p) > target * 1.5:  # very long paragraph: hard-split on sentences
            sentences = re.split(r"(?<=[.!?])\s+", p)
        else:
            sentences = [p]
        for s in sentences:
            if cur and len(cur) + len(s) + 1 > target:
                chunks.append(cur.strip())
                cur = cur[-overlap:] + " " + s if overlap else s
            else:
                cur = f"{cur}\n{s}" if cur else s
    if cur.strip():
        chunks.append(cur.strip())
    return [c for c in chunks if len(c) > 40]


def title_of(filename: str, text: str) -> str:
    for line in text.splitlines():
        line = line.strip(" #\t")
        if 8 <= len(line) <= 160:
            return line
    return filename
