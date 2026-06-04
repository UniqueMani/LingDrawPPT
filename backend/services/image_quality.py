from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
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
    "semantic_match": ("文本语义匹配", 0.35),
    "ocr_cleanliness": ("文字表达有效性", 0.15),
    "clarity": ("清晰度", 0.20),
    "style_consistency": ("风格一致性", 0.15),
    "slide_consistency": ("与页面一致性", 0.15),
}


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


def _token_set(text: str) -> set[str]:
    cleaned = (text or "").lower()
    tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}", cleaned))
    tokens.update(w for w in re.findall(r"[a-z0-9_./-]{3,}", cleaned) if not w.isdigit())
    return tokens


def _ocr_on_image(image: Image.Image) -> str:
    lines = []
    try:
        result, _ = _ocr_engine()(np.asarray(image.convert("RGB")))
        for item in result or []:
            if len(item) > 1 and item[0] and str(item[1]).strip():
                lines.append(
                    {
                        "text": str(item[1]).strip(),
                        "left": min(float(p[0]) for p in item[0]),
                        "top": min(float(p[1]) for p in item[0]),
                        "bottom": max(float(p[1]) for p in item[0]),
                    }
                )
    except Exception as exc:
        logger.warning("OCR evaluate failed: %s", exc)
        return ""
    return _join_ocr_lines(lines).strip()


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
    prompt_part = min(40.0, style_hits * 12.0)

    small = image.convert("RGB").resize((48, 48))
    arr = np.asarray(small).reshape(-1, 3)
    unique_ratio = len({tuple(px) for px in arr}) / max(1, arr.shape[0])
    if unique_ratio < 0.35:
        visual_part = 55.0
        visual_detail = "色块简洁，符合扁平信息图特征"
    elif unique_ratio < 0.60:
        visual_part = 44.0
        visual_detail = "色彩层次适中"
    else:
        visual_part = 30.0
        visual_detail = "色彩较丰富，仍可用于信息图表达"
    score = min(100.0, prompt_part + visual_part)
    return score, visual_detail


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


def _ocr_cleanliness_score(ocr_text: str, source_text: str = "", prompt: str = "") -> Tuple[float, str]:
    text = (ocr_text or "").strip()
    if not text:
        return 100.0, "未检测到可读文字，画面干净"

    normalized = re.sub(r"\s+", " ", text)
    line_count = text.count("\n") + 1
    target_context = " ".join([source_text or "", prompt or ""])
    target_tokens = _token_set(target_context)
    ocr_tokens = _token_set(normalized)
    numeric_tokens = set(re.findall(r"\d+(?:\.\d+)?%?", normalized))
    target_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", target_context))

    overlap = len(ocr_tokens & target_tokens) / max(1, len(ocr_tokens)) if ocr_tokens else 0.0
    number_overlap = len(numeric_tokens & target_numbers) / max(1, len(numeric_tokens)) if numeric_tokens else 0.0

    suspicious_chars = len(re.findall(r"[\ufffd□■◆◇★☆@#$%^*_+=<>\\|]", normalized))
    latin_noise = len(re.findall(r"[A-Za-z]{8,}", normalized))
    long_unmatched = len(normalized) > 80 and overlap < 0.25 and number_overlap < 0.25

    if overlap >= 0.45 or number_overlap >= 0.55:
        penalty = min(18.0, suspicious_chars * 6.0 + max(0, line_count - 8) * 2.0)
        score = max(78.0, 96.0 - penalty)
        preview = normalized[:60] + ("..." if len(normalized) > 60 else "")
        return score, f"检测到与页面内容一致的文字/数值：{preview}"

    penalty = suspicious_chars * 10.0 + latin_noise * 4.0 + line_count * 4.0
    if long_unmatched:
        penalty += 35.0
    score = max(35.0, 85.0 - penalty)
    preview = normalized[:60] + ("..." if len(normalized) > 60 else "")
    return score, f"检测到文字但与页面内容匹配度较低：{preview}"


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
        detail = "色调与当前页预览较为协调"
    elif score >= 55:
        detail = "与当前页风格有一定偏差"
    else:
        detail = "色调或风格与当前页差异较大"
    return score, detail


async def _vl_semantic_boost(image_url: str, source_text: str, prompt: str) -> Optional[Tuple[float, str]]:
    if not IMAGE_EVAL_USE_VL or not DASHSCOPE_API_KEY:
        return None
    url = f"{DASHSCOPE_BASE_URL.rstrip('/')}/api/v1/services/aigc/multimodal-generation/generation"
    instruction = (
        "你是 PPT 配图质量评审。根据配图是否表达以下幻灯片正文语义，给出 0-100 的 semantic_score。"
        "只输出 JSON：{\"semantic_score\": number, \"reason\": string}\n"
        f"正文：{source_text[:800]}\n"
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
        raw = "\n".join(text_parts)
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        data = json.loads(match.group(0))
        score = float(data.get("semantic_score", 0))
        reason = str(data.get("reason") or "多模态语义评估")
        return max(0.0, min(100.0, score)), reason[:200]
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
        "semantic_match": "语义表达",
        "ocr_cleanliness": "文字表达有效性",
        "clarity": "清晰度",
        "style_consistency": "视觉风格",
        "slide_consistency": "页面一致性",
    }
    focus = focus_by_key.get(key, "该维度")
    return f"{focus}扣 {deducted:.0f} 分：{fallback}"


async def evaluate_generated_image(
    *,
    image_url: str,
    source_text: str,
    prompt_used: str,
    preview_path: Optional[str] = None,
) -> ImageQualityReport:
    image = await download_image(image_url)
    ocr_text = _ocr_on_image(image)

    sem_score, sem_detail = _semantic_heuristic(source_text, prompt_used)
    vl = await _vl_semantic_boost(image_url, source_text, prompt_used)
    if vl:
        sem_score = sem_score * 0.4 + vl[0] * 0.6
        sem_detail = f"{sem_detail}；VL：{vl[1]}"

    ocr_score, ocr_detail = _ocr_cleanliness_score(ocr_text, source_text, prompt_used)
    clarity_score, clarity_detail = _clarity_score(image)
    style_score, style_detail = _style_score(image, prompt_used)
    slide_score, slide_detail = _slide_consistency_score(image, preview_path)

    raw_scores = {
        "semantic_match": (sem_score, sem_detail),
        "ocr_cleanliness": (ocr_score, ocr_detail),
        "clarity": (clarity_score, clarity_detail),
        "style_consistency": (style_score, style_detail),
        "slide_consistency": (slide_score, slide_detail),
    }

    dimensions: List[DimensionScore] = []
    for key, (label, weight) in DIMENSION_WEIGHTS.items():
        score, detail = raw_scores[key]
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
    return ImageQualityReport(
        passed=passed,
        total_score=total,
        dimensions=dimensions,
        feedback=feedback,
    )


def build_regeneration_hints(report: ImageQualityReport) -> str:
    hints: List[str] = []
    by_key = {d.key: d for d in report.dimensions}
    if by_key.get("ocr_cleanliness") and by_key["ocr_cleanliness"].score < 65:
        hints.append("避免无关乱码、伪文字、水印或品牌 Logo；如果需要图表标题、年份、数值，必须清晰且与页面内容一致。")
    if by_key.get("semantic_match") and by_key["semantic_match"].score < 65:
        hints.append("必须准确体现幻灯片正文的核心语义与关键词。")
    if by_key.get("clarity") and by_key["clarity"].score < 65:
        hints.append("提高主体边缘、文字/图形轮廓和整体对比度，避免模糊和噪点。")
    if by_key.get("style_consistency") and by_key["style_consistency"].score < 65:
        hints.append("保持现代扁平矢量信息图风格，色块简洁，不要写实照片风。")
    if by_key.get("slide_consistency") and by_key["slide_consistency"].score < 65:
        hints.append("配色与构图应与当前 PPT 页面协调统一。")
    return " ".join(hints)
