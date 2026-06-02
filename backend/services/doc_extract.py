from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Dict, List

from pypdf import PdfReader
from pptx import Presentation


def _normalize_lines(lines: List[str], max_lines: int = 240) -> str:
    cleaned: List[str] = []
    for line in lines:
        s = (line or "").strip()
        if not s:
            continue
        cleaned.append(s)
        if len(cleaned) >= max_lines:
            break
    return "\n".join(cleaned)


def extract_text_from_pdf(file_bytes: bytes) -> Dict[str, object]:
    reader = PdfReader(BytesIO(file_bytes))
    lines: List[str] = []
    pages_detail: List[Dict[str, object]] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            continue
        lines.append(text)
        title = (text.splitlines()[0].strip() if text.splitlines() else f"第 {idx} 页")[:80]
        pages_detail.append({"page": idx, "title": title, "text": text.strip()})
    text = _normalize_lines(lines)
    first_line = text.splitlines()[0].strip() if text else ""
    return {
        "text": text,
        "title": first_line[:80],
        "pages": len(reader.pages),
        "pages_detail": pages_detail,
    }


def extract_text_from_pptx(file_bytes: bytes) -> Dict[str, object]:
    prs = Presentation(BytesIO(file_bytes))
    lines: List[str] = []
    pages_detail: List[Dict[str, object]] = []
    for idx, slide in enumerate(prs.slides, start=1):
        slide_lines: List[str] = []
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text = (shape.text or "").strip()
                if text:
                    lines.append(text)
                    slide_lines.append(text)
        if slide_lines:
            joined = "\n".join(slide_lines)
            title = slide_lines[0][:80]
            pages_detail.append({"page": idx, "title": title, "text": joined})
    text = _normalize_lines(lines)
    first_line = text.splitlines()[0].strip() if text else ""
    return {
        "text": text,
        "title": first_line[:80],
        "pages": len(prs.slides),
        "pages_detail": pages_detail,
    }


def extract_text_from_document(filename: str, file_bytes: bytes) -> Dict[str, object]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(file_bytes)
    if suffix == ".pptx":
        return extract_text_from_pptx(file_bytes)
    raise ValueError("仅支持 .pdf 或 .pptx 文件")
