from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from backend.config import DEEPSEEK_API_KEY, USE_DEEPSEEK
from backend.services.preprocessor import extract_simple_keywords

# 领域 → 默认全文档风格倾向
_DOMAIN_STYLE: Dict[str, Dict[str, Any]] = {
    "rail": {
        "domain": "轨道交通/高铁系统",
        "style_tokens": ["minimal", "blue theme", "flat design", "tech infographic"],
        "style_prompt_zh": "简约扁平矢量信息图，科技蓝与白为主色，专业轨道交通主题",
        "color_palette": ["科技蓝", "白色", "浅灰"],
    },
    "tech": {
        "domain": "科技与信息系统",
        "style_tokens": ["minimal", "blue theme", "flat vector", "clean layout"],
        "style_prompt_zh": "现代扁平矢量科技风，蓝白配色，简洁专业",
        "color_palette": ["蓝色", "白色", "浅蓝灰"],
    },
    "business": {
        "domain": "商业演示",
        "style_tokens": ["minimal", "corporate", "flat design", "neutral palette"],
        "style_prompt_zh": "商务简约扁平风，中性色搭配少量强调色",
        "color_palette": ["深灰", "白色", "强调蓝"],
    },
    "general": {
        "domain": "通用演示文档",
        "style_tokens": ["minimal", "flat design", "consistent palette", "infographic"],
        "style_prompt_zh": "统一简约扁平矢量信息图风格，配色一致、布局清晰",
        "color_palette": ["主色一致", "浅灰背景", "白色"],
    },
}

_DOMAIN_HINTS: List[Tuple[str, str]] = [
    ("高铁", "rail"),
    ("铁路", "rail"),
    ("列车", "rail"),
    ("轨道", "rail"),
    ("调度", "rail"),
    ("信号", "rail"),
    ("科技", "tech"),
    ("系统", "tech"),
    ("平台", "tech"),
    ("数据", "tech"),
    ("算法", "tech"),
    ("商业", "business"),
    ("市场", "business"),
    ("战略", "business"),
]

_ROLE_RULES: List[Tuple[str, str, str]] = [
    (r"总体|整体|架构|概览|总览|结构图|系统结构", "总体结构图", "展示系统整体架构与模块关系"),
    (r"调度|控制|指挥|运营中心|控制中心", "调度/控制中心", "控制室或调度中心场景，屏幕与监控界面"),
    (r"信号|通信|联调|接口|传输", "信号/通信系统", "信号设备、通信链路或接口示意"),
    (r"安全|防护|监测|告警", "安全监测", "安全防护或监测示意"),
    (r"数据|分析|指标|统计", "数据洞察", "数据看板或指标可视化元素"),
]

_ENTITY_SUFFIXES = ("系统", "中心", "平台", "模块", "网络", "列车", "信号", "结构", "服务", "设备")

_VISUAL_ANCHORS: Dict[str, str] = {
    "列车": "modern high-speed train, white body with blue stripe, side view, flat vector",
    "高铁": "modern high-speed train, white body with blue stripe, side view, flat vector",
    "调度中心": "control room with large screens, operators silhouettes, blue UI glow, flat vector",
    "控制中心": "control room with large screens, operators silhouettes, blue UI glow, flat vector",
    "信号系统": "railway signal towers and track schematic, flat infographic icons",
    "信号": "railway signal equipment icons, flat vector",
    "结构": "layered system architecture diagram blocks, flat vector",
    "平台": "layered software platform modules, flat vector cards",
}


def _detect_domain(combined: str) -> str:
    text = combined.lower()
    scores: Counter[str] = Counter()
    for hint, key in _DOMAIN_HINTS:
        if hint in combined or hint.lower() in text:
            scores[key] += 1
    if scores:
        return scores.most_common(1)[0][0]
    return "general"


def _pick_style_profile(domain_key: str, keywords: List[str]) -> Dict[str, Any]:
    base = dict(_DOMAIN_STYLE.get(domain_key, _DOMAIN_STYLE["general"]))
    tokens = list(base.get("style_tokens") or [])
    for kw in keywords[:4]:
        token = kw.strip()
        if token and token not in tokens and len(token) <= 12:
            tokens.append(token)
    base["style_tokens"] = tokens[:8]
    base["negative_style"] = (
        "禁止每页使用不同画风；禁止动漫风、写实照片风、赛博朋克与卡通混搭；"
        "禁止可读文字与 Logo；全篇配色与扁平程度保持一致。"
    )
    return base


def _infer_slide_role(topic: str, body: str) -> Tuple[str, str]:
    text = f"{topic} {body}"
    for pattern, role, focus in _ROLE_RULES:
        if re.search(pattern, text):
            return role, focus
    if topic.strip():
        return "主题配图", f"突出「{topic.strip()[:40]}」相关示意"
    return "内容配图", "与正文要点一致的信息图示意"


def _entity_visual_anchor(name: str) -> str:
    for key, anchor in _VISUAL_ANCHORS.items():
        if key in name:
            return anchor
    if name.endswith(_ENTITY_SUFFIXES):
        return f"{name} infographic icon set, flat vector, consistent with document style"
    return f"{name}, flat vector illustration element, consistent design language"


def _extract_entities(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counter: Counter[str] = Counter()
    page_map: Dict[str, List[int]] = {}

    for page in pages:
        pnum = int(page.get("page") or 0)
        topic = str(page.get("topic") or "")
        body = str(page.get("body") or "")
        text = f"{topic} {body}"
        for kw in extract_simple_keywords(text, max_items=12):
            if len(kw) < 2:
                continue
            counter[kw] += 1
            page_map.setdefault(kw, [])
            if pnum and pnum not in page_map[kw]:
                page_map[kw].append(pnum)

        for m in re.findall(r"[\u4e00-\u9fa5]{2,8}(?:系统|中心|平台|模块|网络|列车|信号|结构)", text):
            counter[m] += 2
            page_map.setdefault(m, [])
            if pnum and pnum not in page_map[m]:
                page_map[m].append(pnum)

    entities: List[Dict[str, Any]] = []
    ranked = counter.most_common(12)
    for idx, (name, freq) in enumerate(ranked):
        if freq < 1:
            continue
        if name in {"内容", "页面", "系统介绍", "概述", "说明"}:
            continue
        eid = f"entity_{idx + 1}"
        entities.append(
            {
                "id": eid,
                "name": name,
                "visual_anchor": _entity_visual_anchor(name),
                "color_hint": "与全文档主色一致",
                "pages": sorted(page_map.get(name, [])),
                "frequency": freq,
            }
        )
    return entities[:8]


def _build_slide_plans(
    pages: List[Dict[str, Any]], entities: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    plans: List[Dict[str, Any]] = []
    for page in pages:
        pnum = int(page.get("page") or 0)
        topic = str(page.get("topic") or "")
        body = str(page.get("body") or "")
        role, focus = _infer_slide_role(topic, body)
        text = f"{topic} {body}"
        linked = [e["id"] for e in entities if e["name"] in text or (pnum and pnum in e.get("pages", []))]
        if not linked and topic:
            linked = [entities[0]["id"]] if entities else []
        plans.append(
            {
                "page": pnum,
                "topic": topic,
                "slide_role": role,
                "visual_focus": focus,
                "entity_ids": linked[:4],
            }
        )
    return plans


def _try_deepseek_enrich(pages: List[Dict[str, Any]], base: Dict[str, Any]) -> Dict[str, Any]:
    if not USE_DEEPSEEK or not DEEPSEEK_API_KEY:
        return base
    try:
        from openai import OpenAI
    except Exception:
        return base

    outline = []
    for p in pages[:20]:
        outline.append(
            f"第{p.get('page')}页 标题:{p.get('topic','')} 摘要:{str(p.get('body',''))[:200]}"
        )
    prompt = (
        "你是PPT视觉总监。根据以下多页大纲，输出JSON："
        '{"domain":"","style_tokens":[],"style_prompt_zh":"","entities":[{"name":"","visual_anchor":"","pages":[]}],'
        '"slide_plans":[{"page":1,"slide_role":"","visual_focus":"","entity_names":[]}]} '
        "要求：全文档统一扁平矢量信息图风格；entities为跨页共享视觉实体；"
        "visual_anchor用英文描述且各页一致。只输出JSON。\n"
        + "\n".join(outline)
    )
    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return base
        data = json.loads(m.group(0))
        if data.get("style_prompt_zh"):
            base["style"]["style_prompt_zh"] = str(data["style_prompt_zh"])
        if isinstance(data.get("style_tokens"), list) and data["style_tokens"]:
            base["style"]["style_tokens"] = [str(x) for x in data["style_tokens"][:8]]
        if isinstance(data.get("entities"), list) and data["entities"]:
            merged = []
            for i, item in enumerate(data["entities"][:8]):
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                merged.append(
                    {
                        "id": f"entity_{i + 1}",
                        "name": name,
                        "visual_anchor": str(item.get("visual_anchor") or _entity_visual_anchor(name)),
                        "color_hint": "与全文档主色一致",
                        "pages": item.get("pages") if isinstance(item.get("pages"), list) else [],
                        "frequency": 1,
                    }
                )
            if merged:
                base["entities"] = merged
        base["source"] = "deepseek+rules"
    except Exception:
        pass
    return base


def analyze_document(
    pages: List[Dict[str, Any]],
    *,
    doc_title: str = "",
) -> Dict[str, Any]:
    if not pages:
        raise ValueError("文档页列表为空")

    combined_parts = [doc_title] if doc_title else []
    for p in pages:
        combined_parts.append(str(p.get("topic") or ""))
        combined_parts.append(str(p.get("body") or ""))
    combined = "\n".join(combined_parts)

    domain_key = _detect_domain(combined)
    keywords = extract_simple_keywords(combined, max_items=10)
    style = _pick_style_profile(domain_key, keywords)
    entities = _extract_entities(pages)
    slide_plans = _build_slide_plans(pages, entities)

    result = {
        "style": style,
        "entities": entities,
        "slide_plans": slide_plans,
        "summary": (
            f"已分析 {len(pages)} 页：领域「{style.get('domain')}」，"
            f"抽取 {len(entities)} 个共享实体，统一风格 token {len(style.get('style_tokens', []))} 项。"
        ),
        "source": "rules",
    }
    return _try_deepseek_enrich(pages, result)


def get_slide_plan(slide_plans: List[Dict[str, Any]], page: int) -> Optional[Dict[str, Any]]:
    for plan in slide_plans:
        if int(plan.get("page") or 0) == page:
            return plan
    if slide_plans and page <= len(slide_plans):
        return slide_plans[page - 1]
    return None


def resolve_entities_for_plan(
    entities: List[Dict[str, Any]], plan: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if not plan:
        return entities[:3]
    ids = set(plan.get("entity_ids") or [])
    picked = [e for e in entities if e.get("id") in ids]
    return picked or entities[:3]


def build_consistency_prompt_suffix(
    *,
    style: Optional[Dict[str, Any]] = None,
    slide_plan: Optional[Dict[str, Any]] = None,
    entities: Optional[List[Dict[str, Any]]] = None,
    use_doc_style: bool = True,
    use_entity_sync: bool = True,
) -> str:
    parts: List[str] = []
    if use_doc_style and style:
        tokens = style.get("style_tokens") or []
        if tokens:
            parts.append(f"全文档统一 style tokens：{', '.join(tokens)}。")
        prompt_zh = str(style.get("style_prompt_zh") or "").strip()
        if prompt_zh:
            parts.append(f"统一视觉风格：{prompt_zh}。")
        palette = style.get("color_palette") or []
        if palette:
            parts.append(f"配色约束：{'、'.join(palette)}，全篇一致。")
        negative = str(style.get("negative_style") or "").strip()
        if negative:
            parts.append(negative)

    if use_entity_sync and slide_plan:
        role = str(slide_plan.get("slide_role") or "").strip()
        focus = str(slide_plan.get("visual_focus") or "").strip()
        if role:
            parts.append(f"本页在多页叙事中的角色：{role}。")
        if focus:
            parts.append(f"画面重点：{focus}。")

    if use_entity_sync and entities:
        anchors = [str(e.get("visual_anchor") or "") for e in entities if e.get("visual_anchor")]
        names = [str(e.get("name") or "") for e in entities if e.get("name")]
        if names:
            parts.append(f"共享实体库（跨页视觉一致）：{'、'.join(names)}。")
        if anchors:
            parts.append(f"实体视觉锚点：{'；'.join(anchors[:4])}。")

    return "".join(parts)
