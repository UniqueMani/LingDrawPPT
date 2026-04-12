from typing import Any, Dict, List, Optional

from backend.services.chart_context import (
    grouped_y_axis_names,
    pie_values_are_share_percent,
    sniff_scale_hints,
    suggest_x_name_trend,
    suggest_y_name_for_simple_bar,
)


def _truncate_list(xs: List[Any], n: int = 10) -> List[Any]:
    if not xs:
        return []
    return xs[:n]


def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def generate_echarts_option(
    *,
    intent: str,
    chartType: str,
    topic: str,
    extracted: Dict[str, Any],
    context_text: str = "",
) -> Dict[str, Any]:
    """
    将语义识别结果映射到 ECharts option（用于前端直接渲染）。
    context_text：标题+正文+数据描述合并串，用于推断单位与轴名称。
    """
    title_text = (topic or "").strip() or "Visualization"
    hints = sniff_scale_hints(context_text)

    if chartType == "trend_line" or intent == "trend":
        x = _safe_list(extracted.get("x")) or []
        y = _safe_list(extracted.get("y")) or []
        # 修正长度不一致
        if len(x) != len(y):
            n = min(len(x), len(y))
            x = x[:n]
            y = y[:n]

        x = _truncate_list([str(i) for i in x], 12)
        y = _truncate_list([float(v) for v in y], 12)

        y_unit = (extracted.get("unit") or extracted.get("yUnit") or "").strip()
        y_name = y_unit if y_unit else suggest_y_name_for_simple_bar(hints, y)
        x_name = (extracted.get("xLabel") or "").strip() or suggest_x_name_trend(hints, x)
        ser_name = (extracted.get("seriesName") or "").strip() or y_name or "序列"

        return {
            "title": {
                "text": title_text,
                "left": "center",
                **({"subtext": "纵轴单位见坐标轴名称"} if hints.get("money_unit") else {}),
            },
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "line"}},
            "legend": {"data": [ser_name], "bottom": 6},
            "grid": {"left": "12%", "right": "10%", "bottom": "18%", "top": "22%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": x,
                "name": x_name,
                "nameLocation": "middle",
                "nameGap": 30,
                "axisLabel": {"interval": 0},
            },
            "yAxis": {
                "type": "value",
                "name": y_name,
                "nameLocation": "middle",
                "nameGap": 42,
                "splitLine": {"show": True, "lineStyle": {"type": "dashed", "opacity": 0.35}},
            },
            "series": [
                {
                    "name": ser_name,
                    "type": "line",
                    "smooth": True,
                    "data": y,
                    "symbolSize": 7,
                    "label": {"show": len(y) <= 10, "position": "top", "formatter": "{c}"},
                }
            ],
        }

    if chartType == "comparison_grouped":
        categories = [str(x) for x in _safe_list(extracted.get("categories"))]
        series_in = extracted.get("series") or []
        if not categories or not series_in:
            categories = categories or ["A", "B"]
            series_in = series_in or [{"name": "值", "values": [0, 0], "yAxisIndex": 0}]

        categories = _truncate_list(categories, 16)
        use_dual = any(int(s.get("yAxisIndex", 0) or 0) == 1 for s in series_in)

        row_n = len(categories)
        for s in series_in:
            row_n = min(row_n, len(_safe_list(s.get("values")) or []))
        if row_n < 1:
            row_n = 1
        categories = categories[:row_n]

        series_out: List[Dict[str, Any]] = []
        for s in series_in:
            name = str(s.get("name", "系列"))
            raw_vals = [float(v) for v in (_safe_list(s.get("values")) or [])][:row_n]
            while len(raw_vals) < row_n:
                raw_vals.append(0.0)
            y_idx = int(s.get("yAxisIndex", 0) or 0)
            series_out.append(
                {
                    "name": name,
                    "type": "bar",
                    "yAxisIndex": y_idx if use_dual else 0,
                    "data": raw_vals,
                    "barMaxWidth": 20,
                }
            )

        left_title, right_title = grouped_y_axis_names(hints, series_in)
        y_axes: List[Dict[str, Any]] = [
            {
                "type": "value",
                "name": left_title,
                "position": "left",
                "nameLocation": "middle",
                "nameGap": 48,
                "splitLine": {"show": True, "lineStyle": {"type": "dashed", "opacity": 0.3}},
            },
            {
                "type": "value",
                "name": right_title,
                "position": "right",
                "nameLocation": "middle",
                "nameGap": 40,
                "axisLabel": {"formatter": "{value}"},
                "splitLine": {"show": False},
            },
        ]
        single_y = [
            {
                "type": "value",
                "name": left_title,
                "nameLocation": "middle",
                "nameGap": 44,
                "splitLine": {"show": True, "lineStyle": {"type": "dashed", "opacity": 0.3}},
            }
        ]

        leg_data = [s["name"] for s in series_out]

        return {
            "title": {"text": title_text, "left": "center"},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {"type": "scroll", "bottom": 4, "data": leg_data},
            "grid": {
                "left": "11%",
                "right": use_dual and "13%" or "10%",
                "bottom": "20%",
                "top": "18%",
                "containLabel": True,
            },
            "xAxis": {
                "type": "category",
                "data": categories,
                "name": "类别",
                "nameLocation": "middle",
                "nameGap": 32,
                "axisLabel": {"interval": 0, "rotate": 20},
            },
            "yAxis": y_axes if use_dual else single_y,
            "series": [
                {
                    **s,
                    "label": {"show": row_n <= 6, "position": "top", "formatter": "{c}"},
                }
                for s in series_out
            ],
        }

    if chartType == "relation_sankey" or intent == "relation":
        nodes_raw = _safe_list(extracted.get("nodes"))
        links_raw = _safe_list(extracted.get("links"))
        nodes = [{"name": str(n)} for n in nodes_raw] if nodes_raw else []
        links: List[Dict[str, Any]] = []
        for lk in links_raw:
            if not isinstance(lk, dict):
                continue
            links.append(
                {
                    "source": str(lk.get("source", "")),
                    "target": str(lk.get("target", "")),
                    "value": float(lk.get("value", 0) or 0),
                }
            )
        links = links[:40]
        if len(nodes) < 2 and links:
            seen: set[str] = set()
            for lk in links:
                for k in ("source", "target"):
                    n = str(lk.get(k, ""))
                    if n and n not in seen:
                        seen.add(n)
                        nodes.append({"name": n})
        if len(links) < 1:
            links = [{"source": "A", "target": "B", "value": 1.0}]
        if len(nodes) < 2:
            nodes = [{"name": "A"}, {"name": "B"}]

        flow_name = "流量"
        if hints.get("money_unit"):
            flow_name = f"流量（{hints['money_unit']}）"
        return {
            "title": {"text": title_text, "left": "center"},
            "tooltip": {"trigger": "item", "formatter": "{b}: {c}"},
            "series": [
                {
                    "name": flow_name,
                    "type": "sankey",
                    "data": nodes[:30],
                    "links": links,
                    "emphasis": {"focus": "adjacency"},
                    "lineStyle": {"color": "gradient", "curveness": 0.5},
                    "label": {"color": "#334155", "fontSize": 11},
                }
            ],
        }

    if chartType == "data_table":
        return {
            "title": {"text": title_text, "left": "center"},
            "graphic": [
                {
                    "type": "text",
                    "left": "center",
                    "top": "48%",
                    "style": {
                        "text": "数据已解析为表格，见下方「结构化表格」",
                        "fill": "#94a3b8",
                        "fontSize": 14,
                    },
                }
            ],
        }

    if chartType == "comparison_bar" or (
        intent == "comparison" and chartType not in ("comparison_grouped", "data_table")
    ):
        labels = [str(x) for x in _safe_list(extracted.get("labels"))]
        values = _safe_list(extracted.get("values")) or []
        if len(labels) != len(values):
            n = min(len(labels), len(values))
            labels = labels[:n]
            values = values[:n]

        labels = _truncate_list(labels, 12)
        values = _truncate_list([float(v) for v in values], 12)

        y_name = suggest_y_name_for_simple_bar(hints, values)
        ser_name = (extracted.get("valueLabel") or extracted.get("seriesName") or "").strip() or "对比指标"

        return {
            "title": {"text": title_text, "left": "center"},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {"data": [ser_name], "bottom": 6},
            "grid": {"left": "11%", "right": "8%", "bottom": "20%", "top": "18%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": labels,
                "name": "类别",
                "nameLocation": "middle",
                "nameGap": 32,
                "axisLabel": {"interval": 0, "rotate": 22},
            },
            "yAxis": {
                "type": "value",
                "name": y_name,
                "nameLocation": "middle",
                "nameGap": 44,
                "splitLine": {"show": True, "lineStyle": {"type": "dashed", "opacity": 0.35}},
            },
            "series": [
                {
                    "name": ser_name,
                    "type": "bar",
                    "data": values,
                    "barMaxWidth": 42,
                    "label": {"show": len(values) <= 10, "position": "top", "formatter": "{c}"},
                }
            ],
        }

    if chartType == "proportion_pie" or intent == "proportion":
        labels = [str(x) for x in _safe_list(extracted.get("labels"))]
        values = _safe_list(extracted.get("values")) or []
        if len(labels) != len(values):
            n = min(len(labels), len(values))
            labels = labels[:n]
            values = values[:n]

        labels = _truncate_list(labels, 10)
        values = _truncate_list([float(v) for v in values], 10)
        data = [{"name": labels[i], "value": values[i]} for i in range(min(len(labels), len(values)))]

        as_percent = pie_values_are_share_percent(values)
        pct_hint = as_percent or hints.get("percent_semantic")
        pie_tooltip = "{b}: {c}（扇区占比 {d}%）"
        pie_label = {"show": True, "formatter": "{b}\n{c}%" if as_percent else "{b}\n{d}%"}

        return {
            "title": {"text": title_text, "left": "center", "subtext": "占比类图表：请确认各块为同一度量口径" if pct_hint else ""},
            "tooltip": {"trigger": "item", "formatter": pie_tooltip},
            "legend": {"type": "scroll", "orient": "vertical", "left": "left", "top": "middle"},
            "series": [
                {
                    "name": "构成",
                    "type": "pie",
                    "radius": ["38%", "68%"],
                    "center": ["58%", "52%"],
                    "avoidLabelOverlap": True,
                    "label": pie_label,
                    "labelLine": {"show": True},
                    "data": data,
                }
            ],
        }

    if chartType == "process_flow" or intent == "process":
        steps = [str(x) for x in _safe_list(extracted.get("steps"))]
        steps = _truncate_list(steps, 12)
        if len(steps) < 2:
            steps = steps or ["Step 1", "Step 2"]

        nodes = [{"id": i, "name": s} for i, s in enumerate(steps)]
        links = [{"source": i, "target": i + 1} for i in range(len(steps) - 1)]

        return {
            "title": {"text": title_text, "left": "center"},
            "tooltip": {"formatter": "{b}"},
            "series": [
                {
                    "name": "流程步骤",
                    "type": "graph",
                    "layout": "force",
                    "roam": True,
                    "label": {"show": True, "position": "right"},
                    "edgeSymbol": ["none", "arrow"],
                    "edgeSymbolSize": 10,
                    "force": {"repulsion": 800, "gravity": 0.1, "layoutAnimation": True},
                    "data": nodes,
                    "links": links,
                }
            ],
        }

    if chartType == "hierarchy_tree" or intent == "hierarchy":
        chain = [str(x) for x in _safe_list(extracted.get("chain"))]
        chain = _truncate_list(chain, 10)
        if len(chain) < 1:
            chain = ["Root"]

        # 把 chain 转成 tree series 数据结构（单链嵌套 children）
        root: Dict[str, Any] = {"name": chain[0]}
        cur = root
        for name in chain[1:]:
            nxt: Dict[str, Any] = {"name": name}
            cur["children"] = [nxt]
            cur = nxt

        return {
            "title": {"text": title_text, "left": "center"},
            "tooltip": {"trigger": "item", "triggerOn": "mousemove", "formatter": "{b}"},
            "series": [
                {
                    "name": "层级",
                    "type": "tree",
                    "data": [root],
                    "top": "10%",
                    "left": "8%",
                    "bottom": "10%",
                    "right": "28%",
                    "symbolSize": 10,
                    "orient": "LR",
                    "label": {
                        "position": "left",
                        "verticalAlign": "middle",
                        "align": "right",
                    },
                    "leaves": {"label": {"position": "right", "verticalAlign": "middle", "align": "left"}},
                }
            ],
        }

    # fallback
    return {
        "title": {"text": title_text, "left": "center"},
        "series": [{"type": "line", "data": []}],
    }

