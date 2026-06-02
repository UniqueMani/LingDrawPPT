import re
from typing import Any, Dict, List, Optional, Tuple


_ARROW_RE = re.compile(r"->|→|=>|⇒")
_SEP_RE = re.compile(r"[，,;；]|\n")

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")


def _normalize_space(text: str) -> str:
    # 把换行/多余空格统一成单空格，方便后续规则匹配
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_simple_keywords(text: str, max_items: int = 6) -> List[str]:
    # 简化版关键词提取：取长度>=2的连续中文片段 + 英文字母单词
    text = text or ""
    cn_chunks = re.findall(r"[\u4e00-\u9fa5]{2,}", text)
    en_words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", text)
    candidates: List[str] = []
    for x in cn_chunks:
        candidates.append(x)
    for x in en_words:
        candidates.append(x)

    # 去重保序
    seen = set()
    out: List[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
        if len(out) >= max_items:
            break
    return out


def preprocess_text(topic: str, body: Optional[str], data_description: Optional[str]) -> Dict[str, Any]:
    """
    预处理尽量保持轻量：统一输入、做基础清洗、并为后续语义提取提供上下文。
    """
    topic = (topic or "").strip()
    body = (body or "").strip()
    data_description = (data_description or "").strip()

    combined = " ".join([x for x in [topic, body, data_description] if x])
    combined_norm = _normalize_space(combined)

    keywords = extract_simple_keywords(combined_norm)

    return {
        "topic": topic,
        "body": body,
        "data_description": data_description,
        "combined": combined_norm,
        "keywords": keywords,
    }


def parse_number_list(text: str) -> List[float]:
    nums = _NUMBER_RE.findall(text or "")
    return [float(x) for x in nums]


def parse_percent_map(text: str) -> List[Tuple[str, float]]:
    """
    提取形如：xxx 40%，yyy 35% 的 (label, value) 列表。
    """
    text = text or ""
    parts = _SEP_RE.split(text)
    out: List[Tuple[str, float]] = []
    for p in parts:
        m = re.search(r"(.+?)\s*(-?\d+(?:\.\d+)?)\s*%", p)
        if m:
            label = m.group(1).strip()
            val = float(m.group(2))
            if label:
                out.append((label, val))
    return out


def parse_label_value_pairs(text: str) -> List[Tuple[str, float]]:
    """
    尝试提取形如：A产品评分4.2，B产品3.8 的 (label, value)。
    """
    text = text or ""
    parts = _SEP_RE.split(text)
    out: List[Tuple[str, float]] = []
    for p in parts:
        nums = _NUMBER_RE.findall(p)
        if not nums:
            continue
        # 取最后一个数字作为值
        val = float(nums[-1])
        label = p
        # 去掉数值与常见后缀
        label = re.sub(r"-?\d+(?:\.\d+)?", "", label).strip()
        label = re.sub(r"(评分|值|比例|占比|销量|销售额|数量|价格|收入|成本)", "", label).strip(" ：:；;，,")
        if label:
            out.append((label, val))
    return out


def parse_time_series(text: str) -> Tuple[List[str], List[float]]:
    """
    简化版时间序列提取：优先找 '20xx年' 或 'X年'，否则退化为按出现顺序取前 N 个数字。
    """
    text = text or ""
    # 例：过去5年...或 2019年...2020年...
    year_matches = re.findall(r"((?:19|20)\d{2})\s*年", text)
    if year_matches:
        x = list(year_matches)
        nums = parse_number_list(text)
        # 如果数字较多，取与年份数量匹配的末尾/前段
        y = nums[: len(x)] if len(nums) >= len(x) else nums
        return x[: len(y)], y

    n_years = re.search(r"过去\s*(\d+)\s*年", text)
    if n_years:
        n = int(n_years.group(1))
        nums = parse_number_list(text)
        y = nums[:n] if len(nums) >= n else nums
        x = [f"T{i+1}" for i in range(len(y))]
        return x, y

    # 无时间信息：同样退化
    nums = parse_number_list(text)
    if not nums:
        return [], []
    return [f"T{i+1}" for i in range(len(nums))], nums


def parse_steps(text: str) -> List[str]:
    """
    提取流程/步骤：按箭头/分隔符切分并清洗。
    """
    text = text or ""
    text = _ARROW_RE.sub("->", text)
    parts = re.split(r"->|\|", text)
    # 再用分号/顿号二次切
    cleaned: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        subparts = re.split(r"[；;。]|、", p)
        for s in subparts:
            s = s.strip()
            if not s:
                continue
            # 删除步骤编号前缀（尽量干净）
            s = re.sub(r"^(步骤|Step|阶段)\s*\d+[:：.\s-]*", "", s).strip()
            if s and s not in cleaned:
                cleaned.append(s)
    return cleaned


def parse_hierarchy_chain(text: str) -> List[str]:
    """
    从类似 'A > B > C' / 'A/B/C' 的文本中提取层级链。
    """
    text = text or ""
    text = text.replace("＞", ">")
    # 支持常见分隔符
    for sep in [">", "/", "\\\\", "|"]:
        if sep in text:
            parts = [p.strip() for p in text.split(sep) if p.strip()]
            if parts:
                return parts
    return []


_ENTITY_SKIP = frozenset(
    {
        "单位",
        "本页",
        "如下",
        "其中",
        "说明",
        "注",
        "数据来源",
    }
)


def _is_skipped_entity(name: str) -> bool:
    n = (name or "").strip()
    n = re.sub(r"\s+", "", n)
    if len(n) < 2 or len(n) > 28:
        return True
    if n in _ENTITY_SKIP or n.startswith("单位"):
        return True
    if re.fullmatch(r"[\d\s\./%万元]+", n):
        return True
    return False


def _parse_row_metric_pairs(body: str) -> Dict[str, float]:
    """解析单行内「指标名 数值[可选%]」，以逗号/顿号分隔。"""
    out: Dict[str, float] = {}
    body = (body or "").strip()
    if not body:
        return out
    for p in re.split(r"[，,、]", body):
        p = p.strip()
        if not p:
            continue
        m = re.search(r"(.+?)\s*(-?\d+(?:\.\d+)?)\s*%?\s*$", p)
        if not m:
            continue
        label = m.group(1).strip()
        val = float(m.group(2))
        label = re.sub(r"[（(].*?[）)]", "", label).strip()
        if label and not re.fullmatch(r"[\d\.]+", label):
            out[label] = val
    return out


def extract_entity_metric_blocks(text: str) -> List[Tuple[str, str]]:
    """
    提取「实体：指标串」块。支持前文说明 + 分号分隔的多实体（如多产品线）。
    """
    text = text or ""
    out: List[Tuple[str, str]] = []
    for m in re.finditer(
        r"([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9·\-\s]{1,28}?)[：:]\s*",
        text,
    ):
        entity = re.sub(r"\s+", "", m.group(1).strip())
        if _is_skipped_entity(entity):
            continue
        start = m.end()
        rest = text[start:]
        stop = re.search(
            r"(?=[\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9·\-\s]{1,28}?[：:])|[；;]",
            rest,
        )
        chunk = rest[: stop.start()] if stop else rest
        chunk = chunk.strip().rstrip("，,")
        if chunk:
            out.append((entity, chunk))
    return out


def parse_entity_metric_grid(text: str) -> Optional[Dict[str, Any]]:
    """
    多实体 × 多指标（类表格）解析。满足：至少 2 个实体，且每个实体至少 2 个指标。
    """
    blocks = extract_entity_metric_blocks(text)
    row_dicts: List[Dict[str, float]] = []
    categories: List[str] = []
    for entity, body in blocks:
        metrics_here = _parse_row_metric_pairs(body)
        if len(metrics_here) < 2:
            continue
        categories.append(entity)
        row_dicts.append(metrics_here)

    if len(categories) < 2:
        return None

    metric_keys: List[str] = []
    seen: set[str] = set()
    for rd in row_dicts:
        for k in rd.keys():
            if k not in seen:
                seen.add(k)
                metric_keys.append(k)

    if len(metric_keys) < 2:
        return None

    matrix: List[List[Optional[float]]] = []
    for rd in row_dicts:
        matrix.append([rd.get(k) for k in metric_keys])

    return {
        "categories": categories,
        "metrics": metric_keys,
        "matrix": matrix,
    }


def grid_to_grouped_series_extracted(grid: Dict[str, Any]) -> Dict[str, Any]:
    """将网格结果转为分组柱状图所需的 extracted。"""
    categories = [str(x) for x in grid.get("categories") or []]
    metrics = [str(x) for x in grid.get("metrics") or []]
    matrix = grid.get("matrix") or []
    series: List[Dict[str, Any]] = []
    pct_hints = ("率", "占比", "比例", "份额", "环比", "同比")
    revenue_like = frozenset({"营收", "收入", "销售额", "销量", "成本", "费用", "金额"})

    for j, name in enumerate(metrics):
        col: List[Optional[float]] = [row[j] if j < len(row) else None for row in matrix]
        values = [float(v) if v is not None else 0.0 for v in col]
        lower = name.lower()
        if name in revenue_like:
            y_axis = 0
        elif any(h in name for h in pct_hints) or "percent" in lower:
            y_axis = 1
        else:
            y_axis = 0
        series.append({"name": name, "values": values, "yAxisIndex": y_axis})

    return {"categories": categories, "series": series}

