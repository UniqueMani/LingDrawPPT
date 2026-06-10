from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

_MAX_SUFFIX_CHARS = 480

PAGE_ROLE_GUIDANCE: Dict[str, str] = {
    "overview": "wide scene, low detail, structural overview layout",
    "detail": "focused zoom, module breakdown, moderate detail",
    "process": "step flow, directional arrows, sequential left-to-right layout",
    "case": "scenario illustration, contextual scene, moderate detail",
    "summary": "minimal recap, key highlights only, low visual density",
    "transition": "section divider, simple visual bridge, minimal elements",
}

RELATION_GUIDANCE: Dict[str, str] = {
    "overview_to_detail": "inherit overview focus, zoom into subsystem modules",
    "detail_to_process": "extend prior module into workflow steps",
    "detail_to_metric": "extend prior detail into metrics and data panels",
    "process_to_metric": "flow from process steps into outcome metrics",
    "overview_to_metric": "connect high-level structure to key metrics",
    "sequential": "continue narrative thread from previous page",
}

NAMED_PRIMITIVES: Dict[str, str] = {
    "architecture_block": "architecture_block, layered modules, flat vector",
    "train_object": "train_object, consistent side-view train icon, flat vector",
    "workflow_arrow": "workflow_arrow, directional process connectors, flat vector",
    "signal_icon": "signal_icon, signal equipment glyph, flat vector",
    "dashboard_panel": "dashboard_panel, metric cards and chart blocks, flat vector",
    "station_icon": "station_icon, platform station glyph, flat vector",
    "control_room": "control_room, large display wall, flat vector",
    "comparison_bar": "comparison_bar, side-by-side panels, flat vector",
    "timeline_node": "timeline_node, milestone markers, flat vector",
    "concept_icon": "concept_icon, explanatory glyph, flat vector",
}

VISUAL_TYPE_PRIMITIVES: Dict[str, List[str]] = {
    "architecture": ["architecture_block"],
    "flowchart": ["workflow_arrow"],
    "chart": ["dashboard_panel"],
    "line_chart": ["dashboard_panel"],
    "comparison": ["comparison_bar"],
    "timeline": ["timeline_node"],
    "illustration": ["concept_icon"],
    "relationship_map": ["architecture_block", "workflow_arrow"],
    "hierarchy": ["architecture_block"],
    "overview": ["architecture_block"],
    "mechanism": ["concept_icon", "workflow_arrow"],
}

ENTITY_PRIMITIVE_HINTS: Dict[str, List[str]] = {
    "object": ["train_object"],
    "facility": ["control_room"],
    "acronym": ["architecture_block", "control_room"],
    "system": ["architecture_block"],
}


def build_global_style_constraints(style: Dict[str, Any]) -> str:
    color_theme = style.get("color_theme") or style.get("color_palette") or []
    palette = "/".join(str(x) for x in color_theme[:3] if x)
    illustration = str(
        style.get("illustration_style") or style.get("illustration_level") or style.get("icon_style") or "flat vector"
    ).strip()
    density = str(style.get("visual_density") or "low").strip()
    shape = str(style.get("shape_language") or "rounded").strip()
    layout = str(style.get("layout_style") or "minimal").strip()
    render_style = str(style.get("render_style") or "infographic").strip()
    domain = str(style.get("domain") or "general").strip()

    parts = [
        f"domain={domain}",
        f"palette={palette}" if palette else "",
        f"illustration={illustration}",
        f"density={density}",
        f"shape={shape}",
        f"layout={layout}",
        f"render={render_style}",
    ]
    return "; ".join(p for p in parts if p)


def build_page_role_constraints(page_role: str) -> str:
    guidance = PAGE_ROLE_GUIDANCE.get(page_role, PAGE_ROLE_GUIDANCE["detail"])
    return f"role={page_role}; {guidance}"


def _resolve_primitives(
    visual_type: str,
    entities: Sequence[Dict[str, Any]],
    deck_primitives: Set[str],
) -> List[str]:
    chosen: List[str] = []
    for key in VISUAL_TYPE_PRIMITIVES.get(visual_type, ["concept_icon"]):
        if key not in chosen:
            chosen.append(key)
    for entity in entities[:3]:
        entity_type = str(entity.get("entity_type") or "")
        for key in ENTITY_PRIMITIVE_HINTS.get(entity_type, []):
            if key not in chosen:
                chosen.append(key)
    for key in deck_primitives:
        if key not in chosen and len(chosen) < 4:
            chosen.append(key)
    return chosen[:4]


def _primitive_descriptions(keys: Sequence[str]) -> List[str]:
    return [NAMED_PRIMITIVES[key] for key in keys if key in NAMED_PRIMITIVES]


def _infer_edge_relation(
    from_plan: Dict[str, Any],
    to_plan: Dict[str, Any],
) -> str:
    from_role = str(from_plan.get("page_role") or from_plan.get("slide_role") or "")
    to_role = str(to_plan.get("page_role") or to_plan.get("slide_role") or "")
    from_topic = str(from_plan.get("topic_type") or "")
    to_topic = str(to_plan.get("topic_type") or "")

    if from_role == "overview" and to_role in {"detail", "process"}:
        return "overview_to_detail"
    if from_topic == "system_architecture" and to_topic == "workflow":
        return "detail_to_process"
    if from_topic == "workflow" and to_topic == "data_analysis":
        return "process_to_metric"
    if to_topic == "data_analysis":
        return "detail_to_metric"
    if from_role == "overview" and to_topic == "data_analysis":
        return "overview_to_metric"
    return "sequential"


def build_typed_slide_graph(
    pages: Sequence[Dict[str, Any]],
    slide_plans: Sequence[Dict[str, Any]],
) -> Dict[int, List[Dict[str, Any]]]:
    plan_by_page = {int(p.get("page") or 0): p for p in slide_plans}
    page_nums = [int(p.get("page") or idx + 1) for idx, p in enumerate(pages)]
    graph: Dict[int, List[Dict[str, Any]]] = {}

    for idx, pnum in enumerate(page_nums):
        edges: List[Dict[str, Any]] = []
        from_plan = plan_by_page.get(pnum) or {}
        if idx + 1 < len(page_nums):
            target = page_nums[idx + 1]
            to_plan = plan_by_page.get(target) or {}
            relation = _infer_edge_relation(from_plan, to_plan)
            edges.append({"target": target, "relation": relation})
        role = str(from_plan.get("page_role") or from_plan.get("slide_role") or "")
        if role == "overview" and idx + 2 < len(page_nums):
            target = page_nums[idx + 2]
            if not any(edge.get("target") == target for edge in edges):
                to_plan = plan_by_page.get(target) or {}
                edges.append(
                    {
                        "target": target,
                        "relation": _infer_edge_relation(from_plan, to_plan),
                    }
                )
        graph[pnum] = edges
    return graph


def _find_predecessor(page_num: int, typed_graph: Dict[int, List[Dict[str, Any]]]) -> Optional[int]:
    for source, edges in typed_graph.items():
        for edge in edges:
            if int(edge.get("target") or 0) == page_num:
                return int(source)
    return None


def _inherit_context(
    page_num: int,
    typed_graph: Dict[int, List[Dict[str, Any]]],
    plan_by_page: Dict[int, Dict[str, Any]],
) -> Tuple[str, str]:
    predecessor = _find_predecessor(page_num, typed_graph)
    if not predecessor:
        return "", ""
    prev_plan = plan_by_page.get(predecessor) or {}
    relation = "sequential"
    for edge in typed_graph.get(predecessor, []):
        if int(edge.get("target") or 0) == page_num:
            relation = str(edge.get("relation") or "sequential")
            break
    inherited_focus = str(prev_plan.get("focus") or prev_plan.get("topic") or "").strip()
    guidance = RELATION_GUIDANCE.get(relation, RELATION_GUIDANCE["sequential"])
    return inherited_focus, guidance


def merge_entity_aliases(entities: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not entities:
        return []

    canonical: List[Dict[str, Any]] = []
    for entity in entities:
        name = str(entity.get("name") or "").strip()
        if not name:
            continue
        merged_into: Optional[Dict[str, Any]] = None
        for existing in canonical:
            existing_name = str(existing.get("name") or "")
            if name == existing_name:
                merged_into = existing
                break
            if name in existing_name or existing_name in name:
                merged_into = existing
                break
            if entity.get("entity_type") == "acronym" and name in existing_name:
                merged_into = existing
                break
            if existing.get("entity_type") == "acronym" and existing_name in name:
                merged_into = existing
                break

        if merged_into is None:
            canonical.append(dict(entity))
            continue

        merged_pages = sorted(set((merged_into.get("pages") or []) + (entity.get("pages") or [])))
        merged_into["pages"] = merged_pages
        merged_into["frequency"] = int(merged_into.get("frequency") or 0) + int(entity.get("frequency") or 0)
        merged_into["importance"] = max(
            float(merged_into.get("importance") or 0),
            float(entity.get("importance") or 0),
        )
        merged_relations = list(
            dict.fromkeys((merged_into.get("relations") or []) + (entity.get("relations") or []))
        )
        merged_into["relations"] = merged_relations[:5]
        if float(entity.get("importance") or 0) >= float(merged_into.get("importance") or 0):
            if entity.get("visual_anchor"):
                merged_into["visual_anchor"] = entity["visual_anchor"]
        if entity.get("entity_type") == "acronym" and len(name) <= len(str(merged_into.get("name") or "")):
            merged_into["name"] = name

    for idx, entity in enumerate(canonical):
        entity["id"] = f"entity_{idx + 1}"
    return canonical[:8]


def apply_consistency_controller(
    *,
    style: Dict[str, Any],
    entities: Sequence[Dict[str, Any]],
    slide_plans: Sequence[Dict[str, Any]],
    pages: Sequence[Dict[str, Any]],
    typed_slide_graph: Optional[Dict[int, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    merged_entities = merge_entity_aliases(entities)
    entity_by_id = {str(e.get("id")): e for e in merged_entities}
    global_constraints = build_global_style_constraints(style)
    typed_graph = typed_slide_graph or build_typed_slide_graph(pages, slide_plans)
    plan_by_page = {int(p.get("page") or 0): dict(p) for p in slide_plans}

    deck_primitives: Set[str] = set()
    enriched_plans: List[Dict[str, Any]] = []

    for plan in slide_plans:
        page_num = int(plan.get("page") or 0)
        page_plan = dict(plan_by_page.get(page_num) or plan)
        linked_entities = [
            entity_by_id[eid]
            for eid in (page_plan.get("entity_ids") or [])
            if eid in entity_by_id
        ]
        if not linked_entities:
            text = f"{page_plan.get('topic') or ''} {page_plan.get('visual_focus') or ''}"
            linked_entities = [
                e for e in merged_entities if str(e.get("name") or "") in text
            ][:3]

        visual_type = str(page_plan.get("visual_type") or "illustration")
        page_role = str(page_plan.get("page_role") or page_plan.get("slide_role") or "detail")
        primitive_keys = _resolve_primitives(visual_type, linked_entities, deck_primitives)
        deck_primitives.update(primitive_keys)
        primitive_text = _primitive_descriptions(primitive_keys)

        inherited_focus, relation_guidance = _inherit_context(page_num, typed_graph, plan_by_page)
        page_constraints = build_page_role_constraints(page_role)
        if relation_guidance:
            page_constraints += f"; inherit={inherited_focus[:30]}" if inherited_focus else ""
            page_constraints += f"; {relation_guidance}"

        entity_names = [str(e.get("name") or "") for e in linked_entities if e.get("name")]
        entity_anchors = [str(e.get("visual_anchor") or "") for e in linked_entities if e.get("visual_anchor")]

        visual_spec = {
            "focus": str(page_plan.get("focus") or page_plan.get("topic") or "")[:60],
            "entities": entity_names[:4],
            "entity_anchors": entity_anchors[:3],
            "style": global_constraints,
            "primitives": primitive_keys,
            "primitive_descriptions": primitive_text,
            "page_role": page_role,
            "visual_type": visual_type,
            "layout": str(page_plan.get("layout") or ""),
            "inherited_focus": inherited_focus[:40] if inherited_focus else "",
        }

        page_plan["visual_primitives"] = primitive_text or page_plan.get("visual_primitives") or []
        page_plan["primitive_keys"] = primitive_keys
        page_plan["global_constraints"] = global_constraints
        page_plan["page_constraints"] = page_constraints
        page_plan["related_pages"] = [int(edge.get("target") or 0) for edge in typed_graph.get(page_num, [])]
        page_plan["visual_spec"] = visual_spec
        page_plan["entity_ids"] = [e.get("id") for e in linked_entities if e.get("id")][:4]
        enriched_plans.append(page_plan)

    return {
        "style": style,
        "entities": merged_entities,
        "slide_plans": enriched_plans,
        "slide_graph": typed_graph,
        "global_constraints": global_constraints,
    }


def build_prompt_from_consistency(
    *,
    style: Optional[Dict[str, Any]] = None,
    slide_plan: Optional[Dict[str, Any]] = None,
    entities: Optional[List[Dict[str, Any]]] = None,
    use_doc_style: bool = True,
    use_entity_sync: bool = True,
) -> str:
    """从 Consistency Controller 输出构建压缩 Prompt 后缀。"""
    sections: List[str] = []
    visual_spec = (slide_plan or {}).get("visual_spec") or {}

    if use_doc_style:
        global_line = str((slide_plan or {}).get("global_constraints") or "").strip()
        if not global_line and style:
            global_line = build_global_style_constraints(style)
        if global_line:
            sections.append(f"[Document Style] {global_line}")

    if use_entity_sync and slide_plan:
        page_line = str(slide_plan.get("page_constraints") or "").strip()
        if not page_line:
            page_role = str(slide_plan.get("page_role") or slide_plan.get("slide_role") or "detail")
            page_line = build_page_role_constraints(page_role)
        topic_bits = "/".join(
            bit
            for bit in (
                slide_plan.get("topic_type"),
                slide_plan.get("content_intent"),
                slide_plan.get("visual_type"),
            )
            if bit
        )
        focus = str(visual_spec.get("focus") or slide_plan.get("focus") or slide_plan.get("topic") or "")[:40]
        if topic_bits or focus:
            page_line += f"; page={topic_bits or 'illustration'}"
            if focus:
                page_line += f"; focus={focus}"
        inherited = str(visual_spec.get("inherited_focus") or "").strip()
        if inherited:
            page_line += f"; prev={inherited[:30]}"
        sections.append(f"[Current Page] {page_line}")

        primitives = visual_spec.get("primitive_descriptions") or slide_plan.get("visual_primitives") or []
        if primitives:
            sections.append(f"[Visual Rules] {'; '.join(str(x) for x in primitives[:3])}")

    if use_entity_sync and entities:
        names = [str(e.get("name") or "") for e in entities[:3] if e.get("name")]
        anchors = [str(e.get("visual_anchor") or "") for e in entities[:2] if e.get("visual_anchor")]
        if names:
            sections.append(f"[Entities] {', '.join(names)}")
        if anchors:
            sections.append(f"[Anchors] {'; '.join(anchors)}")

    if use_doc_style and style:
        negative = str(style.get("negative_style") or "").strip()
        if negative:
            sections.append(f"[Avoid] {negative.replace('；', '; ').replace('。', '')[:120]}")

    suffix = "\n".join(sections).strip()
    if len(suffix) > _MAX_SUFFIX_CHARS:
        suffix = suffix[: _MAX_SUFFIX_CHARS - 3].rstrip() + "..."
    return suffix
