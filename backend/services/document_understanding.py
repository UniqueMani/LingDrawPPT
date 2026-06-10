from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

TOPIC_TYPES: Dict[str, Dict[str, Any]] = {
    "system_architecture": {
        "keywords": ["架构", "模块", "系统", "组件", "结构", "总体", "framework", "architecture"],
        "visual": "architecture",
        "label_zh": "系统架构",
    },
    "workflow": {
        "keywords": ["流程", "步骤", "阶段", "环节", "工序", "pipeline", "workflow"],
        "visual": "flowchart",
        "label_zh": "流程说明",
    },
    "data_analysis": {
        "keywords": ["统计", "指标", "数据", "分析", "占比", "趋势", "chart", "metric"],
        "visual": "chart",
        "label_zh": "数据分析",
    },
    "comparison": {
        "keywords": ["对比", "比较", "差异", "优劣", "vs", "对照"],
        "visual": "comparison",
        "label_zh": "对比分析",
    },
    "timeline": {
        "keywords": ["时间", "历程", "阶段", "里程碑", "timeline", "roadmap"],
        "visual": "timeline",
        "label_zh": "时间线",
    },
    "concept_explanation": {
        "keywords": ["定义", "原理", "概念", "机制", "含义", "introduction"],
        "visual": "illustration",
        "label_zh": "概念说明",
    },
    "relationship": {
        "keywords": ["关系", "网络", "拓扑", "连接", "依赖", "生态"],
        "visual": "relationship_map",
        "label_zh": "关系网络",
    },
}

CONTENT_INTENTS: Dict[str, Dict[str, Any]] = {
    "architecture": {"keywords": ["架构", "模块", "组件", "系统结构"], "visual": "architecture"},
    "process": {"keywords": ["流程", "步骤", "阶段", "运行", "调度"], "visual": "flowchart"},
    "hierarchy": {"keywords": ["层级", "分级", "组织", "结构图"], "visual": "hierarchy"},
    "overview": {"keywords": ["总体", "概览", "总览", "overview", "introduction"], "visual": "overview"},
    "compare": {"keywords": ["对比", "比较", "差异", "vs"], "visual": "comparison"},
    "trend": {"keywords": ["趋势", "增长", "变化", "走势"], "visual": "line_chart"},
    "mechanism": {"keywords": ["机制", "原理", "工作方式", "如何实现"], "visual": "mechanism"},
    "relationship": {"keywords": ["关系", "交互", "连接", "依赖"], "visual": "relationship_map"},
    "timeline": {"keywords": ["时间线", "历程", "里程碑", "roadmap"], "visual": "timeline"},
}

PAGE_ROLES: Dict[str, List[str]] = {
    "overview": ["总体", "概览", "总览", "overview", "目录", "封面", "introduction"],
    "detail": ["细节", "实现", "模块", "子系统", "详解"],
    "process": ["流程", "步骤", "阶段", "环节", "运行", "调度", "pipeline", "workflow"],
    "case": ["案例", "示例", "场景", "应用"],
    "summary": ["总结", "结论", "回顾", "summary"],
    "transition": ["过渡", "章节", "分隔", "section"],
}

VISUAL_PRIMITIVES: Dict[str, str] = {
    "architecture": "architecture_block, layered modules, subsystem cards, flat vector",
    "flowchart": "workflow_arrow, process nodes, directional connectors, flat vector",
    "chart": "dashboard panel, metric cards, simple chart blocks, flat vector",
    "comparison": "comparison_bar, side-by-side panels, flat vector",
    "timeline": "timeline, milestone nodes, flat vector",
    "illustration": "concept icon, explanatory diagram, flat vector",
    "relationship_map": "network nodes, relation links, flat vector",
    "hierarchy": "tree hierarchy, parent-child blocks, flat vector",
    "overview": "hero overview layout, key modules summary, flat vector",
    "mechanism": "mechanism diagram, cause-effect blocks, flat vector",
    "line_chart": "simple line trend panel, flat vector infographic",
}

ENTITY_TYPE_PATTERNS: List[Tuple[str, str]] = [
    (r"^[A-Z0-9]{2,8}$", "acronym"),
    (r".*(系统|平台|模块|网络|服务)$", "system"),
    (r".*(中心|控制台|调度)$", "facility"),
    (r".*(列车|信号|设备|网关)$", "object"),
]

GENERIC_ENTITY_TERMS = frozenset(
    {
        "内容",
        "页面",
        "系统介绍",
        "概述",
        "说明",
        "背景",
        "总结",
        "目录",
        "章节",
        "报告",
        "研究",
        "方法",
        "实现",
        "设计",
        "分析",
    }
)


def _page_text(page: Dict[str, Any]) -> str:
    return f"{page.get('topic') or ''} {page.get('body') or ''}".strip()


def _score_by_keywords(text: str, keyword_map: Dict[str, Dict[str, Any]]) -> Tuple[str, float]:
    lowered = text.lower()
    best_key = "concept_explanation"
    best_score = 0.0
    for key, meta in keyword_map.items():
        score = 0.0
        for kw in meta.get("keywords") or []:
            if kw in text or kw.lower() in lowered:
                score += 1.0
        if score > best_score:
            best_key = key
            best_score = score
    return best_key, best_score


def classify_topic(text: str) -> str:
    topic_key, _ = _score_by_keywords(text, TOPIC_TYPES)
    return topic_key


def detect_intent(text: str) -> str:
    intent_key, _ = _score_by_keywords(text, CONTENT_INTENTS)
    return intent_key


def infer_page_role(
    page_index: int,
    total_pages: int,
    text: str,
    *,
    content_intent: str = "",
    topic_type: str = "",
) -> str:
    lowered = text.lower()
    if topic_type == "workflow" or content_intent == "process":
        return "process"
    for role, hints in PAGE_ROLES.items():
        if role == "process":
            continue
        if any(hint in text or hint.lower() in lowered for hint in hints):
            return role
    for hint in PAGE_ROLES["process"]:
        if hint in text or hint.lower() in lowered:
            return "process"
    if page_index == 0:
        return "overview"
    if page_index == total_pages - 1:
        if topic_type == "data_analysis" or content_intent in {"trend", "compare"}:
            return "detail"
        return "summary"
    if page_index == 1 and total_pages >= 4:
        return "detail"
    return "detail"


def build_slide_graph(pages: Sequence[Dict[str, Any]]) -> Dict[int, List[int]]:
    """Legacy adjacency list; typed relations见 consistency_controller.build_typed_slide_graph。"""
    graph: Dict[int, List[int]] = {}
    page_nums = [int(p.get("page") or idx + 1) for idx, p in enumerate(pages)]
    for idx, page in enumerate(pages):
        pnum = page_nums[idx]
        text = _page_text(page)
        topic_type = classify_topic(text)
        content_intent = detect_intent(text)
        role = infer_page_role(
            idx, len(pages), text, content_intent=content_intent, topic_type=topic_type
        )
        related: List[int] = []
        if idx + 1 < len(pages):
            related.append(page_nums[idx + 1])
        if role == "overview" and idx + 2 < len(pages):
            related.append(page_nums[idx + 2])
        graph[pnum] = sorted(set(related))
    return graph


def _tokenize_terms(text: str) -> List[str]:
    terms: List[str] = []
    terms.extend(re.findall(r"[\u4e00-\u9fa5]{2,12}", text))
    terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", text))
    terms.extend(re.findall(r"[\u4e00-\u9fa5]{2,8}(?:系统|中心|平台|模块|网络|列车|信号|结构|服务|设备)", text))
    return terms


def _entity_type(name: str) -> str:
    for pattern, label in ENTITY_TYPE_PATTERNS:
        if re.match(pattern, name):
            return label
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", name):
        return "concept"
    return "entity"


def _importance_score(term: str, tf: float, idf: float, page_count: int) -> float:
    base = tf * idf
    type_bonus = 1.2 if _entity_type(term) in {"system", "acronym", "facility", "object"} else 1.0
    cross_page_bonus = 1.0 + min(0.5, page_count * 0.12)
    return base * type_bonus * cross_page_bonus


def build_entity_graph(pages: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
    page_terms: List[List[str]] = []
    page_nums: List[int] = []
    doc_freq: Counter[str] = Counter()

    for idx, page in enumerate(pages):
        pnum = int(page.get("page") or idx + 1)
        page_nums.append(pnum)
        terms = [t for t in _tokenize_terms(_page_text(page)) if t not in GENERIC_ENTITY_TERMS]
        page_terms.append(terms)
        for term in set(terms):
            doc_freq[term] += 1

    total_pages = max(1, len(pages))
    scored: Counter[str] = Counter()
    page_map: Dict[str, List[int]] = defaultdict(list)
    term_pages: Dict[str, set[int]] = defaultdict(set)

    for idx, terms in enumerate(page_terms):
        pnum = page_nums[idx]
        tf = Counter(terms)
        for term, count in tf.items():
            idf = math.log((total_pages + 1) / (doc_freq[term] + 1)) + 1.0
            scored[term] += _importance_score(term, float(count), idf, doc_freq[term])
            if pnum not in term_pages[term]:
                term_pages[term].add(pnum)
                page_map[term].append(pnum)

    cooccurrence: Dict[str, Counter[str]] = defaultdict(Counter)
    for terms in page_terms:
        unique = sorted(set(terms))
        for i, left in enumerate(unique):
            for right in unique[i + 1 :]:
                cooccurrence[left][right] += 1
                cooccurrence[right][left] += 1

    entities: List[Dict[str, Any]] = []
    for idx, (name, score) in enumerate(scored.most_common(10)):
        if score <= 0:
            continue
        if len(name) > 10 and _entity_type(name) == "entity":
            continue
        max_co = max(cooccurrence.get(name, Counter()).values(), default=0)
        importance = min(0.99, round(score / (score + 4.0) + min(0.25, max_co * 0.05), 2))
        relations = [
            other
            for other, count in cooccurrence.get(name, Counter()).most_common(3)
            if count >= 1
        ]
        entity_type = _entity_type(name)
        entities.append(
            {
                "id": f"entity_{idx + 1}",
                "name": name,
                "entity_type": entity_type,
                "importance": importance,
                "visual_anchor": _visual_anchor_for_entity(name, entity_type),
                "color_hint": "与全文档主色一致",
                "pages": sorted(page_map.get(name, [])),
                "frequency": int(round(score)),
                "relations": relations,
            }
        )
    return entities[:8], {e["name"]: e.get("relations") or [] for e in entities}


def _visual_anchor_for_entity(name: str, entity_type: str) -> str:
    if entity_type == "acronym":
        return f"{name} system module icon, flat vector, consistent design language"
    if entity_type == "facility":
        return f"{name}, control room or facility icon, flat vector infographic"
    if entity_type == "object":
        return f"{name}, object icon, side view where applicable, flat vector"
    if entity_type == "system":
        return f"{name}, layered system module blocks, flat vector cards"
    return f"{name}, flat vector illustration element, consistent design language"


def _page_focus_phrases(page: Dict[str, Any], max_items: int = 4) -> List[str]:
    phrases: List[str] = []
    topic = str(page.get("topic") or "").strip()
    if topic:
        phrases.append(topic)
    body = str(page.get("body") or "").strip()
    for chunk in re.split(r"[，,、；;\n]", body):
        chunk = chunk.strip()
        if not chunk or len(chunk) > 24:
            continue
        if chunk in phrases:
            continue
        phrases.append(chunk)
        if len(phrases) >= max_items:
            break
    return phrases


def _resolve_page_focus(page: Dict[str, Any], objects: Sequence[str]) -> str:
    topic = str(page.get("topic") or "").strip()
    if topic:
        return topic[:60]
    for name in objects:
        if name:
            return str(name)[:60]
    phrases = _page_focus_phrases(page, max_items=1)
    if phrases:
        return phrases[0][:60]
    return "main topic"


def plan_visual_spec(
    *,
    page: Dict[str, Any],
    topic_type: str,
    content_intent: str,
    page_role: str,
    entities: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    topic_meta = TOPIC_TYPES.get(topic_type, TOPIC_TYPES["concept_explanation"])
    intent_meta = CONTENT_INTENTS.get(content_intent, CONTENT_INTENTS["overview"])
    visual_type = topic_meta.get("visual") or intent_meta.get("visual") or "illustration"
    primitive = VISUAL_PRIMITIVES.get(visual_type, VISUAL_PRIMITIVES["illustration"])

    linked = [e for e in entities if int(page.get("page") or 0) in (e.get("pages") or [])]
    if not linked:
        text = _page_text(page)
        linked = [e for e in entities if e.get("name") and str(e["name"]) in text]
    linked = sorted(linked, key=lambda item: float(item.get("importance") or 0), reverse=True)[:4]
    objects = [str(e.get("name") or "") for e in linked if e.get("name")]

    focus = _resolve_page_focus(page, objects)
    layout = "centered" if page_role in {"overview", "summary"} else "left-to-right flow"

    return {
        "visual_type": visual_type,
        "topic_type": topic_type,
        "content_intent": content_intent,
        "page_role": page_role,
        "focus": focus[:60],
        "objects": objects,
        "layout": layout,
        "visual_primitives": [primitive],
        "importance_order": objects,
    }


def build_style_profile(pages: Sequence[Dict[str, Any]], topic_types: Sequence[str]) -> Dict[str, Any]:
    combined = "\n".join(_page_text(page) for page in pages)
    dominant_topic = Counter(topic_types).most_common(1)[0][0] if topic_types else "concept_explanation"
    label = TOPIC_TYPES.get(dominant_topic, {}).get("label_zh", "通用演示文档")

    color_theme = ["科技蓝", "白色", "浅灰"]
    if any(k in combined for k in ("医疗", "健康", "临床")):
        color_theme = ["青绿", "白色", "浅灰"]
    elif any(k in combined for k in ("金融", "商业", "市场")):
        color_theme = ["深蓝", "白色", "金色点缀"]
    elif any(k in combined for k in ("教育", "课程", "教学")):
        color_theme = ["蓝色", "白色", "浅橙点缀"]

    visual_density = "low" if len(combined) < 800 else "medium"
    tokens = [
        "minimal",
        "flat vector",
        "infographic",
        "consistent palette",
        TOPIC_TYPES.get(dominant_topic, {}).get("visual", "illustration"),
    ]

    return {
        "domain": label,
        "style_tokens": tokens[:8],
        "style_prompt_zh": (
            f"统一扁平矢量信息图风格，{'、'.join(color_theme[:2])} 为主色，"
            f"视觉密度{visual_density}，圆角图形，信息图风格，全篇一致"
        ),
        "color_palette": color_theme,
        "negative_style": (
            "禁止每页使用不同画风；禁止动漫风、写实照片风、赛博朋克与卡通混搭；"
            "避免长段可读文字与精确姓名/编号；全篇配色与扁平程度保持一致。"
        ),
        "color_theme": color_theme,
        "visual_density": visual_density,
        "illustration_style": "flat vector",
        "illustration_level": "flat",
        "shape_language": "rounded",
        "icon_style": "flat vector",
        "layout_style": "minimal",
        "render_style": "infographic",
    }


def build_slide_plans(
    pages: Sequence[Dict[str, Any]],
    entities: Sequence[Dict[str, Any]],
    slide_graph: Dict[int, List[int]],
) -> List[Dict[str, Any]]:
    plans: List[Dict[str, Any]] = []
    entity_by_id = {str(e.get("id")): e for e in entities}

    for idx, page in enumerate(pages):
        pnum = int(page.get("page") or idx + 1)
        text = _page_text(page)
        topic_type = classify_topic(text)
        content_intent = detect_intent(text)
        page_role = infer_page_role(
            idx, len(pages), text, content_intent=content_intent, topic_type=topic_type
        )
        spec = plan_visual_spec(
            page=page,
            topic_type=topic_type,
            content_intent=content_intent,
            page_role=page_role,
            entities=entities,
        )
        linked_ids = [
            e.get("id")
            for e in entities
            if e.get("id") and (pnum in (e.get("pages") or []) or str(e.get("name") or "") in text)
        ][:4]

        related_pages = slide_graph.get(pnum) or []
        focus_phrases = _page_focus_phrases(page)

        plans.append(
            {
                "page": pnum,
                "topic": str(page.get("topic") or ""),
                "slide_role": page_role,
                "visual_focus": " · ".join(focus_phrases[:4]) or spec.get("focus") or "",
                "entity_ids": linked_ids,
                "topic_type": topic_type,
                "content_intent": content_intent,
                "visual_type": spec.get("visual_type") or "",
                "page_role": page_role,
                "visual_primitives": spec.get("visual_primitives") or [],
                "focus": spec.get("focus") or "",
                "layout": spec.get("layout") or "",
                "related_pages": related_pages,
            }
        )

        _ = entity_by_id  # reserved for future relation-aware planning
    return plans


def analyze_document_structure(
    pages: Sequence[Dict[str, Any]],
    *,
    doc_title: str = "",
) -> Dict[str, Any]:
    if not pages:
        raise ValueError("文档页列表为空")

    from backend.services.consistency_controller import apply_consistency_controller

    slide_graph = build_slide_graph(pages)
    entities, _relations = build_entity_graph(pages)
    topic_types = [classify_topic(_page_text(page)) for page in pages]
    style = build_style_profile(pages, topic_types)
    slide_plans = build_slide_plans(pages, entities, slide_graph)

    consistency = apply_consistency_controller(
        style=style,
        entities=entities,
        slide_plans=slide_plans,
        pages=pages,
    )

    dominant = Counter(topic_types).most_common(1)[0][0] if topic_types else "concept_explanation"
    typed_graph = consistency.get("slide_graph") or {}
    return {
        "style": consistency.get("style") or style,
        "entities": consistency.get("entities") or entities,
        "slide_plans": consistency.get("slide_plans") or slide_plans,
        "slide_graph": typed_graph,
        "global_constraints": consistency.get("global_constraints") or "",
        "summary": (
            f"已理解 {len(pages)} 页：主 topic={TOPIC_TYPES.get(dominant, {}).get('label_zh', dominant)}，"
            f"抽取 {len(consistency.get('entities') or [])} 个实体，"
            f"建立 {len(typed_graph)} 个带关系类型的页面节点。"
        ),
        "source": "document_understanding+consistency_controller",
    }
