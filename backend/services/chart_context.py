"""
从幻灯片合并文本中推断单位、轴语义，用于 ECharts 坐标轴名、图例与 tooltip 文案，
提升「数据映射可读性」与信息表达完整性（不涉及图像模型路线）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def merge_slide_context(topic: str, body: Optional[str], data_description: Optional[str]) -> str:
    parts = [topic or "", (body or "").strip(), (data_description or "").strip()]
    return " ".join(p for p in parts if p).strip()


def sniff_scale_hints(text: str) -> Dict[str, Any]:
    """从叙述中抓取常见单位与「是否百分比语义」。"""
    t = text or ""
    money_unit = ""
    if "亿元" in t:
        money_unit = "亿元"
    elif "万美元" in t or "万美金" in t:
        money_unit = "万美元"
    elif "万元" in t or "万块" in t or "万人" in t:
        # 「万人」更像计数；优先万元用于金额类指标
        if re.search(r"营收|收入|销售|金额|成本|费用|利润|产值|预算", t):
            money_unit = "万元"
        elif "万元" in t:
            money_unit = "万元"
    elif re.search(r"(?<![万亿])元(?![器件])", t) and "万" not in t[: min(len(t), 80)]:
        pass

    count_suffix = ""
    for suf in ("万件", "万辆", "万台", "万人", "家", "个"):
        if suf in t:
            count_suffix = suf
            break

    percent_semantic = bool(
        re.search(r"(?:%|％|百分比|占比|份额|毛利率|净利率|同比|环比|增长\s*率|及格\s*率)", t)
    )

    time_semantic = bool(
        re.search(
            r"(?:19|20)\d{2}\s*年|年\s*度|季度|Q[1-4]|月份|月份|趋势|逐年|时间序列",
            t,
            re.I,
        )
    )

    return {
        "money_unit": money_unit,
        "count_suffix": count_suffix,
        "percent_semantic": percent_semantic,
        "time_semantic": time_semantic,
    }


def pie_values_are_share_percent(values: List[float]) -> bool:
    if len(values) < 2:
        return False
    s = sum(values)
    return all(0 <= v <= 100 for v in values) and 80 <= s <= 120


def suggest_y_name_for_simple_bar(hints: Dict[str, Any], values: List[float]) -> str:
    if hints.get("money_unit"):
        return f"数值（{hints['money_unit']}）"
    if hints.get("percent_semantic") and values and max(values) <= 100 and min(values) >= 0:
        return "数值（%）"
    if hints.get("count_suffix"):
        return f"数量（{hints['count_suffix']}）"
    return "数值"


def suggest_x_name_trend(hints: Dict[str, Any], x_labels: List[str]) -> str:
    if hints.get("time_semantic") or (
        x_labels and all(re.match(r"^(?:19|20)\d{2}$", str(l).strip()) for l in x_labels[:5])
    ):
        return "时间"
    return "类别"


def grouped_y_axis_names(hints: Dict[str, Any], series_in: List[Dict[str, Any]]) -> Tuple[str, str]:
    """双轴时左右轴标题。"""
    revenue_like = frozenset({"营收", "收入", "销售额", "销量", "成本", "费用", "金额"})
    left_names = [str(s.get("name", "")) for s in series_in if int(s.get("yAxisIndex", 0) or 0) == 0]
    if hints.get("money_unit"):
        left = f"金额（{hints['money_unit']}）"
    elif left_names and any(n in revenue_like for n in left_names):
        left = "金额类指标（请在正文中标明单位，常见为万元）"
    elif hints.get("count_suffix"):
        left = f"数量（{hints['count_suffix']}）"
    else:
        left = "指标值（左轴）"

    right = "比率 / 占比（%）"
    return left, right
