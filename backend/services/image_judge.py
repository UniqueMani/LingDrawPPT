from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

import httpx
from backend.config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    IMAGE_EVAL_VL_MODEL,
    IMAGE_JUDGE_CONFIDENCE_GATE,
    IMAGE_JUDGE_LOW_THRESHOLD,
    IMAGE_JUDGE_MAX_FEEDBACK,
    IMAGE_JUDGE_MAX_FIX_TOKENS,
    IMAGE_JUDGE_USE_VL,
)
from backend.services.image_quality import ImageQualityReport

logger = logging.getLogger(__name__)

# 评估维度 → 裁判固定维度（诊断用途，通用模式不再做增量 Prompt 改写）
EVAL_TO_JUDGE_DIM: Dict[str, str] = {
    "semantic_alignment": "semantic_alignment",
    "text_fidelity": "text_fidelity",
    "visual_clarity": "visual_clarity",
    "style_consistency": "style_consistency",
    "slide_consistency": "slide_consistency",
    "layout_quality": "layout_quality",
}

DEFAULT_LOCKED_FEATURES = ("theme", "main object", "color palette", "aspect ratio")
BASE_PROMPT_MAX_CHARS = 800
MAX_INCREMENTAL_FIXES = 2
FIX_HISTORY_MAXLEN = 6
MAX_FEEDBACK_ROUNDS = 3
# index 0 = 最新一轮，index 越大越旧
ROUND_DECAY_WEIGHTS = (1.0, 0.7, 0.5)

GENERIC_CN_TERMS = frozenset(
    {
        "介绍",
        "概述",
        "说明",
        "内容",
        "背景",
        "总结",
        "分析",
        "封面",
        "目录",
        "总体",
        "整体",
        "方案",
        "架构",
        "系统",
        "流程",
        "模块",
        "平台",
        "框架",
        "结构",
        "页面",
        "章节",
    }
)

BAD_OBJECTS = frozenset(
    {
        "设计",
        "研究",
        "实现",
        "方法",
        "方案",
        "分析",
        "总结",
        "介绍",
        "概述",
        "说明",
        "内容",
        "背景",
        "应用",
        "发展",
        "趋势",
        "现状",
        "展望",
        "结论",
    }
)

STRUCTURAL_SPLIT_RE = re.compile(
    r"(?:系统|架构|方案|流程|模块|平台|框架|结构|总体|整体|介绍|概述|说明|分析|总结|设计|研究|实现|方法)"
)

OPPOSITE_FIX_PAIRS = (
    ("increase spacing", "reduce spacing"),
    ("increase whitespace", "reduce whitespace"),
    ("more whitespace", "less whitespace"),
    ("enlarge", "shrink"),
    ("enlarge", "reduce size"),
    ("expand", "compress"),
    ("increase", "decrease"),
    ("add clutter", "reduce clutter"),
    ("more elements", "fewer elements"),
    ("add more semantic", "reduce clutter"),
    ("add more elements", "reduce clutter"),
    ("more semantic", "less clutter"),
    ("brighten", "darken"),
    ("more text", "less text"),
)
RULE_FIX_TEMPLATES: Dict[str, Dict[str, str]] = {
    "semantic_alignment": {
        "problem": "image misses core slide semantics",
        "constraint": "emphasize slide topic keywords in primary visual focus",
    },
    "text_fidelity": {
        "problem": "ocr text mismatches slide content or contains garbled characters",
        "constraint": "avoid long paragraphs; keep short titles only; do not invent names IDs or numbers",
    },
    "visual_clarity": {
        "problem": "edges weak or overall contrast low",
        "constraint": "increase edge contrast and primary object sharpness by 20%",
    },
    "style_consistency": {
        "problem": "style drifts from flat infographic intent",
        "constraint": "keep flat vector infographic style; avoid photorealistic rendering",
    },
    "slide_consistency": {
        "problem": "color or layout mismatches slide preview",
        "constraint": "align palette and spacing with current slide preview",
    },
    "layout_quality": {
        "problem": "layout crowded or hierarchy unclear",
        "constraint": "reduce side clutter and increase whitespace around primary object",
    },
}


@dataclass
class JudgeFix:
    issue_area: str
    severity: str
    problem: str
    constraint: str
    preserve: List[str] = field(default_factory=list)
    priority: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issueArea": self.issue_area,
            "severity": self.severity,
            "problem": self.problem,
            "constraint": self.constraint,
            "preserve": self.preserve,
            "priority": self.priority,
        }


@dataclass
class JudgeFeedback:
    feedback_confidence: float
    cannot_modify: List[str]
    fixes: List[JudgeFix]
    low_score_dimensions: Dict[str, float]
    discarded: bool = False
    source: str = "rules"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feedbackConfidence": round(self.feedback_confidence, 2),
            "cannotModify": self.cannot_modify,
            "fixes": [item.to_dict() for item in self.fixes],
            "lowScoreDimensions": {
                key: round(value, 2) for key, value in self.low_score_dimensions.items()
            },
            "discarded": self.discarded,
            "source": self.source,
        }


def _normalize_score(score: float) -> float:
    if score <= 1.0:
        return max(0.0, min(1.0, score))
    return max(0.0, min(1.0, score / 100.0))


def _confidence_from_low_dims(low_dims: Dict[str, float]) -> float:
    if not low_dims:
        return 0.5
    mean_low = sum(low_dims.values()) / len(low_dims)
    severity = 1.0 - mean_low
    coverage = min(len(low_dims) / 3.0, 1.0)
    confidence = 0.7 * severity + 0.3 * coverage
    return max(0.5, min(0.9, confidence))


def is_quality_generation_mode(generation_mode: str) -> bool:
    """通用模式（standard）：三轮生成 + 裁判反馈；极速模式（fast）不启用裁判。"""
    return (generation_mode or "standard").strip().lower() == "standard"


def _merge_cannot_modify(parsed: Sequence[str]) -> List[str]:
    merged = list(DEFAULT_LOCKED_FEATURES)
    seen = {item.lower() for item in merged}
    for item in parsed:
        cleaned = str(item).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(cleaned)
    return merged


def _is_cjk_dominant(text: str) -> bool:
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return False
    cjk_count = sum(1 for ch in chars if "\u4e00" <= ch <= "\u9fff")
    return cjk_count / len(chars) >= 0.3


def _truncate_tokens(text: str, max_tokens: int = IMAGE_JUDGE_MAX_FIX_TOKENS) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if _is_cjk_dominant(cleaned):
        max_chars = max_tokens * 2
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[:max_chars].rstrip()
    parts = cleaned.split()
    if len(parts) <= max_tokens:
        return " ".join(parts)
    return " ".join(parts[:max_tokens])


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


def _extract_main_object(topic: str, base_prompt: str) -> Optional[str]:
    topic = (topic or "").strip()
    if not topic:
        return None

    segments = [part.strip() for part in STRUCTURAL_SPLIT_RE.split(topic) if part.strip()]
    candidates: List[str] = []
    for segment in segments:
        if segment in GENERIC_CN_TERMS or segment in BAD_OBJECTS:
            continue
        if 2 <= len(segment) <= 6:
            candidates.append(segment)
        elif len(segment) > 6:
            candidates.append(segment[:6])

    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        return None

    prompt = base_prompt or ""
    shared = [item for item in candidates if item in prompt]
    pool = shared or candidates
    return min(pool, key=len)


def _normalize_fix_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _is_opposite_fix(new_fix: str, old_fix: str) -> bool:
    new_norm = _normalize_fix_text(new_fix)
    old_norm = _normalize_fix_text(old_fix)
    for left, right in OPPOSITE_FIX_PAIRS:
        if (left in old_norm and right in new_norm) or (right in old_norm and left in new_norm):
            return True
    return False


def filter_oscillating_fixes(
    new_items: Sequence[str],
    history: Sequence[str],
) -> List[str]:
    accepted: List[str] = []
    for item in new_items:
        normalized = _normalize_fix_text(item)
        if not normalized:
            continue
        if any(_is_opposite_fix(item, old) for old in history):
            logger.info("Discarding oscillating fix: %s", item)
            continue
        accepted.append(item.strip())
    return accepted


def _dedupe_fixes_by_dimension(fixes: Sequence[JudgeFix]) -> List[JudgeFix]:
    used_dims: Set[str] = set()
    deduped: List[JudgeFix] = []
    for fix in sorted(fixes, key=lambda item: item.priority):
        if fix.issue_area in used_dims:
            continue
        used_dims.add(fix.issue_area)
        deduped.append(fix)
        if len(deduped) >= IMAGE_JUDGE_MAX_FEEDBACK:
            break
    return deduped


def _build_preserve_list(locked_constraints: Sequence[str]) -> List[str]:
    preserve = [
        item.split(":", 1)[-1].strip()
        for item in locked_constraints
        if item and ":" in item
    ]
    return preserve[:5]


def extract_locked_constraints(base_prompt: str, source_text: str) -> List[str]:
    locked: List[str] = []
    topic = (source_text or "").strip().split("\n")[0][:120].strip()
    if topic:
        locked.append(f"theme: {topic}")

    style_hits = [
        kw
        for kw in (
            "扁平",
            "矢量",
            "信息图",
            "科技",
            "蓝色",
            "flat",
            "vector",
            "infographic",
            "ppt",
        )
        if kw in (base_prompt or "").lower() or kw in (base_prompt or "")
    ]
    if style_hits:
        locked.append(f"style: {', '.join(style_hits[:4])}")

    main_object = _extract_main_object(topic, base_prompt)
    if main_object:
        locked.append(f"main object: {main_object}")

    palette_hits = re.findall(
        r"(蓝|红|绿|黄|橙|紫|灰|黑|白|科技蓝|暖色|冷色|blue|red|green)",
        base_prompt or "",
        flags=re.I,
    )
    if palette_hits:
        locked.append(f"color palette: {', '.join(dict.fromkeys(palette_hits[:3]))}")

    locked.append("aspect ratio: keep slide-friendly 16:9 composition")
    return locked


def get_low_score_breakdown(report: ImageQualityReport) -> Dict[str, float]:
    breakdown: Dict[str, float] = {}
    for dim in report.dimensions:
        normalized = _normalize_score(dim.score)
        judge_key = EVAL_TO_JUDGE_DIM.get(dim.key, dim.key)
        breakdown[judge_key] = normalized
    return breakdown


def get_low_score_dimensions(report: ImageQualityReport) -> Dict[str, float]:
    threshold = _normalize_score(IMAGE_JUDGE_LOW_THRESHOLD)
    breakdown = get_low_score_breakdown(report)
    return {key: score for key, score in breakdown.items() if score < threshold}


def _severity_for_score(score: float) -> str:
    if score < 0.45:
        return "high"
    if score < 0.58:
        return "medium"
    return "low"


def _rule_based_judge(
    report: ImageQualityReport,
    *,
    locked_constraints: Sequence[str],
    low_dims: Dict[str, float],
) -> JudgeFeedback:
    reverse_map = {v: k for k, v in EVAL_TO_JUDGE_DIM.items()}
    ranked_judge_keys = sorted(low_dims.keys(), key=lambda key: low_dims[key])
    fixes: List[JudgeFix] = []
    preserve = _build_preserve_list(locked_constraints)
    for idx, judge_key in enumerate(ranked_judge_keys[:IMAGE_JUDGE_MAX_FEEDBACK], start=1):
        eval_key = reverse_map.get(judge_key, judge_key)
        score = low_dims.get(judge_key, 0.0)
        template = RULE_FIX_TEMPLATES.get(eval_key, {})
        fixes.append(
            JudgeFix(
                issue_area=judge_key,
                severity=_severity_for_score(score),
                problem=template.get("problem", f"{judge_key} below threshold"),
                constraint=_truncate_tokens(
                    template.get("constraint", f"improve {judge_key} without changing theme")
                ),
                preserve=preserve,
                priority=idx,
            )
        )

    fixes = _dedupe_fixes_by_dimension(fixes)
    confidence = _confidence_from_low_dims(low_dims)
    discarded = confidence < IMAGE_JUDGE_CONFIDENCE_GATE or not fixes
    return JudgeFeedback(
        feedback_confidence=confidence,
        cannot_modify=list(DEFAULT_LOCKED_FEATURES),
        fixes=[] if discarded else fixes,
        low_score_dimensions=low_dims,
        discarded=discarded,
        source="rules",
    )


async def _vl_judge(
    *,
    image_url: str,
    base_prompt: str,
    source_text: str,
    low_dims: Dict[str, float],
    locked_constraints: Sequence[str],
) -> Optional[JudgeFeedback]:
    if not IMAGE_JUDGE_USE_VL or not DASHSCOPE_API_KEY or not low_dims:
        return None

    low_dim_text = json.dumps(low_dims, ensure_ascii=False)
    locked_text = json.dumps(list(locked_constraints), ensure_ascii=False)
    low_threshold = _normalize_score(IMAGE_JUDGE_LOW_THRESHOLD)
    instruction = (
        "你是 PPT 配图增量优化裁判。只能分析低分维度，禁止评价或修改高分维度。\n"
        "必须优先检查 text_fidelity：OCR 乱码、错字、幻觉文字、重复文字、姓名/学号错误。\n"
        "禁止创造新元素（新主体、新图表、新风格、新配色）。只允许调整已有元素。\n"
        f"低分维度 (<{low_threshold:.2f}): {low_dim_text}\n"
        f"锁定约束: {locked_text}\n"
        f"正文: {source_text[:600]}\n"
        f"基础 Prompt: {base_prompt[:500]}\n"
        "任务:\n"
        f"- 仅分析上述低分维度，最多 {IMAGE_JUDGE_MAX_FEEDBACK} 条 fixes\n"
        f"- 每条 constraint 必须是可执行英文指令，<= {IMAGE_JUDGE_MAX_FIX_TOKENS} tokens\n"
        "- 禁止输出「更美观/更高级/更合理」等模糊词\n"
        "- cannot_modify 必须包含 theme, main object, color palette\n"
        "只输出 JSON:\n"
        '{"feedback_confidence":0.0,"cannot_modify":["theme"],"fixes":[{"issue_area":"layout_balance",'
        '"severity":"high","problem":"left region overcrowded",'
        '"constraint":"increase whitespace around center object",'
        '"preserve":["train silhouette"],"priority":1}]}'
    )
    url = f"{DASHSCOPE_BASE_URL.rstrip('/')}/api/v1/services/aigc/multimodal-generation/generation"
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
        confidence = float(data.get("feedback_confidence", 0))
        cannot_modify = _merge_cannot_modify(
            str(item).strip()
            for item in (data.get("cannot_modify") or [])
            if str(item).strip()
        )

        fixes: List[JudgeFix] = []
        for idx, item in enumerate((data.get("fixes") or [])[:IMAGE_JUDGE_MAX_FEEDBACK], start=1):
            if not isinstance(item, dict):
                continue
            issue_area = str(item.get("issue_area") or "").strip()
            if issue_area and issue_area not in low_dims:
                continue
            constraint = _truncate_tokens(str(item.get("constraint") or "").strip())
            if not constraint:
                continue
            fixes.append(
                JudgeFix(
                    issue_area=issue_area or "unknown",
                    severity=str(item.get("severity") or "medium"),
                    problem=str(item.get("problem") or "")[:120],
                    constraint=constraint,
                    preserve=[
                        str(v).strip()
                        for v in (item.get("preserve") or [])
                        if str(v).strip()
                    ],
                    priority=int(item.get("priority") or idx),
                )
            )

        fixes = _dedupe_fixes_by_dimension(fixes)
        if confidence < IMAGE_JUDGE_CONFIDENCE_GATE or not fixes:
            return JudgeFeedback(
                feedback_confidence=confidence,
                cannot_modify=cannot_modify,
                fixes=[],
                low_score_dimensions=low_dims,
                discarded=True,
                source="vl",
            )

        return JudgeFeedback(
            feedback_confidence=confidence,
            cannot_modify=cannot_modify,
            fixes=fixes,
            low_score_dimensions=low_dims,
            discarded=False,
            source="vl",
        )
    except Exception as exc:
        logger.info("VL judge skipped: %s", exc)
        return None


async def judge_for_regeneration(
    *,
    image_url: str,
    base_prompt: str,
    source_text: str,
    report: ImageQualityReport,
    locked_constraints: Sequence[str],
    generation_mode: str = "standard",
) -> Optional[JudgeFeedback]:
    if not is_quality_generation_mode(generation_mode):
        return None

    low_dims = get_low_score_dimensions(report)
    if not low_dims:
        return None

    vl_result = await _vl_judge(
        image_url=image_url,
        base_prompt=base_prompt,
        source_text=source_text,
        low_dims=low_dims,
        locked_constraints=locked_constraints,
    )
    if vl_result and not vl_result.discarded and vl_result.fixes:
        return vl_result

    rule_result = _rule_based_judge(
        report,
        locked_constraints=locked_constraints,
        low_dims=low_dims,
    )
    if vl_result and vl_result.discarded:
        rule_result.source = "rules_fallback"
    return rule_result


def merge_incremental_fixes(
    existing: Sequence[str],
    new_items: Sequence[str],
    *,
    max_total: int = MAX_INCREMENTAL_FIXES,
) -> List[str]:
    merged: List[str] = []
    seen = set()
    for item in list(existing) + list(new_items):
        normalized = (item or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(item.strip())
    return merged[:max_total]


def collect_weighted_fixes(
    fix_rounds: Sequence[Sequence[str]],
    *,
    max_total: int = MAX_INCREMENTAL_FIXES,
    min_weight: float = 0.45,
) -> List[str]:
    rounds = [list(round_fixes) for round_fixes in fix_rounds if round_fixes][-MAX_FEEDBACK_ROUNDS:]
    if not rounds:
        return []

    weighted_items: List[tuple[float, int, int, str]] = []
    round_count = len(rounds)
    for round_idx, round_fixes in enumerate(rounds):
        age_from_latest = round_count - 1 - round_idx
        weight = ROUND_DECAY_WEIGHTS[min(age_from_latest, len(ROUND_DECAY_WEIGHTS) - 1)]
        for fix_idx, fix in enumerate(round_fixes):
            cleaned = (fix or "").strip()
            if not cleaned or weight < min_weight:
                continue
            weighted_items.append((weight, round_idx, fix_idx, cleaned))

    weighted_items.sort(key=lambda item: (-item[0], -item[1], item[2]))
    selected: List[str] = []
    seen = set()
    for _, _, _, fix in weighted_items:
        normalized = _normalize_fix_text(fix)
        if normalized in seen:
            continue
        seen.add(normalized)
        selected.append(fix)
        if len(selected) >= max_total:
            break
    return selected


def integrate_judge_fixes(
    fix_rounds: Sequence[Sequence[str]],
    feedback: JudgeFeedback,
    history_fixes: Sequence[str],
) -> tuple[List[List[str]], List[str], List[str]]:
    history = list(history_fixes)[-FIX_HISTORY_MAXLEN:]
    new_fixes = fixes_from_feedback(feedback)
    filtered = filter_oscillating_fixes(new_fixes, history)
    updated_rounds = [list(round_fixes) for round_fixes in fix_rounds]
    if filtered:
        updated_rounds.append(filtered)
        updated_rounds = updated_rounds[-MAX_FEEDBACK_ROUNDS:]
    weighted = collect_weighted_fixes(updated_rounds)
    prompt_fixes = weighted[:MAX_INCREMENTAL_FIXES]
    return updated_rounds, filtered, prompt_fixes


def build_incremental_prompt(
    base_prompt: str,
    locked_constraints: Sequence[str],
    incremental_fixes: Sequence[str],
) -> str:
    base = (base_prompt or "").strip()
    if len(base) > BASE_PROMPT_MAX_CHARS:
        base = base[:BASE_PROMPT_MAX_CHARS].rstrip() + "..."
    locked = [item.strip() for item in locked_constraints if item.strip()]
    fixes = [_truncate_tokens(item) for item in incremental_fixes if item.strip()]

    sections = [f"[Base Intent]\n{base}"]
    if locked:
        sections.append("[Locked Constraints]\n" + "\n".join(f"- {item}" for item in locked))
    if fixes:
        sections.append(
            "[Fixes]\n" + "\n".join(f"{idx}. {item}" for idx, item in enumerate(fixes, start=1))
        )
    sections.append(
        "[Generation Rules]\n"
        "Do not add new main subjects, charts, styles, or color systems. "
        "Only adjust existing elements. "
        "Preserve overall composition when possible. "
        "Avoid large structural changes. "
        "Do not replace primary entities."
    )
    return "\n\n".join(sections)


def fixes_from_feedback(feedback: JudgeFeedback) -> List[str]:
    ranked = sorted(feedback.fixes, key=lambda item: item.priority)
    fixes: List[str] = []
    seen: Set[str] = set()
    for item in ranked:
        constraint = _truncate_tokens(item.constraint)
        if not constraint:
            continue
        normalized = _normalize_fix_text(constraint)
        if normalized in seen:
            continue
        seen.add(normalized)
        fixes.append(constraint)
    return fixes
