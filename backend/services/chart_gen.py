from typing import Any, Dict, List, Optional


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
) -> Dict[str, Any]:
    """
    将语义识别结果映射到 ECharts option（用于前端直接渲染）。
    """
    title_text = (topic or "").strip() or "Visualization"

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

        return {
            "title": {"text": title_text, "left": "center"},
            "tooltip": {"trigger": "axis"},
            "grid": {"left": "8%", "right": "8%", "bottom": "12%"},
            "xAxis": {"type": "category", "data": x, "axisLabel": {"interval": 0}},
            "yAxis": {"type": "value"},
            "series": [
                {
                    "name": "value",
                    "type": "line",
                    "smooth": True,
                    "data": y,
                    "symbolSize": 6,
                }
            ],
        }

    if chartType == "comparison_bar" or intent == "comparison":
        labels = [str(x) for x in _safe_list(extracted.get("labels"))]
        values = _safe_list(extracted.get("values")) or []
        if len(labels) != len(values):
            n = min(len(labels), len(values))
            labels = labels[:n]
            values = values[:n]

        labels = _truncate_list(labels, 12)
        values = _truncate_list([float(v) for v in values], 12)

        return {
            "title": {"text": title_text, "left": "center"},
            "tooltip": {"trigger": "axis"},
            "grid": {"left": "10%", "right": "6%", "bottom": "18%"},
            "xAxis": {
                "type": "category",
                "data": labels,
                "axisLabel": {"interval": 0, "rotate": 20},
            },
            "yAxis": {"type": "value"},
            "series": [
                {
                    "name": "value",
                    "type": "bar",
                    "data": values,
                    "barMaxWidth": 40,
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

        return {
            "title": {"text": title_text, "left": "center"},
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "legend": {"top": "10%"},
            "series": [
                {
                    "name": "比例",
                    "type": "pie",
                    "radius": ["35%", "70%"],
                    "center": ["50%", "55%"],
                    "avoidLabelOverlap": True,
                    "label": {"show": True, "formatter": "{b}"},
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
            "tooltip": {},
            "series": [
                {
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
            "tooltip": {"trigger": "item", "triggerOn": "mousemove"},
            "series": [
                {
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

