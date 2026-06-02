from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

import numpy as np
from PIL import Image

from backend.config import PREVIEW_DIR


PREVIEW_ROOT = Path(PREVIEW_DIR).resolve()
PREVIEW_URL_PREFIX = "/previews/"


def resolve_preview_path(preview_url: str) -> Path:
    path = unquote(urlsplit(preview_url).path)
    if not path.startswith(PREVIEW_URL_PREFIX):
        raise ValueError("仅允许识别平台生成的预览图片")
    relative = path[len(PREVIEW_URL_PREFIX) :]
    candidate = (PREVIEW_ROOT / relative).resolve()
    if candidate != PREVIEW_ROOT and PREVIEW_ROOT not in candidate.parents:
        raise ValueError("预览图片路径无效")
    if not candidate.is_file():
        raise ValueError("预览图片不存在")
    return candidate


def crop_preview_region(
    preview_url: str,
    x: float,
    y: float,
    width: float,
    height: float,
) -> Image.Image:
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
        raise ValueError("框选区域必须位于页面范围内")

    with Image.open(resolve_preview_path(preview_url)) as source:
        image = source.convert("RGB")
    left = max(0, min(image.width - 1, round(x * image.width)))
    top = max(0, min(image.height - 1, round(y * image.height)))
    right = max(left + 1, min(image.width, round((x + width) * image.width)))
    bottom = max(top + 1, min(image.height, round((y + height) * image.height)))
    return image.crop((left, top, right, bottom))


@lru_cache(maxsize=1)
def _ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise RuntimeError("OCR 依赖未安装，请安装 rapidocr-onnxruntime") from exc
    return RapidOCR()


def recognize_region(
    preview_url: str,
    x: float,
    y: float,
    width: float,
    height: float,
) -> str:
    image = crop_preview_region(preview_url, x, y, width, height)
    result, _ = _ocr_engine()(np.asarray(image))
    lines = [
        {
            "text": str(item[1]).strip(),
            "left": min(float(point[0]) for point in item[0]),
            "top": min(float(point[1]) for point in item[0]),
            "bottom": max(float(point[1]) for point in item[0]),
        }
        for item in (result or [])
        if len(item) > 1 and item[0] and str(item[1]).strip()
    ]
    return _join_ocr_lines(lines)


def _same_visual_row(left: dict[str, float | str], right: dict[str, float | str]) -> bool:
    left_top = float(left["top"])
    left_bottom = float(left["bottom"])
    right_top = float(right["top"])
    right_bottom = float(right["bottom"])
    overlap = min(left_bottom, right_bottom) - max(left_top, right_top)
    min_height = min(left_bottom - left_top, right_bottom - right_top)
    return overlap > max(1.0, min_height * 0.35)


def _join_row_fragments(fragments: list[dict[str, float | str]]) -> dict[str, float | str]:
    ordered = sorted(fragments, key=lambda item: float(item.get("left", 0)))
    text = ""
    for fragment in ordered:
        cleaned = str(fragment["text"]).strip()
        if not cleaned:
            continue
        separator = " " if text and cleaned[:1].isascii() and cleaned[:1].isalnum() and text[-1:] not in ("/", "_", "-") else ""
        text += separator + cleaned
    return {
        "text": text,
        "top": min(float(item["top"]) for item in ordered),
        "bottom": max(float(item["bottom"]) for item in ordered),
    }


def _visual_rows(lines: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    rows: list[list[dict[str, float | str]]] = []
    for line in sorted(lines, key=lambda item: (float(item["top"]), float(item.get("left", 0)))):
        row = next((candidate for candidate in rows if any(_same_visual_row(item, line) for item in candidate)), None)
        if row is None:
            rows.append([line])
        else:
            row.append(line)
    return sorted((_join_row_fragments(row) for row in rows), key=lambda item: float(item["top"]))


def _join_ocr_lines(lines: list[dict[str, float | str]]) -> str:
    paragraphs: list[str] = []
    current = ""
    previous_bottom: float | None = None
    previous_height: float | None = None
    for line in _visual_rows(lines):
        cleaned = str(line["text"]).strip()
        if not cleaned:
            continue
        top = float(line["top"])
        bottom = float(line["bottom"])
        height = max(1.0, bottom - top)
        has_paragraph_gap = (
            previous_bottom is not None
            and previous_height is not None
            and top - previous_bottom > max(previous_height, height) * 0.7
        )
        if has_paragraph_gap and current:
            paragraphs.append(current)
            current = ""
        if not current:
            current = cleaned
            if current.endswith(("。", "！", "？", "；", ".", "!", "?", ";")):
                paragraphs.append(current)
                current = ""
        else:
            separator = " " if cleaned[:1].isascii() and cleaned[:1].isalnum() and current[-1:] not in ("/", "_", "-") else ""
            current += separator + cleaned
            if current.endswith(("。", "！", "？", "；", ".", "!", "?", ";")):
                paragraphs.append(current)
                current = ""
        previous_bottom = bottom
        previous_height = height
    if current:
        paragraphs.append(current)
    return "\n".join(paragraphs)
