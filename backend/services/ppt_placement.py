from __future__ import annotations

from typing import Dict, List, Optional, Tuple


MARGIN = 0.03
MIN_IMAGE_WIDTH = 0.16
MIN_IMAGE_HEIGHT = 0.12


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _rect_area(rect: Dict[str, float]) -> float:
    return max(0.0, rect["width"]) * max(0.0, rect["height"])


def _rect_overlap_area(a: Dict[str, float], b: Dict[str, float]) -> float:
    ax2 = a["x"] + a["width"]
    ay2 = a["y"] + a["height"]
    bx2 = b["x"] + b["width"]
    by2 = b["y"] + b["height"]
    ix = max(0.0, min(ax2, bx2) - max(a["x"], b["x"]))
    iy = max(0.0, min(ay2, by2) - max(a["y"], b["y"]))
    return ix * iy


def _expand_rect(rect: Dict[str, float], pad: float) -> Dict[str, float]:
    x = _clamp01(rect["x"] - pad)
    y = _clamp01(rect["y"] - pad)
    x2 = _clamp01(rect["x"] + rect["width"] + pad)
    y2 = _clamp01(rect["y"] + rect["height"] + pad)
    return {"x": x, "y": y, "width": max(0.0, x2 - x), "height": max(0.0, y2 - y)}


def _normalize_block(block: Dict[str, object]) -> Optional[Dict[str, float]]:
    try:
        x = float(block.get("x", 0))
        y = float(block.get("y", 0))
        width = float(block.get("width", 0))
        height = float(block.get("height", 0))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return {
        "x": _clamp01(x),
        "y": _clamp01(y),
        "width": _clamp01(width),
        "height": _clamp01(height),
        "text": str(block.get("text", "") or ""),
    }


def parse_aspect_ratio(value: str) -> float:
    raw = (value or "16:9").strip()
    if ":" in raw:
        left, right = raw.split(":", 1)
        try:
            w = float(left)
            h = float(right)
            if w > 0 and h > 0:
                return w / h
        except ValueError:
            pass
    return 16.0 / 9.0


def fit_rect_in_zone(
    zone: Dict[str, float],
    image_aspect: float,
    slide_aspect: float = 16.0 / 9.0,
) -> Optional[Dict[str, float]]:
    ratio_wh = image_aspect / max(slide_aspect, 1e-6)
    zone_w = max(zone["width"], MIN_IMAGE_WIDTH)
    zone_h = max(zone["height"], MIN_IMAGE_HEIGHT)

    height = zone_h
    width = height * ratio_wh
    if width > zone_w:
        width = zone_w
        height = width / ratio_wh

    width = max(MIN_IMAGE_WIDTH, min(width, zone_w))
    height = max(MIN_IMAGE_HEIGHT, min(height, zone_h))
    if width / max(height, 1e-6) > ratio_wh:
        width = height * ratio_wh
    else:
        height = width / ratio_wh

    x = zone["x"] + (zone["width"] - width) / 2.0
    y = zone["y"] + (zone["height"] - height) / 2.0
    rect = {
        "x": _clamp01(x),
        "y": _clamp01(y),
        "width": _clamp01(width),
        "height": _clamp01(height),
    }
    if rect["x"] + rect["width"] > 1.0:
        rect["x"] = max(0.0, 1.0 - rect["width"])
    if rect["y"] + rect["height"] > 1.0:
        rect["y"] = max(0.0, 1.0 - rect["height"])
    return rect


def _candidate_zones(text_blocks: List[Dict[str, float]]) -> List[Dict[str, float]]:
    zones = [
        {"x": 0.52, "y": 0.38, "width": 0.42, "height": 0.52},
        {"x": 0.55, "y": 0.22, "width": 0.38, "height": 0.68},
        {"x": 0.10, "y": 0.55, "width": 0.80, "height": 0.35},
        {"x": 0.15, "y": 0.30, "width": 0.70, "height": 0.55},
    ]
    if not text_blocks:
        return zones

    max_bottom = max(block["y"] + block["height"] for block in text_blocks)
    right_x = max(block["x"] + block["width"] for block in text_blocks)
    bottom_zone_y = _clamp01(max_bottom + 0.04)
    bottom_zone_h = max(0.14, 0.94 - bottom_zone_y)
    zones.insert(
        0,
        {
            "x": 0.50,
            "y": bottom_zone_y,
            "width": 0.42,
            "height": bottom_zone_h,
        },
    )
    if right_x < 0.72:
        zones.insert(
            1,
            {
                "x": _clamp01(right_x + 0.03),
                "y": 0.24,
                "width": max(0.18, 0.94 - right_x),
                "height": 0.62,
            },
        )
    return zones


def compute_recommended_placement(
    text_blocks: List[Dict[str, object]],
    *,
    aspect_ratio: str = "16:9",
    slide_aspect: float = 16.0 / 9.0,
) -> Tuple[Dict[str, float], List[Dict[str, object]]]:
    normalized_blocks: List[Dict[str, float]] = []
    occupied_for_ui: List[Dict[str, object]] = []
    for block in text_blocks or []:
        parsed = _normalize_block(block)
        if not parsed:
            continue
        normalized_blocks.append(parsed)
        occupied_for_ui.append(
            {
                "text": parsed.get("text", ""),
                "x": parsed["x"],
                "y": parsed["y"],
                "width": parsed["width"],
                "height": parsed["height"],
            }
        )

    occupied = [_expand_rect(block, 0.02) for block in normalized_blocks]
    image_aspect = parse_aspect_ratio(aspect_ratio)
    best_rect: Optional[Dict[str, float]] = None
    best_score = -1.0

    for zone in _candidate_zones(normalized_blocks):
        candidate = fit_rect_in_zone(zone, image_aspect, slide_aspect)
        if not candidate:
            continue
        overlap = sum(_rect_overlap_area(candidate, occ) for occ in occupied)
        score = _rect_area(candidate) - overlap * 2.5
        if score > best_score:
            best_score = score
            best_rect = candidate

    if not best_rect:
        best_rect = fit_rect_in_zone(
            {"x": 0.55, "y": 0.40, "width": 0.38, "height": 0.48},
            image_aspect,
            slide_aspect,
        )
    if not best_rect:
        width = 0.34
        best_rect = {
            "x": 0.58,
            "y": 0.42,
            "width": width,
            "height": width * slide_aspect / image_aspect,
        }

    return best_rect, occupied_for_ui
