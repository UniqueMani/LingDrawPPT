"""
通用可视化决策引擎（与具体业务场景解耦）。

思路：
1. 结构特征（features）：从文本中抽取与「是否像趋势/构成/流程/表格/流向」相关的可计算信号，而非手写 if-else 穷举场景。
2. 意图评分（scoring）：对各 intent 加权打分，取最高分；置信度低时保守落到「简单柱状对比」。
3. 生成 extracted：在既定 chartType 下调用已有解析器填数。
4. 校验归一化（validate）：修正数组错位、饼图误用、非法 chartType 等，LLM 与规则共用同一套闸门。

说明：「完美」在开放文本上不可达；本模块目标是可解释、可扩展的通用骨架，便于接论文中的准确率实验与后续换更强 LLM。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from backend.services.preprocessor import (
    _parse_row_metric_pairs,
    extract_entity_metric_blocks,
    grid_to_grouped_series_extracted,
    parse_entity_metric_grid,
    parse_hierarchy_chain,
    parse_label_value_pairs,
    parse_percent_map,
    parse_steps,
    parse_time_series,
)

# --- 结构特征 -----------------------------------------------------------------

_TIME_HINT = re.compile(
    r"(?:19|20)\d{2}\s*年|年|月|季度|Q[1-4]|趋势|逐年|增长|下降|变化|走势|同比|环比",
    re.I,
)
_COMPARE_HINT = re.compile(r"对比|比较|vs\.?|相比|排名|差异|高低", re.I)
_FLOW_HINT = re.compile(r"流程|步骤|阶段|环节|->|→|=>")
_HIER_HINT = re.compile(r"层级|组织|架构|树|上下级|层次|隶属")
_PART_WHOLE_HINT = re.compile(r"占比|构成|份额|比例分布|市场份额|收入结构|饼图")
_TABLE_HINT = re.compile(r"表格|一览表|矩阵|对照表|明细表")
_SANKEY_HINT = re.compile(r"桑基|流向|迁移|漏斗|从.+到|来源|去向|转化")


def _parse_sankey_links(text: str) -> Optional[Dict[str, Any]]:
    """
    轻量「源→目标→数值」抽取，覆盖常见中文叙述；至少 2 条边才认为可用桑基图。
    """
    text = text or ""
    links: List[Dict[str, Any]] = []
    # A到B：100 / A至B 100
    for m in re.finditer(
        r"([\u4e00-\u9fa5A-Za-z0-9·\-]{1,16})[到至→]\s*([\u4e00-\u9fa5A-Za-z0-9·\-]{1,16})\s*[：:，,]?\s*(\d+(?:\.\d+)?)",
        text,
    ):
        s, t, v = m.group(1).strip(), m.group(2).strip(), float(m.group(3))
        if s and t and v > 0:
            links.append({"source": s, "target": t, "value": v})
    if len(links) < 2:
        return None
    nodes: List[str] = []
    seen = set()
    for lk in links:
        for n in (lk["source"], lk["target"]):
            if n not in seen:
                seen.add(n)
                nodes.append(n)
    return {"nodes": nodes, "links": links[:24]}


def extract_features(combined: str) -> Dict[str, Any]:
    text = combined or ""
    grid = parse_entity_metric_grid(text)
    pct = parse_percent_map(text)
    pct_labels = [p[0].strip() for p in pct]
    pct_sum = sum(p[1] for p in pct) if pct else 0.0
    lv = parse_label_value_pairs(text)
    tx, ty = parse_time_series(text)
    steps = parse_steps(text)
    chain = parse_hierarchy_chain(text)
    blocks = extract_entity_metric_blocks(text)
    single_entity_multi_metric = False
    if len(blocks) == 1:
        mdict = _parse_row_metric_pairs(blocks[0][1])
        single_entity_multi_metric = len(mdict) >= 2

    sankey = _parse_sankey_links(text)

    return {
        "text": text,
        "has_grid": grid is not None,
        "grid": grid,
        "percent_count": len(pct),
        "percent_sum": pct_sum,
        "percent_dup_labels": len(pct_labels) != len(set(pct_labels)),
        "label_value_count": len(lv),
        "time_x_len": len(tx),
        "time_y_len": len(ty),
        "steps_len": len(steps),
        "hierarchy_len": len(chain),
        "entity_block_count": len(blocks),
        "single_entity_multi_metric": single_entity_multi_metric,
        "has_time_hint": bool(_TIME_HINT.search(text)),
        "has_compare_hint": bool(_COMPARE_HINT.search(text)),
        "has_flow_hint": bool(_FLOW_HINT.search(text)),
        "has_hier_hint": bool(_HIER_HINT.search(text)),
        "has_part_whole_hint": bool(_PART_WHOLE_HINT.search(text)),
        "has_table_hint": bool(_TABLE_HINT.search(text)),
        "has_sankey_hint": bool(_SANKEY_HINT.search(text)),
        "sankey": sankey,
    }


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_intents(f: Dict[str, Any]) -> Tuple[str, str, float, Dict[str, float]]:
    """
    返回 (intent, chartType, confidence, score_breakdown)
    intent 使用上层已有枚举：trend|comparison|proportion|process|hierarchy|relation
    """
    s: Dict[str, float] = {}

    # 流程
    s["process"] = 0.0
    if f["steps_len"] >= 2:
        s["process"] += 0.55
    if f["has_flow_hint"]:
        s["process"] += 0.35
    s["process"] = _clamp(s["process"])

    # 层级
    s["hierarchy"] = 0.0
    if f["hierarchy_len"] >= 3:
        s["hierarchy"] += 0.6
    if f["has_hier_hint"] and f["hierarchy_len"] >= 2:
        s["hierarchy"] += 0.3
    s["hierarchy"] = _clamp(s["hierarchy"])

    # 关系 / 流向（桑基）
    s["relation"] = 0.0
    if f["sankey"]:
        s["relation"] += 0.75
    if f["has_sankey_hint"]:
        s["relation"] += 0.25
    s["relation"] = _clamp(s["relation"])

    # 趋势
    s["trend"] = 0.0
    if f["time_x_len"] >= 2 and f["time_y_len"] >= 2:
        s["trend"] += 0.65
    if f["has_time_hint"] and f["time_x_len"] >= 2:
        s["trend"] += 0.25
    if f["has_time_hint"] and f["label_value_count"] == 0 and f["percent_count"] == 0:
        s["trend"] += 0.1
    s["trend"] = _clamp(s["trend"])

    # 占比（饼图）— 严格：无实体网格、无重复标签、合计接近 100 或有明确构成语义
    s["proportion"] = 0.0
    if not f["has_grid"] and f["percent_count"] >= 2 and not f["percent_dup_labels"]:
        if 85 <= f["percent_sum"] <= 115:
            s["proportion"] += 0.85
        elif f["has_part_whole_hint"] and f["percent_sum"] <= 120:
            s["proportion"] += 0.55
        elif f["percent_count"] >= 2:
            s["proportion"] += 0.15
    s["proportion"] = _clamp(s["proportion"])

    # 对比（简单柱）
    s["comparison"] = 0.0
    if f["label_value_count"] >= 2:
        s["comparison"] += 0.45
    if f["has_compare_hint"]:
        s["comparison"] += 0.25
    if f["single_entity_multi_metric"]:
        s["comparison"] += 0.15
    if not f["has_grid"] and f["entity_block_count"] >= 2:
        s["comparison"] += 0.2
    s["comparison"] = _clamp(s["comparison"])

    # 互斥衰减：有明确网格时压饼图
    if f["has_grid"]:
        s["proportion"] *= 0.05

    winner = max(s, key=s.get)
    top = s[winner]
    second = sorted(s.values(), reverse=True)[1] if len(s) > 1 else 0.0
    margin = top - second
    confidence = _clamp(0.35 + margin * 1.2 + top * 0.35)

    chart_map = {
        "trend": "trend_line",
        "comparison": "comparison_bar",
        "proportion": "proportion_pie",
        "process": "process_flow",
        "hierarchy": "hierarchy_tree",
        "relation": "relation_sankey",
    }
    chart_type = chart_map.get(winner, "comparison_bar")

    # 低置信：保守柱状，避免乱折线/空饼
    if top < 0.28 and winner in ("trend", "proportion", "relation"):
        winner = "comparison"
        chart_type = "comparison_bar"
        confidence = 0.25

    return winner, chart_type, confidence, s


def grid_to_table_extracted(grid: Dict[str, Any]) -> Dict[str, Any]:
    cats = grid.get("categories") or []
    metrics = grid.get("metrics") or []
    matrix = grid.get("matrix") or []
    columns = ["类别"] + [str(m) for m in metrics]
    rows: List[List[Any]] = []
    for i, c in enumerate(cats):
        row: List[Any] = [c]
        if i < len(matrix):
            row.extend(matrix[i])
        else:
            row.extend([None] * len(metrics))
        rows.append(row)
    return {"columns": columns, "rows": rows}


def _build_extracted(intent: str, chart_type: str, combined: str, f: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    reason_extra = ""
    if chart_type == "relation_sankey" and f.get("sankey"):
        sk = f["sankey"]
        return (
            {"nodes": sk["nodes"], "links": sk["links"]},
            "检测到多组「来源→去向→数值」式流向描述，使用桑基图展示转移关系。",
        )
    if intent == "trend":
        x, y = parse_time_series(combined)
        return ({"x": x, "y": y, "unit": ""}, "基于时间维度与数值序列，使用折线图展示趋势。")
    if intent == "comparison":
        pairs = parse_label_value_pairs(combined)
        labels = [p[0] for p in pairs][:8]
        values = [p[1] for p in pairs][:8]
        return ({"labels": labels, "values": values}, "基于多类别-数值对，使用柱状图进行对比。")
    if intent == "proportion":
        pairs = parse_percent_map(combined)
        labels = [p[0] for p in pairs][:8]
        values = [p[1] for p in pairs][:8]
        return ({"labels": labels, "values": values}, "百分比构成满足单一整体语义校验，使用饼图展示比例。")
    if intent == "process":
        steps = parse_steps(combined)
        return ({"steps": steps[:10]}, "检测到步骤或流程结构，使用流程图展示。")
    if intent == "hierarchy":
        chain = parse_hierarchy_chain(combined)
        return ({"chain": chain[:10]}, "检测到层级链，使用树图展示。")
    return ({}, reason_extra)


def rule_based_visualization(combined: str) -> Dict[str, Any]:
    """无 LLM 的统一入口。"""
    f = extract_features(combined)

    if f["has_grid"] and f["grid"]:
        grid = f["grid"]
        if f["has_table_hint"]:
            ext = grid_to_table_extracted(grid)
            return {
                "intent": "comparison",
                "chartType": "data_table",
                "extracted": ext,
                "reason": "类表格多实体多指标数据，按语义偏好输出为表格；亦可改用分组柱状图对比。",
                "confidence": 0.92,
                "scores": {},
            }
        ext = grid_to_grouped_series_extracted(grid)
        return {
            "intent": "comparison",
            "chartType": "comparison_grouped",
            "extracted": ext,
            "reason": "结构特征：多实体×多指标（网格解析）。分组柱状图 + 双轴区分绝对量与百分比，避免误用饼图。",
            "confidence": 0.95,
            "scores": {},
        }

    intent, chart_type, conf, scores = score_intents(f)
    extracted, reason = _build_extracted(intent, chart_type, combined, f)

    # 关系类但抽边失败 → 降级对比
    if chart_type == "relation_sankey" and not extracted.get("links"):
        intent, chart_type = "comparison", "comparison_bar"
        extracted, reason = _build_extracted(intent, chart_type, combined, f)
        conf = min(conf, 0.4)

    # 兜底空数据
    if intent in ("trend", "comparison", "proportion") and not extracted:
        if intent == "trend":
            extracted = {"x": [], "y": []}
        else:
            extracted = {"labels": [], "values": []}

    out = {
        "intent": intent,
        "chartType": chart_type,
        "extracted": extracted,
        "reason": reason + f"（规则置信度约 {conf:.0%}）",
        "confidence": conf,
        "scores": scores,
    }
    return validate_and_normalize(out, combined)


_CHART_ALIASES = {
    "bar": "comparison_bar",
    "line": "trend_line",
    "pie": "proportion_pie",
    "sankey": "relation_sankey",
    "table": "data_table",
    "grouped_bar": "comparison_grouped",
}


def validate_and_normalize(sem: Dict[str, Any], combined: str) -> Dict[str, Any]:
    """
    统一校验 LLM 与规则输出：字段补全、饼图误用修正、chartType 别名、数组对齐。
    """
    grid = parse_entity_metric_grid(combined)
    intent = str(sem.get("intent") or "comparison")
    chart_type = str(sem.get("chartType") or "").strip()
    extracted = sem.get("extracted")
    if not isinstance(extracted, dict):
        extracted = {}
    reason = str(sem.get("reason") or "")

    chart_type = _CHART_ALIASES.get(chart_type, chart_type)

    valid_types = {
        "trend_line",
        "comparison_bar",
        "comparison_grouped",
        "proportion_pie",
        "process_flow",
        "hierarchy_tree",
        "relation_sankey",
        "data_table",
    }
    if chart_type not in valid_types:
        chart_type = "comparison_bar"

    # 饼图：重复标签或网格文本 → 强制改为分组柱或表格
    if chart_type == "proportion_pie":
        pct = parse_percent_map(combined)
        labels = [p[0] for p in pct]
        pct_sum = sum(p[1] for p in pct) if pct else 0.0
        bad_pie = (
            grid is not None
            or (labels and len(labels) != len(set(labels)))
            or (
                pct
                and not (75 <= pct_sum <= 125)
                and not _PART_WHOLE_HINT.search(combined or "")
            )
        )
        if bad_pie and grid:
            extracted = grid_to_grouped_series_extracted(grid)
            chart_type = "comparison_grouped"
            intent = "comparison"
            reason = (reason + "；[校验] 饼图语义不成立，已改为分组柱状图。").strip("；")
        elif bad_pie:
            chart_type = "comparison_bar"
            intent = "comparison"
            pairs = parse_label_value_pairs(combined)
            extracted = {"labels": [p[0] for p in pairs][:8], "values": [p[1] for p in pairs][:8]}
            reason = (reason + "；[校验] 饼图不适用，已改为柱状对比。").strip("；")

    # 趋势：对齐 x/y
    if chart_type == "trend_line":
        x = extracted.get("x") if isinstance(extracted.get("x"), list) else []
        y = extracted.get("y") if isinstance(extracted.get("y"), list) else []
        n = min(len(x), len(y))
        extracted = {**extracted, "x": x[:n], "y": y[:n]}

    # 简单对比：对齐 labels/values
    if chart_type == "comparison_bar":
        lb = extracted.get("labels") if isinstance(extracted.get("labels"), list) else []
        vl = extracted.get("values") if isinstance(extracted.get("values"), list) else []
        n = min(len(lb), len(vl))
        extracted = {**extracted, "labels": lb[:n], "values": vl[:n]}

    # 分组柱：对齐 categories 与每条 series.values
    if chart_type == "comparison_grouped":
        cats = extracted.get("categories") if isinstance(extracted.get("categories"), list) else []
        series = extracted.get("series") if isinstance(extracted.get("series"), list) else []
        row_n = len(cats)
        for s in series:
            if isinstance(s, dict) and isinstance(s.get("values"), list):
                row_n = min(row_n, len(s["values"]))
        if row_n < 1:
            row_n = 1
        cats = cats[:row_n]
        new_series = []
        for s in series:
            if not isinstance(s, dict):
                continue
            vals = s.get("values") if isinstance(s.get("values"), list) else []
            vals = [float(v) for v in vals][:row_n]
            while len(vals) < row_n:
                vals.append(0.0)
            new_series.append({**s, "values": vals})
        extracted = {**extracted, "categories": cats, "series": new_series}

    # 表格：columns + rows
    if chart_type == "data_table":
        cols = extracted.get("columns") if isinstance(extracted.get("columns"), list) else []
        rows = extracted.get("rows") if isinstance(extracted.get("rows"), list) else []
        if not cols or not rows:
            if grid:
                extracted = grid_to_table_extracted(grid)
            else:
                chart_type = "comparison_bar"
                intent = "comparison"
                pairs = parse_label_value_pairs(combined)
                extracted = {"labels": [p[0] for p in pairs][:8], "values": [p[1] for p in pairs][:8]}

    # 桑基：nodes + links
    if chart_type == "relation_sankey":
        links = extracted.get("links") if isinstance(extracted.get("links"), list) else []
        if len(links) < 2:
            fallback = _parse_sankey_links(combined)
            if fallback:
                extracted = {"nodes": fallback["nodes"], "links": fallback["links"]}
            else:
                chart_type = "comparison_bar"
                intent = "comparison"
                pairs = parse_label_value_pairs(combined)
                extracted = {"labels": [p[0] for p in pairs][:8], "values": [p[1] for p in pairs][:8]}

    sem = {**sem, "intent": intent, "chartType": chart_type, "extracted": extracted, "reason": reason}
    # scores 等非标准字段可保留给调试
    return sem


# --- Stability overrides ----------------------------------------------------
# Keep the public entry points but use stricter, readable rules for the current
# platform iteration.

_TIME_HINT_STABLE = re.compile(r"(?:趋势|逐年|年度|年份|月份|季度|时间序列|变化|增长|下降|NPS|(?:19|20)\d{2})", re.I)
_COMPARE_HINT_STABLE = re.compile(r"(?:对比|比较|排名|评分|增长率|转化率|同比|环比|conversion rate|vs\.?)", re.I)
_PART_WHOLE_HINT_STABLE = re.compile(r"(?:占比|构成|份额|市场份额|比例分布|收入结构|合计\s*100|同一.*整体|整体.*构成)", re.I)
_NOT_PART_WHOLE_STABLE = re.compile(r"(?:不是.*份额|不是.*占比|不是.*构成|增长率|转化率|同比|环比|conversion rate)", re.I)
_TABLE_HINT_STABLE = re.compile(r"(?:表格|矩阵|不要转成图表|明细表|对照表)", re.I)
_SANKEY_HINT_STABLE = re.compile(r"(?:流向|分配|再分配|来源|去向|迁移|转移|预算|Sankey|桑基)", re.I)
_HIER_HINT_STABLE = re.compile(r"(?:层级|组织|架构|下设|隶属|上下级|层级链)", re.I)
_PROCESS_HINT_STABLE = re.compile(r"(?:流程|步骤|依次|经过|环节)", re.I)


def _parse_sankey_links(text: str) -> Optional[Dict[str, Any]]:
    text = text or ""
    links: List[Dict[str, Any]] = []
    for m in re.finditer(
        r"([^\s,，;；:：=\-]+)\s*(?:\-\>|=>)\s*([^\s,，;；:：=\-]+)\s*[:=]\s*(-?\d+(?:\.\d+)?)",
        text,
    ):
        links.append({"source": m.group(1).strip(), "target": m.group(2).strip(), "value": float(m.group(3))})

    root_match = re.search(r"([^\s,，;；:：=\-]+)预算\d+(?:\.\d+)?(?:万元|元)?流向(.+?)(?:；|;|。|$)", text)
    if root_match:
        root = root_match.group(1)
        for target, value in re.findall(r"([^\d\s,，;；:：=\-]+)(\d+(?:\.\d+)?)(?:万元|元)?", root_match.group(2)):
            links.append({"source": root.strip("、，, "), "target": target.strip("、，, "), "value": float(value)})

    reallocate_match = re.search(r"([^\s,，;；:：=\-]+)再分配给(.+?)(?:；|;|。|$)", text)
    if reallocate_match:
        source = reallocate_match.group(1)
        for target, value in re.findall(r"([^\d\s,，;；:：=\-]+)(\d+(?:\.\d+)?)(?:万元|元)?", reallocate_match.group(2)):
            links.append({"source": source.strip("、，, "), "target": target.strip("、，, "), "value": float(value)})

    deduped: List[Dict[str, Any]] = []
    seen_edges: set[Tuple[str, str, float]] = set()
    for link in links:
        key = (link["source"], link["target"], float(link["value"]))
        if key not in seen_edges and link["source"] and link["target"] and link["value"] > 0:
            seen_edges.add(key)
            deduped.append(link)
    if len(deduped) < 2:
        return None
    nodes: List[str] = []
    for link in deduped:
        for name in (link["source"], link["target"]):
            if name not in nodes:
                nodes.append(name)
    return {"nodes": nodes, "links": deduped[:40]}


def grid_to_table_extracted(grid: Dict[str, Any]) -> Dict[str, Any]:
    categories = grid.get("categories") or []
    metrics = grid.get("metrics") or []
    matrix = grid.get("matrix") or []
    columns = ["类别"] + [str(m) for m in metrics]
    rows: List[List[Any]] = []
    for idx, category in enumerate(categories):
        row: List[Any] = [category]
        row.extend(matrix[idx] if idx < len(matrix) else [None] * len(metrics))
        rows.append(row)
    return {"columns": columns, "rows": rows}


def _parse_explicit_table(text: str) -> Optional[Dict[str, Any]]:
    text = text or ""
    col_match = re.search(r"(?:表格列|列)\s*[:：]\s*(.+?)(?:；|;|\n|$)", text)
    if not col_match:
        return None
    columns = [c.strip() for c in re.split(r"[,，、]", col_match.group(1)) if c.strip()]
    if len(columns) < 2:
        return None
    tail = text[col_match.end() :]
    row_chunks = re.split(r"；|;", tail)
    rows: List[List[Any]] = []
    for chunk in row_chunks:
        chunk = re.sub(r"^\s*行\s*[:：]\s*", "", chunk.strip())
        if not chunk:
            continue
        cells = [c.strip().rstrip("。") for c in re.split(r"[,，、]", chunk) if c.strip()]
        if len(cells) >= len(columns):
            row: List[Any] = []
            for cell in cells[: len(columns)]:
                row.append(float(cell) if re.fullmatch(r"-?\d+(?:\.\d+)?", cell) else cell)
            rows.append(row)
    return {"columns": columns, "rows": rows} if rows else None


def extract_features(combined: str) -> Dict[str, Any]:
    text = combined or ""
    grid = parse_entity_metric_grid(text)
    pct = parse_percent_map(text)
    tx, ty = parse_time_series(text)
    lv = parse_label_value_pairs(text)
    steps = parse_steps(text)
    chain = parse_hierarchy_chain(text)
    sankey = _parse_sankey_links(text)
    pct_labels = [label for label, _ in pct]
    return {
        "text": text,
        "grid": grid,
        "has_grid": grid is not None,
        "percent_count": len(pct),
        "percent_sum": sum(value for _, value in pct) if pct else 0.0,
        "percent_dup_labels": len(pct_labels) != len(set(pct_labels)),
        "label_value_count": len(lv),
        "time_x_len": len(tx),
        "time_y_len": len(ty),
        "steps_len": len(steps),
        "hierarchy_len": len(chain),
        "has_time_hint": bool(_TIME_HINT_STABLE.search(text)),
        "has_compare_hint": bool(_COMPARE_HINT_STABLE.search(text)),
        "has_part_whole_hint": bool(_PART_WHOLE_HINT_STABLE.search(text)),
        "has_not_part_whole_hint": bool(_NOT_PART_WHOLE_STABLE.search(text)),
        "has_table_hint": bool(_TABLE_HINT_STABLE.search(text)),
        "has_sankey_hint": bool(_SANKEY_HINT_STABLE.search(text)),
        "has_process_hint": bool(_PROCESS_HINT_STABLE.search(text)),
        "has_hier_hint": bool(_HIER_HINT_STABLE.search(text)),
        "sankey": sankey,
    }


def score_intents(f: Dict[str, Any]) -> Tuple[str, str, float, Dict[str, float]]:
    scores = {k: 0.0 for k in ("trend", "comparison", "proportion", "process", "hierarchy", "relation")}
    if f["time_x_len"] >= 2 and f["time_y_len"] >= 2:
        scores["trend"] += 0.75
    if f["has_time_hint"] and f["time_x_len"] >= 2:
        scores["trend"] += 0.2
    if f["label_value_count"] >= 2:
        scores["comparison"] += 0.55
    if f["has_compare_hint"]:
        scores["comparison"] += 0.25
    if f["percent_count"] >= 2 and not f["percent_dup_labels"] and not f["has_not_part_whole_hint"]:
        if 90 <= f["percent_sum"] <= 110:
            scores["proportion"] += 0.75
        if f["has_part_whole_hint"]:
            scores["proportion"] += 0.25
    if f["steps_len"] >= 2 and f["has_process_hint"] and not f["sankey"]:
        scores["process"] += 0.8
    if f["has_hier_hint"] and f["hierarchy_len"] >= 2:
        scores["hierarchy"] += 0.85
    if f["sankey"]:
        scores["relation"] += 0.9
    if f["has_sankey_hint"] and f["sankey"]:
        scores["relation"] += 0.1

    winner = max(scores, key=scores.get)
    top = scores[winner]
    second = sorted(scores.values(), reverse=True)[1]
    confidence = _clamp(0.4 + (top - second) * 0.8 + top * 0.25)
    chart_type = {
        "trend": "trend_line",
        "comparison": "comparison_bar",
        "proportion": "proportion_pie",
        "process": "process_flow",
        "hierarchy": "hierarchy_tree",
        "relation": "relation_sankey",
    }.get(winner, "comparison_bar")
    if top < 0.25:
        winner, chart_type, confidence = "comparison", "comparison_bar", 0.25
    return winner, chart_type, confidence, scores


def _build_extracted(intent: str, chart_type: str, combined: str, f: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    if chart_type == "relation_sankey" and f.get("sankey"):
        return f["sankey"], "检测到多条来源到目标的数值流向，使用桑基图展示关系。"
    if chart_type == "trend_line":
        x, y = parse_time_series(combined)
        return {"x": x, "y": y, "unit": ""}, "检测到时间维度与指标值，使用折线图展示趋势。"
    if chart_type == "comparison_bar":
        pairs = parse_label_value_pairs(combined)
        return {"labels": [p[0] for p in pairs][:12], "values": [p[1] for p in pairs][:12]}, "检测到多类别数值对，使用柱状图进行对比。"
    if chart_type == "proportion_pie":
        pairs = parse_percent_map(combined)
        return {"labels": [p[0] for p in pairs][:10], "values": [p[1] for p in pairs][:10]}, "检测到同一整体的构成比例，使用饼图展示占比。"
    if chart_type == "process_flow":
        return {"steps": parse_steps(combined)[:12]}, "检测到明确流程步骤，使用流程图展示。"
    if chart_type == "hierarchy_tree":
        return {"chain": parse_hierarchy_chain(combined)[:10]}, "检测到层级链路，使用树图展示。"
    return {}, ""


def rule_based_visualization(combined: str) -> Dict[str, Any]:
    f = extract_features(combined)

    if f["has_table_hint"]:
        explicit_table = _parse_explicit_table(combined)
        extracted = explicit_table or (grid_to_table_extracted(f["grid"]) if f["grid"] else {
            "columns": ["项目", "数值"],
            "rows": [[label, value] for label, value in parse_label_value_pairs(combined)],
        })
        return validate_and_normalize({"intent": "comparison", "chartType": "data_table", "extracted": extracted, "reason": "检测到显式表格或矩阵需求，优先输出结构化表格。", "confidence": 0.95, "scores": {}, "warnings": []}, combined)

    if f["sankey"]:
        return validate_and_normalize({"intent": "relation", "chartType": "relation_sankey", "extracted": f["sankey"], "reason": "检测到多条数值流向，优先输出桑基图。", "confidence": 0.95, "scores": {}, "warnings": []}, combined)

    if f["grid"]:
        return validate_and_normalize({"intent": "comparison", "chartType": "comparison_grouped", "extracted": grid_to_grouped_series_extracted(f["grid"]), "reason": "检测到多实体多指标结构，输出分组柱状图。", "confidence": 0.95, "scores": {}, "warnings": []}, combined)

    intent, chart_type, confidence, scores = score_intents(f)
    extracted, reason = _build_extracted(intent, chart_type, combined, f)
    return validate_and_normalize({"intent": intent, "chartType": chart_type, "extracted": extracted, "reason": f"{reason}（规则置信度约 {confidence:.0%}）", "confidence": confidence, "scores": scores, "warnings": []}, combined)


def validate_and_normalize(sem: Dict[str, Any], combined: str) -> Dict[str, Any]:
    grid = parse_entity_metric_grid(combined)
    intent = str(sem.get("intent") or "comparison")
    chart_type = _CHART_ALIASES.get(str(sem.get("chartType") or "").strip(), str(sem.get("chartType") or "").strip())
    extracted = sem.get("extracted") if isinstance(sem.get("extracted"), dict) else {}
    reason = str(sem.get("reason") or "")
    warnings = list(sem.get("warnings") or [])

    if chart_type not in {"trend_line", "comparison_bar", "comparison_grouped", "proportion_pie", "process_flow", "hierarchy_tree", "relation_sankey", "data_table"}:
        chart_type = "comparison_bar"
        intent = "comparison"
        warnings.append("未知 chartType 已回退为 comparison_bar")

    if chart_type == "proportion_pie":
        pairs = parse_percent_map(combined)
        labels = [p[0] for p in pairs]
        total = sum(p[1] for p in pairs) if pairs else 0
        bad_pie = grid is not None or bool(_NOT_PART_WHOLE_STABLE.search(combined or "")) or len(labels) != len(set(labels)) or (pairs and not (75 <= total <= 125) and not _PART_WHOLE_HINT_STABLE.search(combined or ""))
        if bad_pie:
            intent, chart_type = "comparison", "comparison_bar"
            pairs2 = parse_label_value_pairs(combined) or pairs
            extracted = {"labels": [p[0] for p in pairs2][:12], "values": [p[1] for p in pairs2][:12]}
            reason += " [校验] 百分比不满足同一整体构成，已改为柱状对比。"
            warnings.append("百分比数据未按饼图处理")

    if chart_type == "trend_line":
        x = extracted.get("x") if isinstance(extracted.get("x"), list) else []
        y = extracted.get("y") if isinstance(extracted.get("y"), list) else []
        if len(x) < 2 or len(y) < 2:
            x, y = parse_time_series(combined)
        n = min(len(x), len(y))
        extracted = {**extracted, "x": x[:n], "y": y[:n]}

    if chart_type == "comparison_bar":
        labels = extracted.get("labels") if isinstance(extracted.get("labels"), list) else []
        values = extracted.get("values") if isinstance(extracted.get("values"), list) else []
        if len(labels) < 2 or len(values) < 2:
            pairs = parse_label_value_pairs(combined)
            labels, values = [p[0] for p in pairs], [p[1] for p in pairs]
        n = min(len(labels), len(values))
        extracted = {**extracted, "labels": labels[:n], "values": values[:n]}

    if chart_type == "comparison_grouped":
        if (not extracted.get("categories") or not extracted.get("series")) and grid:
            extracted = grid_to_grouped_series_extracted(grid)
        categories = extracted.get("categories") if isinstance(extracted.get("categories"), list) else []
        series = extracted.get("series") if isinstance(extracted.get("series"), list) else []
        row_n = len(categories)
        for item in series:
            if isinstance(item, dict) and isinstance(item.get("values"), list):
                row_n = min(row_n, len(item["values"]))
        categories = categories[:row_n]
        normalized_series = []
        for item in series:
            if isinstance(item, dict):
                vals = item.get("values") if isinstance(item.get("values"), list) else []
                normalized_series.append({**item, "values": [float(v) for v in vals[:row_n]]})
        extracted = {**extracted, "categories": categories, "series": normalized_series}

    if chart_type == "data_table":
        cols = extracted.get("columns") if isinstance(extracted.get("columns"), list) else []
        rows = extracted.get("rows") if isinstance(extracted.get("rows"), list) else []
        if not cols or not rows:
            explicit_table = _parse_explicit_table(combined)
            extracted = explicit_table or (grid_to_table_extracted(grid) if grid else {"columns": ["项目", "数值"], "rows": [[label, value] for label, value in parse_label_value_pairs(combined)]})

    if chart_type == "relation_sankey":
        links = extracted.get("links") if isinstance(extracted.get("links"), list) else []
        if len(links) < 2:
            fallback = _parse_sankey_links(combined)
            if fallback:
                extracted = fallback
            else:
                intent, chart_type = "comparison", "comparison_bar"
                pairs = parse_label_value_pairs(combined)
                extracted = {"labels": [p[0] for p in pairs], "values": [p[1] for p in pairs]}
                warnings.append("桑基图流向不足，已回退为柱状图")

    return {**sem, "intent": intent, "chartType": chart_type, "extracted": extracted, "reason": reason, "warnings": warnings}
