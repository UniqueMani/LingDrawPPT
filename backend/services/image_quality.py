from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import httpx
import numpy as np
from PIL import Image

from backend.config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    IMAGE_EVAL_PASS_SCORE,
    IMAGE_EVAL_VL_MODEL,
    IMAGE_EVAL_USE_VL,
)
from backend.services.ocr_region import _ocr_engine, _join_ocr_lines, resolve_preview_path

logger = logging.getLogger(__name__)

DIMENSION_WEIGHTS: Dict[str, Tuple[str, float]] = {
    "semantic_alignment": ("语义一致性", 0.25),
    "text_fidelity": ("文字真实性", 0.25),
    "visual_clarity": ("视觉清晰度", 0.15),
    "style_consistency": ("风格一致性", 0.15),
    "slide_consistency": ("配色一致性", 0.10),
    "layout_quality": ("布局质量", 0.10),
}

# 封面/分隔页：图片不负责精确文字，降低 text_fidelity 权重
PAGE_TYPE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "cover": {
        "semantic_alignment": 0.30,
        "text_fidelity": 0.05,
        "visual_clarity": 0.20,
        "style_consistency": 0.25,
        "slide_consistency": 0.10,
        "layout_quality": 0.10,
    },
    "section-divider": {
        "semantic_alignment": 0.28,
        "text_fidelity": 0.07,
        "visual_clarity": 0.18,
        "style_consistency": 0.27,
        "slide_consistency": 0.10,
        "layout_quality": 0.10,
    },
    # 架构/流程等信息图：视觉语义为主，图中标签文字允许轻微 OCR 偏差
    "diagram": {
        "semantic_alignment": 0.32,
        "text_fidelity": 0.12,
        "visual_clarity": 0.18,
        "style_consistency": 0.18,
        "slide_consistency": 0.10,
        "layout_quality": 0.10,
    },
    "content": dict((k, v[1]) for k, v in DIMENSION_WEIGHTS.items()),
}

DIAGRAM_HINTS = (
    "架构",
    "流程",
    "示意图",
    "流程图",
    "拓扑",
    "pipeline",
    "framework",
    "architecture",
    "flowchart",
    "信息图",
)

COVER_HINTS = ("封面", "报告人", "学号", "汇报人", "中期报告", "答辩", "学院", "专业")

PERSON_PATTERNS = (
    re.compile(r"报告人[:：]?\s*([\u4e00-\u9fff]{2,4})"),
    re.compile(r"姓名[:：]?\s*([\u4e00-\u9fff]{2,4})"),
    re.compile(r"汇报人[:：]?\s*([\u4e00-\u9fff]{2,4})"),
)
ID_RE = re.compile(r"\d{6,}")
NAME_MATCH_THRESHOLD = 0.92
ID_MATCH_THRESHOLD = 0.98

TEXT_FIDELITY_SKIP = frozenset(
    {
        "系统",
        "架构",
        "流程",
        "方案",
        "介绍",
        "概述",
        "说明",
        "内容",
        "背景",
        "总结",
        "分析",
        "页面",
        "章节",
        "报告",
        "研究",
        "方法",
        "实现",
        "设计",
    }
)

TEXT_ROLE_LABELS = {
    "data_chart": "数据图",
    "diagram": "流程/架构图",
    "cover_text": "封面/标题页",
    "decorative": "普通配图",
}

META_TEXT_PATTERNS = (
    re.compile(r"\b(?:expected_intent|expected_chartType|intent|chartType)\s*[:=][^\n；;。]*", re.I),
    re.compile(r"\b(?:comparison_grouped|comparison_bar|proportion_pie|trend_line|process_flow|hierarchy_tree|relation_sankey|data_table)\b", re.I),
    re.compile(r"至少\s*\d+\s*个?\s*series", re.I),
    re.compile(r"不应生成\s*[A-Za-z0-9_/-]+", re.I),
    re.compile(r"生成提示[:：].*$", re.I | re.S),
    re.compile(r"风格[:：].*$", re.I | re.S),
)

DATA_CHART_HINTS = (
    "图表",
    "数据",
    "指标",
    "趋势",
    "对比",
    "比较",
    "营收",
    "收入",
    "利润",
    "毛利",
    "毛利率",
    "转化率",
    "增长率",
    "占比",
    "份额",
    "同比",
    "环比",
    "series",
    "chart",
    "bar",
    "line",
    "pie",
)

DECORATIVE_HINTS = (
    "配图",
    "插画",
    "场景",
    "背景",
    "概念",
    "人物",
    "办公室",
    "城市",
    "科技感",
    "无文字",
    "不要文字",
    "no text",
    "without text",
)

METRIC_TERMS = (
    "营收",
    "收入",
    "销售额",
    "利润",
    "毛利率",
    "毛利",
    "转化率",
    "增长率",
    "达成率",
    "占比",
    "份额",
    "成本",
    "用户",
    "活跃用户",
    "金额",
)

WATERMARK_TERMS = ("watermark", "stock", "shutterstock", "getty", "logo", "copyright", "sample")

OCR_META_PATTERNS = (
    re.compile(r"\b(?:intent|chartType|topic|body|data_description|expected_intent|expected_chartType)\s*[:=]", re.I),
    re.compile(r"\b(?:comparison_grouped|comparison_bar|proportion_pie|trend_line|process_flow|hierarchy_tree|relation_sankey|data_table)\b", re.I),
)


@dataclass
class DimensionScore:
    key: str
    label: str
    score: float
    weight: float
    detail: str
    max_score: float = 100.0
    deducted: float = 0.0
    deduction_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(self.score, 1),
            "maxScore": round(self.max_score, 1),
            "deducted": round(self.deducted, 1),
            "weight": self.weight,
            "detail": self.detail,
            "deductionReason": self.deduction_reason,
        }


@dataclass
class ImageQualityReport:
    passed: bool
    total_score: float
    dimensions: List[DimensionScore]
    feedback: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "totalScore": round(self.total_score, 1),
            "passThreshold": IMAGE_EVAL_PASS_SCORE,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "feedback": self.feedback,
        }


POSITIVE_VL_HINTS = (
    "完全符合",
    "符合",
    "简洁",
    "清晰",
    "和谐",
    "专业",
    "扁平",
    "统一",
    "美观",
    "直观",
    "协调",
    "准确",
    "没有无关",
    "无无关",
    "无乱码",
    "流程清晰",
)
NEGATIVE_VL_HINTS = ("不符合", "混乱", "写实", "照片风", "动漫", "赛博", "杂乱")
NEGATIVE_VL_PHRASES = ("无关文字", "乱码", "水印")


def _vl_negated_before(text: str, index: int) -> bool:
    prefix = text[max(0, index - 12) : index]
    if any(marker in prefix for marker in ("无", "没有", "避免", "不含", "未出现", "不出现", "未含")):
        return True
    avoid_idx = text.rfind("避免", 0, index)
    if avoid_idx >= 0 and "。" not in text[avoid_idx:index]:
        return True
    return False


def _reason_is_positive_vl(reason: str) -> bool:
    text = reason or ""
    positives = sum(1 for hint in POSITIVE_VL_HINTS if hint in text)

    for hint in NEGATIVE_VL_HINTS:
        if hint in text:
            return False

    for phrase in NEGATIVE_VL_PHRASES:
        start = 0
        while True:
            idx = text.find(phrase, start)
            if idx < 0:
                break
            if not _vl_negated_before(text, idx):
                return False
            start = idx + len(phrase)

    return positives >= 2


def _parse_vl_score_raw(raw: object) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    fraction = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", text)
    if fraction:
        return float(fraction.group(1)) * 10.0
    number = re.search(r"(\d+(?:\.\d+)?)", text)
    if number:
        return float(number.group(1))
    return None


def _pick_style_score_field(data: Dict[str, object]) -> object:
    for key in ("style_score", "score", "styleScore"):
        if key in data and data[key] is not None:
            return data[key]
    return 0


def _pick_semantic_score_field(data: Dict[str, object]) -> object:
    for key in ("semantic_score", "score", "semanticScore"):
        if key in data and data[key] is not None:
            return data[key]
    return 0


def _pick_vl_score_field(data: Dict[str, object]) -> object:
    """Deprecated alias kept for tests; prefer _pick_style_score_field / _pick_semantic_score_field."""
    return _pick_style_score_field(data)


def _normalize_vl_score(raw: object, *, reason: str = "") -> float:
    """VL 分数统一到 0~100，并处理 0.09/9/90 等常见格式错误。"""
    parsed = _parse_vl_score_raw(raw)
    if parsed is None or parsed <= 0:
        return 78.0 if _reason_is_positive_vl(reason) else 0.0

    score = parsed
    if score <= 1.0:
        scaled = score * 100.0
        # 0.05~0.15 多为 0.9 少写一位（0.09→9 分 Bug）
        if 0.05 <= score <= 0.15:
            scaled = 90.0
        elif scaled < 30.0 and _reason_is_positive_vl(reason):
            scaled = max(scaled, 78.0)
        return max(0.0, min(100.0, scaled))

    if score <= 10.0:
        return max(0.0, min(100.0, score * 10.0))

    normalized = max(0.0, min(100.0, score))
    if normalized < 40.0 and _reason_is_positive_vl(reason):
        return max(normalized, 78.0)
    return normalized


def _reconcile_vl_score(raw: object, reason: str, *, label: str) -> Tuple[float, str, object]:
    normalized = _normalize_vl_score(raw, reason=reason)
    detail = reason[:200]
    raw_display = raw if raw is not None else "missing"
    if normalized >= 40.0 or not _reason_is_positive_vl(reason):
        logger.info("VL %s raw=%s normalized=%.1f", label, raw_display, normalized)
        return normalized, detail, raw_display

    corrected = max(normalized, 78.0)
    logger.warning(
        "VL %s score/reason mismatch raw=%s normalized=%.1f corrected=%.1f",
        label,
        raw_display,
        normalized,
        corrected,
    )
    detail += f"（VL 数值 {raw_display} 与评语不一致，已校正为 {corrected:.0f} 分）"
    return corrected, detail, raw_display


VL_STYLE_RUBRIC = (
    "style_score 必须是 0~100 的整数，禁止使用 0~1 或 1~10 刻度。"
    "90~100=高度符合扁平矢量信息图；70~89=基本符合；50~69=部分符合；50 以下=明显不符合。"
    "分数必须与 reason 一致：评语正面时 score 不得低于 70。"
)


def _infer_slide_type(slide_type: Optional[str], source_text: str, prompt: str) -> str:
    normalized = (slide_type or "content").strip().lower()
    if normalized in PAGE_TYPE_WEIGHTS and normalized not in {"content"}:
        return normalized
    text = f"{source_text}\n{prompt}"
    if sum(1 for hint in COVER_HINTS if hint in text) >= 2:
        return "cover"
    if "目录" in text and len(text) < 120:
        return "section-divider"
    if _is_diagram_heavy(source_text, prompt):
        return "diagram"
    return "content"


def _is_diagram_heavy(source_text: str, prompt: str) -> bool:
    text = f"{source_text}\n{prompt}".lower()
    if len((source_text or "").strip()) < 40:
        return False
    return any(hint in text for hint in DIAGRAM_HINTS)


def _resolve_dimension_weights(slide_type: Optional[str], source_text: str, prompt: str) -> Dict[str, float]:
    page_type = _infer_slide_type(slide_type, source_text, prompt)
    return dict(PAGE_TYPE_WEIGHTS.get(page_type, PAGE_TYPE_WEIGHTS["content"]))


def _semantic_brief_for_vl(source_text: str, prompt: str) -> str:
    """供 VL 判断主题/布局/主体，不包含姓名学号等应由 OCR 负责的文字。"""
    lines: List[str] = []
    for line in (source_text or "").split("\n"):
        cleaned = line.strip()
        if not cleaned:
            continue
        if any(k in cleaned for k in ("报告人", "学号", "姓名", "汇报人")):
            continue
        if ID_RE.search(cleaned):
            continue
        lines.append(cleaned)
    brief = "\n".join(lines[:12]).strip() or (prompt or "")[:400]
    tokens = [t for t in _token_set(brief) if t not in TEXT_FIDELITY_SKIP]
    if tokens:
        return "主题关键词：" + "、".join(list(tokens)[:12])
    return brief[:400] or "PPT 信息图配图"


def _token_set(text: str) -> set[str]:
    cleaned = (text or "").lower()
    tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}", cleaned))
    tokens.update(w for w in re.findall(r"[a-z0-9_./-]{3,}", cleaned) if not w.isdigit())
    return tokens


def _ocr_on_image(image: Image.Image) -> str:
    text, _stats = _ocr_on_image_with_stats(image)
    return text


def _ocr_on_image_with_stats(image: Image.Image) -> Tuple[str, Dict[str, Any]]:
    lines = []
    confidences: List[float] = []
    vertical_boxes = 0
    narrow_text_boxes = 0
    try:
        result, _ = _ocr_engine()(np.asarray(image.convert("RGB")))
        for item in result or []:
            if len(item) > 1 and item[0] and str(item[1]).strip():
                box = item[0]
                text = str(item[1]).strip()
                left = min(float(p[0]) for p in box)
                top = min(float(p[1]) for p in box)
                right = max(float(p[0]) for p in box)
                bottom = max(float(p[1]) for p in box)
                width = max(1.0, right - left)
                height = max(1.0, bottom - top)
                if len(item) > 2:
                    try:
                        confidences.append(float(item[2]))
                    except Exception:
                        pass
                if re.search(r"[\u4e00-\u9fff]", text):
                    if height > width * 1.45 and len(text) >= 2:
                        vertical_boxes += 1
                    if width / max(1, len(text)) < 12 and height > 18:
                        narrow_text_boxes += 1
                lines.append(
                    {
                        "text": text,
                        "left": left,
                        "top": top,
                        "bottom": bottom,
                    }
                )
    except Exception as exc:
        logger.warning("OCR evaluate failed: %s", exc)
        return "", {"confidenceAvg": None, "lowConfidenceCount": 0, "verticalBoxes": 0, "narrowTextBoxes": 0}
    confidence_avg = sum(confidences) / len(confidences) if confidences else None
    low_confidence_count = sum(1 for c in confidences if c < 0.72)
    return _join_ocr_lines(lines).strip(), {
        "confidenceAvg": confidence_avg,
        "lowConfidenceCount": low_confidence_count,
        "verticalBoxes": vertical_boxes,
        "narrowTextBoxes": narrow_text_boxes,
    }


def _clarity_score(image: Image.Image) -> Tuple[float, str]:
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    if gray.size < 4:
        return 60.0, "图像过小，清晰度采用中性分"

    height, width = gray.shape
    grad_x = np.abs(np.diff(gray, axis=1))
    grad_y = np.abs(np.diff(gray, axis=0))
    edge_p95 = float(np.percentile(np.concatenate([grad_x.ravel(), grad_y.ravel()]), 95))
    contrast = float(gray.std())

    lap = np.zeros_like(gray)
    if height > 2 and width > 2:
        lap[1:-1, 1:-1] = (
            -4 * gray[1:-1, 1:-1]
            + gray[:-2, 1:-1]
            + gray[2:, 1:-1]
            + gray[1:-1, :-2]
            + gray[1:-1, 2:]
        )
    lap_var = float(lap.var())

    resolution_bonus = 8.0 if width >= 900 and height >= 500 else 0.0
    edge_part = min(32.0, edge_p95 * 1.8)
    contrast_part = min(18.0, contrast * 0.45)
    lap_part = min(12.0, lap_var * 0.018)
    score = max(0.0, min(100.0, 50.0 + resolution_bonus + edge_part + contrast_part + lap_part))

    if score >= 78:
        detail = "主体边缘、文字/图形轮廓和整体对比度清晰"
    elif score >= 62:
        detail = "清晰度基本可用，局部边缘或对比度仍可增强"
    else:
        detail = "局部边缘弱或整体对比度偏低，可能影响识别"
    return score, detail


def _style_score(image: Image.Image, prompt: str) -> Tuple[float, str]:
    prompt_l = (prompt or "").lower()
    style_hits = sum(
        1
        for kw in ("扁平", "矢量", "信息图", "infographic", "flat", "vector", "ppt", "幻灯片")
        if kw in prompt_l
    )
    prompt_part = min(45.0, style_hits * 12.0)
    score = min(100.0, prompt_part + 50.0)
    return score, "Prompt 风格约束启发式分（启用 VL 后会进一步看图评估）"


def _normalize_compare_text(text: str) -> str:
    cleaned = (text or "").lower()
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"[，,。．.；;：:、!?！？\-—_·\"'“”‘’（）()\\[\\]{}]", "", cleaned)
    return cleaned


def _similarity_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _best_substring_match(needle: str, haystack: str) -> float:
    if not needle or not haystack:
        return 0.0
    if needle in haystack:
        return 1.0
    best = 0.0
    size = len(needle)
    for idx in range(max(1, len(haystack) - size + 1)):
        chunk = haystack[idx : idx + size]
        best = max(best, _similarity_ratio(needle, chunk))
        if best >= 0.98:
            break
    return best


def _extract_person_and_id(source_text: str, prompt: str) -> Tuple[Optional[str], Optional[str]]:
    text = "\n".join(part for part in (source_text or "", prompt or "") if part)
    person: Optional[str] = None
    for pattern in PERSON_PATTERNS:
        match = pattern.search(text)
        if match:
            person = match.group(1).strip()
            break
    ids = ID_RE.findall(text)
    student_id = max(ids, key=len) if ids else None
    return person, student_id


def _extract_text_anchors(source_text: str, prompt: str) -> List[str]:
    text = "\n".join(part for part in (source_text or "", prompt or "") if part)
    anchors: List[str] = []
    for line in text.split("\n"):
        cleaned = line.strip()
        if not cleaned:
            continue
        if re.search(r"[：:]", cleaned):
            value = re.split(r"[：:]", cleaned, maxsplit=1)[-1].strip()
            if 2 <= len(value) <= 24:
                anchors.append(value)
        if 4 <= len(cleaned) <= 36:
            anchors.append(cleaned)
        for token in re.findall(r"[\u4e00-\u9fff]{3,}", cleaned):
            if token not in TEXT_FIDELITY_SKIP:
                anchors.append(token)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{1,}", text):
        if len(token) >= 2:
            anchors.append(token)
    for token in re.findall(r"\d{3,}", text):
        anchors.append(token)
    return list(dict.fromkeys(anchors))[:24]


def _important_keywords(source_text: str, prompt: str) -> set[str]:
    text = "\n".join(part for part in (source_text or "", prompt or "") if part)
    keywords: set[str] = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{1,}", text):
        keywords.add(token.lower())
    for token in re.findall(r"\d{3,}", text):
        keywords.add(token)
    for line in text.split("\n"):
        for part in re.split(r"[，,。．.；;：:、\s()（）\[\]{}]+", line):
            cleaned = part.strip()
            if 2 <= len(cleaned) <= 16 and re.search(r"[\u4e00-\u9fff]", cleaned):
                if cleaned not in TEXT_FIDELITY_SKIP:
                    keywords.add(cleaned)
            for zh in re.findall(r"[\u4e00-\u9fff]{2,6}", cleaned):
                if zh not in TEXT_FIDELITY_SKIP:
                    keywords.add(zh)
    return {k for k in keywords if len(k) >= 2}


def _keyword_coverage(source_text: str, prompt: str, ocr_norm: str) -> Tuple[float, int, int]:
    tokens = _important_keywords(source_text, prompt)
    if not tokens:
        return 0.85, 0, 0
    hits = 0
    for token in tokens:
        norm = _normalize_compare_text(token)
        if norm and _best_substring_match(norm, ocr_norm) >= 0.72:
            hits += 1
    return hits / len(tokens), hits, len(tokens)


def _is_displayable_keyword(token: str) -> bool:
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{2,}", token):
        return True
    if re.fullmatch(r"[\u4e00-\u9fff]{4,8}", token) and token not in TEXT_FIDELITY_SKIP:
        return True
    if re.fullmatch(r"\d{3,}", token):
        return True
    return False


def _missing_keywords(source_text: str, prompt: str, ocr_norm: str, limit: int = 5) -> List[str]:
    missing: List[str] = []
    seen: set[str] = set()
    candidates: List[str] = []
    for anchor in _extract_text_anchors(source_text, prompt):
        if len(anchor) > 16:
            continue
        candidates.append(anchor)
    for token in sorted(_important_keywords(source_text, prompt), key=len, reverse=True):
        if _is_displayable_keyword(token):
            candidates.append(token)
    for token in candidates:
        norm = _normalize_compare_text(token)
        if not norm or _best_substring_match(norm, ocr_norm) >= 0.72:
            continue
        if not _is_displayable_keyword(token) and not re.search(r"[A-Za-z]", token):
            continue
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        missing.append(token)
        if len(missing) >= limit:
            break
    return missing


def _strip_meta_text(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"\b(?:topic|body|data_description)\s*[:：=]\s*", " ", cleaned, flags=re.I)
    for pattern in META_TEXT_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"用于自动化和人工回归测试", " ", cleaned)
    cleaned = re.sub(r"EXPECTED[:：].*$", " ", cleaned, flags=re.I | re.M)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _semantic_text_for_fidelity(source_text: str, prompt: str) -> str:
    parts = [source_text or ""]
    prompt_text = prompt or ""
    content_match = re.search(r"主题与内容[:：]\s*(.+?)(?:风格[:：]|附加风格[:：]|$)", prompt_text, re.S)
    if content_match:
        parts.append(content_match.group(1))
    elif not source_text:
        parts.append(prompt_text[:500])
    return _strip_meta_text("\n".join(parts))


def _detect_text_role(source_text: str, prompt: str, slide_type: Optional[str]) -> str:
    page_type = _infer_slide_type(slide_type, source_text, prompt)
    text = f"{source_text}\n{prompt}".lower()
    if page_type in {"cover", "section-divider"} or any(hint in text for hint in COVER_HINTS):
        return "cover_text"
    data_hits = sum(1 for hint in DATA_CHART_HINTS if hint.lower() in text)
    if data_hits >= 2 or re.search(r"[A-Za-z]产品|[\u4e00-\u9fffA-Za-z0-9]+[：:]\s*-?\d", text):
        return "data_chart"
    if any(hint.lower() in text for hint in DIAGRAM_HINTS):
        return "diagram"
    if any(hint.lower() in text for hint in DECORATIVE_HINTS):
        return "decorative"
    if page_type == "diagram":
        return "diagram"
    return "decorative"


def _dedupe_keep_order(items: List[str], limit: int = 12) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = str(item).strip()
        if not cleaned:
            continue
        key = _normalize_compare_text(cleaned).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def _extract_title_anchor(text: str) -> List[str]:
    candidates: List[str] = []
    for pattern in (
        r"(?:topic|标题|主题)\s*[:：]\s*([^\n；;。]{4,28})",
        r"主题与内容[:：]\s*([^\n；;。]{4,28})",
    ):
        for match in re.finditer(pattern, text, re.I):
            candidates.append(_strip_meta_text(match.group(1)))
    first = _strip_meta_text(re.split(r"[。；;\n]", text or "", maxsplit=1)[0])
    first = re.sub(r"^(?:标题|主题)\s*[:：]\s*", "", first).strip()
    if re.search(r"->|=>|→", first):
        first = ""
    if 4 <= len(first) <= 28:
        candidates.append(first)
    return _dedupe_keep_order(candidates, 2)


def _extract_data_chart_anchors(source_text: str, prompt: str) -> Dict[str, List[str]]:
    text = _semantic_text_for_fidelity(source_text, prompt)
    title = _extract_title_anchor(f"{source_text}\n{prompt}")
    entities: List[str] = []
    metrics: List[str] = []
    values: List[str] = []

    entities.extend(re.findall(r"[A-Za-z]\s*产品", text))
    entities.extend(re.findall(r"[\u4e00-\u9fffA-Za-z0-9_-]{1,12}(?:产品|部门|地区|渠道|平台)", text))
    product_list = re.search(r"产品\s*=\s*([A-Za-z0-9,，、\s]+)", f"{source_text}\n{prompt}")
    if product_list:
        entities.extend(f"{p.strip()}产品" for p in re.split(r"[,，、\s]+", product_list.group(1)) if p.strip())

    for term in METRIC_TERMS:
        if term in text:
            metrics.append(term)
    metric_list = re.search(r"(?:指标|metrics?)\s*[:：=]\s*([^\n；;。]+)", f"{source_text}\n{prompt}", re.I)
    if metric_list:
        for part in re.split(r"[,，、/;\s]+", metric_list.group(1)):
            cleaned = part.strip()
            if not (2 <= len(cleaned) <= 8) or "=" in cleaned:
                continue
            if cleaned in METRIC_TERMS or re.search(r"率|额|量|数|收入|营收|利润|成本", cleaned):
                metrics.append(cleaned)

    for raw in re.findall(r"-?\d+(?:\.\d+)?\s*%?", text):
        token = raw.strip()
        if token and not re.fullmatch(r"(?:19|20)\d{2}", token):
            values.append(token)
    return {
        "title": _dedupe_keep_order(title, 2),
        "entities": _dedupe_keep_order(entities, 8),
        "metrics": _dedupe_keep_order(metrics, 8),
        "values": _dedupe_keep_order(values, 12),
    }


def _extract_diagram_anchors(source_text: str, prompt: str) -> Dict[str, List[str]]:
    text = _semantic_text_for_fidelity(source_text, prompt)
    nodes: List[str] = []
    if re.search(r"->|=>|→", text):
        flow_text = re.sub(r"^.*?(?:流程|步骤|节点)\s*[:：]", "", text, count=1)
        nodes.extend(p.strip() for p in re.split(r"->|=>|→", flow_text) if 2 <= len(p.strip()) <= 16)
    step_match = re.search(r"(?:流程|步骤|节点|模块)\s*[:：]\s*([^\n。]+)", text)
    if step_match:
        nodes.extend(
            p.strip()
            for p in re.split(r"[,，、;；\s]+", step_match.group(1))
            if 2 <= len(p.strip()) <= 16 and not re.fullmatch(r"[-=→>]+", p.strip())
        )
    nodes.extend(
        t for t in re.findall(r"[\u4e00-\u9fff]{2,8}", text)
        if t not in TEXT_FIDELITY_SKIP and not t.startswith(("流程", "步骤"))
    )
    return {
        "title": _extract_title_anchor(text),
        "nodes": _dedupe_keep_order(nodes, 10),
    }


def _match_items(items: List[str], ocr_norm: str, threshold: float = 0.70) -> Tuple[int, int, List[str]]:
    if not items:
        return 0, 0, []
    hits = 0
    missing: List[str] = []
    for item in items:
        norm = _normalize_compare_text(item)
        matched = bool(norm and _best_substring_match(norm, ocr_norm) >= threshold)
        if matched:
            hits += 1
        else:
            missing.append(item)
    return hits, len(items), missing


def _group_score(items: List[str], ocr_norm: str, points: float, threshold: float = 0.70) -> Tuple[float, str]:
    hits, total, missing = _match_items(items, ocr_norm, threshold)
    if total == 0:
        return points * 0.5, "无明确期望项，采用中性分"
    score = points * hits / total
    if missing:
        return score, f"匹配 {hits}/{total}，未识别：{'、'.join(missing[:4])}"
    return score, f"匹配 {hits}/{total}"


def _visible_text_penalty(ocr: str) -> Tuple[float, List[str]]:
    issues: List[str] = []
    suspicious = len(re.findall(r"[\ufffd□■◆◇]", ocr))
    watermark_hits = [term for term in WATERMARK_TERMS if term.lower() in (ocr or "").lower()]
    meta_hits = [pattern.pattern for pattern in OCR_META_PATTERNS if pattern.search(ocr or "")]
    lines = [line.strip() for line in (ocr or "").split("\n") if line.strip()]
    duplicate_ratio = 1.0 - (len(set(lines)) / len(lines)) if len(lines) > 1 else 0.0
    short_cjk_lines = [
        line
        for line in lines
        if re.search(r"[\u4e00-\u9fff]", line) and len(_normalize_compare_text(line)) <= 2
    ]
    avg_line_len = sum(len(_normalize_compare_text(line)) for line in lines) / max(1, len(lines))
    fragmented_text = len(short_cjk_lines) >= 3 or (len(lines) >= 8 and avg_line_len <= 4)

    penalty = (
        suspicious * 10.0
        + len(watermark_hits) * 18.0
        + len(meta_hits) * 16.0
        + duplicate_ratio * 12.0
    )
    if fragmented_text:
        penalty += min(30.0, 8.0 + len(short_cjk_lines) * 4.0)
    if suspicious:
        issues.append("存在不可读字符")
    if watermark_hits:
        issues.append("存在疑似水印/品牌字样")
    if meta_hits:
        issues.append("出现不应渲染的调试/元信息文字")
    if duplicate_ratio > 0.25:
        issues.append("存在重复文本")
    if fragmented_text:
        issues.append("文字可读性较差，存在竖排/断裂/过多短行")
    return min(45.0, penalty), issues


def _score_data_chart_text(ocr: str, source_text: str, prompt: str) -> Tuple[float, str]:
    ocr_norm = _normalize_compare_text(ocr)
    anchors = _extract_data_chart_anchors(source_text, prompt)
    title_score, title_detail = _group_score(anchors["title"], ocr_norm, 15.0, 0.68)
    entity_score, entity_detail = _group_score(anchors["entities"], ocr_norm, 20.0, 0.68)
    metric_score, metric_detail = _group_score(anchors["metrics"], ocr_norm, 20.0, 0.68)
    value_score, value_detail = _group_score(anchors["values"], ocr_norm, 25.0, 0.80)
    penalty, issues = _visible_text_penalty(ocr)
    clean_score = max(0.0, 20.0 - penalty)
    score = max(0.0, min(100.0, title_score + entity_score + metric_score + value_score + clean_score))

    expected_total = sum(len(anchors[k]) for k in ("title", "entities", "metrics", "values"))
    if expected_total >= 4 and not issues:
        matched = sum(_match_items(anchors[k], ocr_norm, 0.68 if k != "values" else 0.80)[0] for k in anchors)
        if matched / expected_total >= 0.55:
            score = max(score, 72.0)
    if issues:
        score = min(score, 92.0)

    details = [
        f"文字角色：{TEXT_ROLE_LABELS['data_chart']}",
        f"标题：{title_detail}",
        f"实体：{entity_detail}",
        f"指标：{metric_detail}",
        f"数值：{value_detail}",
        "无明显乱码/水印" if not issues else "；".join(issues),
    ]
    return score, "；".join(details) + "。"


def _score_diagram_text(ocr: str, source_text: str, prompt: str) -> Tuple[float, str]:
    ocr_norm = _normalize_compare_text(ocr)
    anchors = _extract_diagram_anchors(source_text, prompt)
    title_score, title_detail = _group_score(anchors["title"], ocr_norm, 20.0, 0.68)
    node_score, node_detail = _group_score(anchors["nodes"], ocr_norm, 35.0, 0.68)
    penalty, issues = _visible_text_penalty(ocr)
    clean_score = max(0.0, 25.0 - penalty)
    unrelated_score = 20.0 if not issues else 12.0
    score = max(0.0, min(100.0, title_score + node_score + clean_score + unrelated_score))
    if not issues and anchors["nodes"]:
        node_hits, node_total, _ = _match_items(anchors["nodes"], ocr_norm, 0.68)
        if node_total and node_hits / node_total >= 0.5:
            score = max(score, 70.0)
    details = [
        f"文字角色：{TEXT_ROLE_LABELS['diagram']}",
        f"标题：{title_detail}",
        f"核心节点：{node_detail}",
        "无明显乱码/无关文字" if not issues else "；".join(issues),
    ]
    return score, "；".join(details) + "。"


def _score_decorative_text(ocr: str, source_text: str, prompt: str) -> Tuple[float, str]:
    if not ocr.strip():
        return 96.0, f"文字角色：{TEXT_ROLE_LABELS['decorative']}；未检测到文字，该类配图不要求出现文字。"
    penalty, issues = _visible_text_penalty(ocr)
    ocr_norm = _normalize_compare_text(ocr)
    semantic_text = _semantic_text_for_fidelity(source_text, prompt)
    source_tokens = [t for t in _token_set(semantic_text) if t not in TEXT_FIDELITY_SKIP]
    hits = 0
    for token in source_tokens[:12]:
        if _best_substring_match(_normalize_compare_text(token), ocr_norm) >= 0.70:
            hits += 1
    conflict_penalty = 0.0
    if len(ocr_norm) > 20 and source_tokens and hits == 0:
        conflict_penalty = 18.0
        issues.append("出现与主题无明显关联的文字")
    score = max(0.0, min(100.0, 92.0 - penalty - conflict_penalty))
    detail = "；".join(issues) if issues else "无明显乱码、水印或主题冲突文字"
    return score, f"文字角色：{TEXT_ROLE_LABELS['decorative']}；{detail}。"


def _score_cover_text(ocr: str, source_text: str, prompt: str) -> Tuple[float, str]:
    if not ocr.strip():
        return 88.0, f"文字角色：{TEXT_ROLE_LABELS['cover_text']}；未检测到文字，封面精确文字建议由 PPT 文本层渲染。"
    ocr_norm = _normalize_compare_text(ocr)
    title_score, title_detail = _group_score(_extract_title_anchor(f"{source_text}\n{prompt}"), ocr_norm, 30.0, 0.70)
    person_name, student_id = _extract_person_and_id(source_text, prompt)
    person_score = 30.0
    id_score = 25.0
    notes: List[str] = []
    if person_name:
        person_match = _best_substring_match(_normalize_compare_text(person_name), ocr_norm)
        person_score = 30.0 if person_match >= NAME_MATCH_THRESHOLD else 8.0
        if person_match < NAME_MATCH_THRESHOLD:
            notes.append(f"姓名/报告人匹配不足（期望 {person_name}）")
    if student_id:
        id_match = 1.0 if student_id in ocr else _best_substring_match(student_id, ocr_norm)
        id_score = 25.0 if id_match >= ID_MATCH_THRESHOLD else 6.0
        if id_match < ID_MATCH_THRESHOLD:
            notes.append(f"编号/学号匹配不足（期望 {student_id}）")
    penalty, issues = _visible_text_penalty(ocr)
    clean_score = max(0.0, 15.0 - penalty)
    score = max(0.0, min(100.0, title_score + person_score + id_score + clean_score))
    details = [f"文字角色：{TEXT_ROLE_LABELS['cover_text']}", f"标题：{title_detail}"]
    details.extend(notes)
    details.append("无明显乱码/多余文字" if not issues else "；".join(issues))
    return score, "；".join(details) + "。"


def _build_text_fidelity_detail(
    *,
    score: float,
    coverage: float,
    cov_hits: int,
    cov_total: int,
    diagram: bool,
    entity_notes: List[str],
    suspicious: int,
    duplicate_ratio: float,
    digit_errors: int,
    source_text: str,
    prompt: str,
    ocr_norm: str,
) -> str:
    pct = int(round(coverage * 100)) if cov_total else 0
    parts: List[str] = []

    if score >= 78:
        parts.append("图中文字与幻灯片正文基本一致，核心术语均可识别")
    elif score >= 55:
        parts.append("图中文字大体可读，但存在少量错字、漏字或语序差异")
    else:
        parts.append("图中文字与正文匹配度偏低，存在错字、断句混乱或疑似幻觉文字")

    if cov_total:
        parts.append(f"关键词识别 {cov_hits}/{cov_total}（{pct}%）")

    if cov_total and coverage < 0.80:
        missing = _missing_keywords(source_text, prompt, ocr_norm)
        if missing:
            sample = "、".join(missing[:4])
            suffix = " 等" if len(missing) > 4 else ""
            parts.append(f"尚未完整识别的术语包括：{sample}{suffix}")

    issues: List[str] = []
    if suspicious > 0:
        issues.append("不可读字符")
    if duplicate_ratio > 0.2:
        issues.append("重复文本")
    if digit_errors > 0:
        issues.append("数字或编号不匹配")
    if issues:
        parts.append("主要问题：" + "、".join(issues))

    if entity_notes:
        parts.extend(entity_notes)

    if diagram and not entity_notes:
        parts.append("信息图页以术语覆盖为主，不要求与正文逐字一致")

    return "；".join(parts) + "。"


def _text_fidelity_score(
    ocr_text: str,
    source_text: str,
    prompt: str,
    *,
    slide_type: Optional[str] = None,
) -> Tuple[float, str]:
    ocr = (ocr_text or "").strip()
    role = _detect_text_role(source_text, prompt, slide_type)
    if role == "data_chart":
        if not ocr:
            return 62.0, f"文字角色：{TEXT_ROLE_LABELS[role]}；未检测到 OCR 文字，数据图应包含核心标题、标签或数值，采用保守分。"
        return _score_data_chart_text(ocr, source_text, prompt)
    if role == "diagram":
        if not ocr:
            return 82.0, f"文字角色：{TEXT_ROLE_LABELS[role]}；未检测到文字，按无文字示意图处理，不要求覆盖正文。"
        return _score_diagram_text(ocr, source_text, prompt)
    if role == "cover_text":
        return _score_cover_text(ocr, source_text, prompt)
    return _score_decorative_text(ocr, source_text, prompt)


def _ocr_readability_score(ocr_text: str, image: Image.Image) -> Tuple[float, str]:
    text = (ocr_text or "").strip()
    if not text:
        return 100.0, "无文字区域，OCR 可读性不适用"

    clarity_score, clarity_detail = _clarity_score(image)
    suspicious = len(re.findall(r"[\ufffd□■◆◇]", text))
    line_count = text.count("\n") + 1
    penalty = suspicious * 8.0 + max(0, line_count - 10) * 2.0
    score = max(0.0, min(100.0, clarity_score * 0.85 + 10.0 - penalty))
    detail = f"{clarity_detail}；检测到 {line_count} 行 OCR 文本"
    return score, detail


def _ocr_stats_readability_penalty(stats: Dict[str, Any]) -> Tuple[float, List[str]]:
    penalty = 0.0
    issues: List[str] = []
    confidence_avg = stats.get("confidenceAvg")
    low_confidence_count = int(stats.get("lowConfidenceCount") or 0)
    vertical_boxes = int(stats.get("verticalBoxes") or 0)
    narrow_text_boxes = int(stats.get("narrowTextBoxes") or 0)

    if isinstance(confidence_avg, (int, float)) and confidence_avg < 0.82:
        penalty += min(22.0, (0.82 - float(confidence_avg)) * 80.0)
        issues.append(f"OCR 平均置信度偏低（{float(confidence_avg):.0%}）")
    if low_confidence_count:
        penalty += min(18.0, low_confidence_count * 4.0)
        issues.append("存在低置信度文字识别框")
    if vertical_boxes:
        penalty += min(24.0, vertical_boxes * 8.0)
        issues.append("存在疑似竖排或窄高文字，影响阅读")
    if narrow_text_boxes >= 2:
        penalty += min(18.0, narrow_text_boxes * 4.0)
        issues.append("部分文字框过窄，可能字号过小或笔画粘连")
    return min(45.0, penalty), issues


def _layout_quality_score(image: Image.Image, ocr_text: str) -> Tuple[float, str]:
    arr = np.asarray(image.convert("L"), dtype=np.float32)
    height, width = arr.shape
    if height < 8 or width < 8:
        return 70.0, "图像过小，布局采用中性分"

    mid_y, mid_x = height // 2, width // 2
    quads = (
        arr[:mid_y, :mid_x],
        arr[:mid_y, mid_x:],
        arr[mid_y:, :mid_x],
        arr[mid_y:, mid_x:],
    )
    quad_means = [float(q.mean()) for q in quads if q.size > 0]
    balance = 100.0 - min(35.0, float(np.std(quad_means)) * 3.0)

    center = arr[height // 4 : 3 * height // 4, width // 4 : 3 * width // 4]
    edge_x = np.abs(np.diff(arr, axis=1)).mean() if width > 1 else 0.0
    center_x = np.abs(np.diff(center, axis=1)).mean() if center.shape[1] > 1 else 0.0
    focus_ratio = float(center_x / max(edge_x, 1e-6))
    focus_score = min(100.0, 50.0 + focus_ratio * 22.0)

    whitespace = float((arr > 220.0).mean())
    whitespace_bonus = min(12.0, whitespace * 30.0)

    text_len = len((ocr_text or "").strip())
    density_penalty = min(6.0, max(0.0, text_len - 260) * 0.015)

    score = max(
        0.0,
        min(100.0, balance * 0.40 + focus_score * 0.40 + whitespace_bonus + 8.0 - density_penalty),
    )
    if score >= 78:
        detail = "四象限亮度较均衡，主体区域聚焦，留白合理"
    elif score >= 62:
        detail = "布局基本可用，局部重心或留白仍可优化"
    else:
        detail = "布局重心失衡或信息堆叠感较强"
    return score, detail


def _semantic_heuristic(source_text: str, prompt: str) -> Tuple[float, str]:
    src = _token_set(source_text)
    if not src:
        return 72.0, "源文本较短，采用中性语义分"
    prompt_tokens = _token_set(prompt)
    overlap = len(src & prompt_tokens) / len(src)
    score = min(100.0, 35.0 + overlap * 65.0)
    if overlap >= 0.45:
        detail = f"Prompt 覆盖约 {int(overlap * 100)}% 关键词义"
    elif overlap >= 0.2:
        detail = "语义覆盖一般，建议检查是否偏离正文主题"
    else:
        detail = "语义覆盖偏低，配图可能未体现正文要点"
    return score, detail


def _color_vec(image: Image.Image) -> np.ndarray:
    arr = np.asarray(image.convert("RGB").resize((64, 64)), dtype=np.float32) / 255.0
    mean = arr.mean(axis=(0, 1))
    std = arr.std(axis=(0, 1))
    return np.concatenate([mean, std])


def _slide_consistency_score(generated: Image.Image, preview_path: Optional[str]) -> Tuple[float, str]:
    if not preview_path:
        return 78.0, "未提供幻灯片预览，页面一致性采用中性分"
    try:
        with Image.open(resolve_preview_path(preview_path)) as slide_img:
            slide_rgb = slide_img.convert("RGB")
    except Exception as exc:
        return 70.0, f"无法读取预览页：{exc}"

    gen_vec = _color_vec(generated)
    slide_vec = _color_vec(slide_rgb)
    dist = float(np.linalg.norm(gen_vec - slide_vec))
    score = max(0.0, min(100.0, 100.0 - dist * 120.0))
    if score >= 72:
        detail = "配图色调与当前页预览较为协调（仅评估配色）"
    elif score >= 55:
        detail = "配图色调与当前页预览有一定偏差（仅评估配色）"
    else:
        detail = "配图色调与当前页预览差异较大（仅评估配色）"
    return score, detail


def _extract_json_object(raw: str) -> Optional[Dict[str, object]]:
    start = raw.find("{")
    if start < 0:
        return None
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(raw[start:])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def _vl_style_boost(image_url: str, prompt: str) -> Optional[Tuple[float, str, object]]:
    if not IMAGE_EVAL_USE_VL or not DASHSCOPE_API_KEY:
        return None
    url = f"{DASHSCOPE_BASE_URL.rstrip('/')}/api/v1/services/aigc/multimodal-generation/generation"
    instruction = (
        "你是 PPT 配图风格评审。评估配图是否符合 flat vector infographic / 扁平矢量信息图风格。"
        f"{VL_STYLE_RUBRIC}"
        "只输出 JSON：{\"style_score\": number, \"reason\": string}\n"
        f"生成提示：{prompt[:500]}"
    )
    body = {
        "model": IMAGE_EVAL_VL_MODEL,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": image_url},
                        {"text": instruction},
                    ],
                }
            ]
        },
    }
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=body)
        payload = resp.json()
        if resp.status_code != 200:
            return None
        text_parts: List[str] = []
        output = payload.get("output") or {}
        for choice in output.get("choices") or []:
            message = choice.get("message") or {}
            for item in message.get("content") or []:
                if isinstance(item, dict) and item.get("text"):
                    text_parts.append(str(item["text"]))
        data = _extract_json_object("\n".join(text_parts))
        if not data:
            return None
        raw_score = _pick_style_score_field(data)
        reason = str(data.get("reason") or "多模态风格评估")
        score, reason, raw_display = _reconcile_vl_score(raw_score, reason, label="style")
        return score, reason, raw_display
    except Exception as exc:
        logger.info("VL style eval skipped: %s", exc)
        return None


async def _vl_semantic_boost(image_url: str, source_text: str, prompt: str) -> Optional[Tuple[float, str]]:
    if not IMAGE_EVAL_USE_VL or not DASHSCOPE_API_KEY:
        return None
    url = f"{DASHSCOPE_BASE_URL.rstrip('/')}/api/v1/services/aigc/multimodal-generation/generation"
    instruction = (
        "你是 PPT 配图质量评审。只根据配图画面评估：主题是否相关、主体/图标是否合适、"
        "信息图布局是否清晰。**不要**评估图中文字是否正确、是否乱码、姓名学号是否准确（由 OCR 负责）。"
        "给出 0~100 的 semantic_score 整数（100=最佳），禁止使用 0~1 或 1~10。"
        "90~100=高度符合主题；70~89=基本符合；50 以下=明显偏离。分数须与 reason 一致。"
        "只输出 JSON：{\"semantic_score\": number, \"reason\": string}\n"
        f"应表达的主题要点：{_semantic_brief_for_vl(source_text, prompt)}"
    )
    body = {
        "model": IMAGE_EVAL_VL_MODEL,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": image_url},
                        {"text": instruction},
                    ],
                }
            ]
        },
    }
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=body)
        payload = resp.json()
        if resp.status_code != 200:
            return None
        text_parts: List[str] = []
        output = payload.get("output") or {}
        for choice in output.get("choices") or []:
            message = choice.get("message") or {}
            for item in message.get("content") or []:
                if isinstance(item, dict) and item.get("text"):
                    text_parts.append(str(item["text"]))
        raw = "\n".join(text_parts)
        data = _extract_json_object(raw)
        if not data:
            return None
        raw_score = _pick_semantic_score_field(data)
        reason = str(data.get("reason") or "多模态语义评估")
        score, reason, _raw_display = _reconcile_vl_score(raw_score, reason, label="semantic")
        return score, reason
    except Exception as exc:
        logger.info("VL semantic eval skipped: %s", exc)
        return None


async def download_image(url: str) -> Image.Image:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    image = Image.open(BytesIO(resp.content))
    return image.convert("RGB")


def _weighted_total(dimensions: List[DimensionScore]) -> float:
    total = 0.0
    weight_sum = 0.0
    for dim in dimensions:
        total += dim.score * dim.weight
        weight_sum += dim.weight
    if weight_sum <= 0:
        return 0.0
    return total / weight_sum


def _build_feedback(dimensions: List[DimensionScore], total: float) -> str:
    weak = [d for d in dimensions if d.score < 60.0]
    if not weak and total >= IMAGE_EVAL_PASS_SCORE:
        return "配图质量达标。"
    parts = [f"{d.label}不足（{d.score:.0f}分）：{d.detail}" for d in weak]
    return "；".join(parts) if parts else f"综合分 {total:.1f} 未达阈值 {IMAGE_EVAL_PASS_SCORE}"


def _build_deduction_reason(key: str, score: float, detail: str) -> str:
    deducted = max(0.0, 100.0 - score)
    if deducted <= 0.5:
        return "未明显扣分。"

    fallback = detail or "该维度仍有优化空间。"
    focus_by_key = {
        "semantic_alignment": "语义一致性",
        "text_fidelity": "文字真实性",
        "visual_clarity": "视觉清晰度",
        "style_consistency": "视觉风格",
        "slide_consistency": "配色一致性",
        "layout_quality": "布局质量",
    }
    focus = focus_by_key.get(key, "该维度")
    return f"{focus}扣 {deducted:.0f} 分：{fallback}"


async def evaluate_generated_image(
    *,
    image_url: str,
    source_text: str,
    prompt_used: str,
    preview_path: Optional[str] = None,
    slide_type: Optional[str] = None,
) -> ImageQualityReport:
    image = await download_image(image_url)
    ocr_text, ocr_stats = _ocr_on_image_with_stats(image)
    page_type = _infer_slide_type(slide_type, source_text, prompt_used)
    weights = _resolve_dimension_weights(slide_type, source_text, prompt_used)

    text_fidelity_score, text_fidelity_detail = _text_fidelity_score(
        ocr_text, source_text, prompt_used, slide_type=slide_type
    )
    text_readability_score, text_readability_detail = _ocr_readability_score(ocr_text, image)
    stats_penalty, stats_issues = _ocr_stats_readability_penalty(ocr_stats)
    if ocr_text.strip() and stats_penalty > 0:
        text_fidelity_score = max(0.0, text_fidelity_score - stats_penalty)
        text_fidelity_detail = f"{text_fidelity_detail}；文字框可读性扣分：{'、'.join(stats_issues)}"
    if ocr_text.strip() and text_readability_score < 82.0:
        blended_text_score = min(text_fidelity_score, text_fidelity_score * 0.75 + text_readability_score * 0.25)
        if blended_text_score < text_fidelity_score:
            text_fidelity_score = blended_text_score
            text_fidelity_detail = f"{text_fidelity_detail}；文字可读性复核：{text_readability_detail}"

    sem_score, sem_detail = _semantic_heuristic(source_text, prompt_used)
    vl = await _vl_semantic_boost(image_url, source_text, prompt_used)
    if vl:
        sem_score, sem_detail = vl[0], f"VL 评估：{vl[1]}"
        if text_fidelity_score < 45:
            sem_detail += "。文字对错见「文字真实性」评分，此处不重复扣分"
    else:
        sem_detail = f"Prompt 关键词启发式（未启用 VL）：{sem_detail}"

    clarity_score, clarity_detail = _clarity_score(image)
    heuristic_style, heuristic_style_detail = _style_score(image, prompt_used)
    vl_style = await _vl_style_boost(image_url, prompt_used)
    if vl_style:
        vl_score, vl_reason, vl_raw = vl_style
        style_score = max(0.0, min(100.0, heuristic_style * 0.2 + vl_score * 0.8))
        if style_score < 50 and _reason_is_positive_vl(vl_reason):
            style_score = max(style_score, 78.0)
        style_detail = (
            f"[v2] VL raw={vl_raw}→{vl_score:.0f}，启发式={heuristic_style:.0f}，"
            f"综合={style_score:.0f}；{vl_reason}"
        )
    else:
        style_score, style_detail = heuristic_style, heuristic_style_detail
    slide_score, slide_detail = _slide_consistency_score(image, preview_path)
    layout_score, layout_detail = _layout_quality_score(image, ocr_text)

    raw_scores = {
        "semantic_alignment": (sem_score, sem_detail),
        "text_fidelity": (text_fidelity_score, text_fidelity_detail),
        "visual_clarity": (clarity_score, clarity_detail),
        "style_consistency": (style_score, style_detail),
        "slide_consistency": (slide_score, slide_detail),
        "layout_quality": (layout_score, layout_detail),
    }

    dimensions: List[DimensionScore] = []
    for key, (label, _default_weight) in DIMENSION_WEIGHTS.items():
        score, detail = raw_scores[key]
        weight = weights.get(key, _default_weight)
        dimensions.append(
            DimensionScore(
                key=key,
                label=label,
                score=score,
                weight=weight,
                detail=detail,
                max_score=100.0,
                deducted=max(0.0, 100.0 - score),
                deduction_reason=_build_deduction_reason(key, score, detail),
            )
        )

    total = _weighted_total(dimensions)
    passed = total >= IMAGE_EVAL_PASS_SCORE
    feedback = _build_feedback(dimensions, total)
    if page_type in {"cover", "section-divider", "diagram"}:
        feedback = f"[{page_type} 页权重] {feedback}"
    return ImageQualityReport(
        passed=passed,
        total_score=total,
        dimensions=dimensions,
        feedback=feedback,
    )


def build_regeneration_hints(report: ImageQualityReport) -> str:
    hints: List[str] = []
    by_key = {d.key: d for d in report.dimensions}
    if by_key.get("text_fidelity") and by_key["text_fidelity"].score < 65:
        hints.append(
            "Avoid rendering long Chinese paragraphs. Only render short titles when necessary. "
            "Do not invent names, IDs, or numbers."
        )
    if by_key.get("semantic_alignment") and by_key["semantic_alignment"].score < 65:
        hints.append("必须准确体现幻灯片正文的核心语义与关键词。")
    if by_key.get("visual_clarity") and by_key["visual_clarity"].score < 65:
        hints.append("提高主体边缘、文字/图形轮廓和整体对比度，避免模糊和噪点。")
    if by_key.get("style_consistency") and by_key["style_consistency"].score < 65:
        hints.append("保持现代扁平矢量信息图风格，色块简洁，不要写实照片风。")
    if by_key.get("slide_consistency") and by_key["slide_consistency"].score < 65:
        hints.append("配色与构图应与当前 PPT 页面协调统一。")
    if by_key.get("layout_quality") and by_key["layout_quality"].score < 65:
        hints.append("降低信息密度，增加留白，保持对齐与层级清晰。")
    return " ".join(hints)
