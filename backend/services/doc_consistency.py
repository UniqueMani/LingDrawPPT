from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from backend.config import DEEPSEEK_API_KEY, USE_DEEPSEEK
from backend.services.consistency_controller import build_prompt_from_consistency
from backend.services.document_understanding import analyze_document_structure


def analyze_document(
    pages: List[Dict[str, Any]],
    *,
    doc_title: str = "",
) -> Dict[str, Any]:
    result = analyze_document_structure(pages, doc_title=doc_title)
    return _try_deepseek_enrich(pages, result)


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
            f"第{p.get('page')}页 标题:{p.get('topic', '')} 摘要:{str(p.get('body', ''))[:200]}"
        )
    prompt = (
        "你是PPT视觉总监。根据以下多页大纲，输出JSON："
        '{"style_prompt_zh":"","style_tokens":[],"entities":[{"name":"","visual_anchor":"","pages":[]}],'
        '"slide_plans":[{"page":1,"topic_type":"","content_intent":"","visual_type":"","visual_focus":"","entity_names":[]}]} '
        "要求：按 topic_type 与 content_intent 规划每页视觉；entities 为跨页共享实体且 visual_anchor 各页一致。只输出JSON。\n"
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
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return base
        data = json.loads(match.group(0))
        if data.get("style_prompt_zh"):
            base["style"]["style_prompt_zh"] = str(data["style_prompt_zh"])
        if isinstance(data.get("style_tokens"), list) and data["style_tokens"]:
            base["style"]["style_tokens"] = [str(x) for x in data["style_tokens"][:8]]

        entity_lookup = {str(e.get("name")): e for e in base.get("entities") or []}
        if isinstance(data.get("entities"), list) and data["entities"]:
            merged = []
            for i, item in enumerate(data["entities"][:8]):
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                prev = entity_lookup.get(name, {})
                merged.append(
                    {
                        "id": prev.get("id") or f"entity_{i + 1}",
                        "name": name,
                        "entity_type": prev.get("entity_type") or "",
                        "importance": prev.get("importance") or 0.0,
                        "visual_anchor": str(
                            item.get("visual_anchor") or prev.get("visual_anchor") or name
                        ),
                        "color_hint": prev.get("color_hint") or "与全文档主色一致",
                        "pages": item.get("pages")
                        if isinstance(item.get("pages"), list)
                        else prev.get("pages") or [],
                        "frequency": prev.get("frequency") or 1,
                        "relations": prev.get("relations") or [],
                    }
                )
            if merged:
                base["entities"] = merged

        plan_lookup = {int(p.get("page") or 0): p for p in base.get("slide_plans") or []}
        if isinstance(data.get("slide_plans"), list) and data["slide_plans"]:
            for item in data["slide_plans"]:
                if not isinstance(item, dict):
                    continue
                page = int(item.get("page") or 0)
                if page not in plan_lookup:
                    continue
                plan = plan_lookup[page]
                if item.get("topic_type"):
                    plan["topic_type"] = str(item["topic_type"])
                if item.get("content_intent"):
                    plan["content_intent"] = str(item["content_intent"])
                if item.get("visual_type"):
                    plan["visual_type"] = str(item["visual_type"])
                if item.get("visual_focus"):
                    plan["visual_focus"] = str(item["visual_focus"])

        base["source"] = "deepseek+consistency_controller"
    except Exception:
        pass
    return base


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
    return build_prompt_from_consistency(
        style=style,
        slide_plan=slide_plan,
        entities=entities,
        use_doc_style=use_doc_style,
        use_entity_sync=use_entity_sync,
    )
