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


# --- Stable parsers used by the chart stability pass -----------------------
# These definitions intentionally override the lightweight demo parsers above.
# They keep the public function names unchanged while tightening numeric
# extraction around common PPT business-chart language.

_SPLIT_RE_STABLE = re.compile(r"[;；\n|]+")
_METRIC_SPLIT_RE_STABLE = re.compile(r"[,，、;；\n]+")
_NUM_UNIT_RE_STABLE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(万元|亿元|万|%|元|人|个|件|台|分)?"
)


def _source_text_for_structured_data(text: str) -> str:
    raw = text or ""
    m = re.search(r"(?:数据描述|data_description)\s*[:：]\s*(.+)$", raw, re.I | re.S)
    return m.group(1).strip() if m else raw


def _is_year_token(value: str) -> bool:
    return bool(re.fullmatch(r"(?:19|20)\d{2}", str(value).strip()))


def _clean_label(label: str) -> str:
    label = re.sub(r"^\s*(?:topic|body|data_description|expected_intent|expected_chartType)\s*[:：]\s*", "", label, flags=re.I)
    if "：" in label or ":" in label:
        label = re.split(r"[:：]", label)[-1]
    label = re.sub(r"[\s:=：，,；;]+$", "", label)
    label = re.sub(r"^(?:和|及|以及|其中|分别为|为|是|则|行|列)\s*", "", label)
    return label.strip(" -—>=").strip()


def _to_float(value: str) -> float:
    n = float(value)
    return int(n) if n.is_integer() else n


def _parse_named_series(text: str) -> Optional[Tuple[List[str], List[float], str]]:
    source = _source_text_for_structured_data(text)
    labels_match = re.search(
        r"(?:时间序列|年份|年度|月份|季度|时间|x|X)\s*[:：=]\s*([A-Za-z0-9\u4e00-\u9fa5,\-，、\s]+?)(?=；|;|\n|$)",
        source,
        re.I,
    )
    if not labels_match:
        return None
    labels = [_clean_label(x) for x in re.split(r"[,，、\s]+", labels_match.group(1)) if _clean_label(x)]
    labels = [x for x in labels if not re.fullmatch(r"单位|万元|亿元|元|%|人|个|件|台", x)]
    if len(labels) < 2:
        return None

    tail = source[labels_match.end() :]
    metric_match = re.search(
        r"([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9\s/_-]{0,20})\s*[:：=]\s*(-?\d+(?:\.\d+)?(?:\s*[,，、]\s*-?\d+(?:\.\d+)?)+)",
        tail,
    )
    if not metric_match:
        return None
    values = [_to_float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", metric_match.group(2))]
    n = min(len(labels), len(values))
    if n < 2:
        return None
    return labels[:n], values[:n], _clean_label(metric_match.group(1))


def parse_time_series(text: str) -> Tuple[List[str], List[float]]:
    text = text or ""
    named = _parse_named_series(text)
    if named:
        x, y, _name = named
        return x, y

    pairs: List[Tuple[str, float]] = []
    seen_spans: set[Tuple[int, int]] = set()
    patterns = [
        r"((?:19|20)\d{2})\s*年?\s*[:：=]?\s*(-?\d+(?:\.\d+)?)\s*(?:万元|亿元|万|元|%|人|个|件|台)?",
        r"((?:[1-9]|1[0-2])月|Q[1-4]|第[一二三四1234]季度)\s*[:：=]?\s*(-?\d+(?:\.\d+)?)\s*(?:万元|亿元|万|元|%|人|个|件|台)?",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            label = m.group(1)
            value = _to_float(m.group(2))
            # A bare year immediately followed by another year is a label list,
            # not a value pair.
            if _is_year_token(str(value)):
                continue
            pairs.append((label, value))
            seen_spans.add(m.span())

    if len(pairs) >= 2:
        return [p[0] for p in pairs], [p[1] for p in pairs]

    n_years = re.search(r"过去\s*(\d+)\s*年", text)
    if n_years:
        n = int(n_years.group(1))
        nums = [
            _to_float(m.group(1))
            for m in _NUM_UNIT_RE_STABLE.finditer(text)
            if not _is_year_token(m.group(1)) and m.group(2)
        ]
        nums = nums[:n]
        return [f"T{i+1}" for i in range(len(nums))], nums

    return [], []


def parse_percent_map(text: str) -> List[Tuple[str, float]]:
    text = _source_text_for_structured_data(text or "")
    out: List[Tuple[str, float]] = []
    for part in _SPLIT_RE_STABLE.split(text):
        for m in re.finditer(r"([^,，、;；\n:=：]+?)\s*[:：=]?\s*(-?\d+(?:\.\d+)?)\s*%", part):
            label = _clean_label(m.group(1))
            if label and label not in {"合计", "总计", "总和"} and not _is_year_token(label):
                out.append((label, _to_float(m.group(2))))
    deduped: List[Tuple[str, float]] = []
    seen: set[str] = set()
    for label, value in out:
        key = re.sub(r"\s+", "", label)
        if key not in seen:
            seen.add(key)
            deduped.append((label, value))
    return deduped


def parse_label_value_pairs(text: str) -> List[Tuple[str, float]]:
    text = _source_text_for_structured_data(text or "")
    out: List[Tuple[str, float]] = []

    # Prefer structured "labels: ...; values: ..." descriptions.
    label_match = re.search(
        r"(?:产品|渠道|阶段|套餐|类别|labels?|分类)\s*[:：=]\s*([A-Za-z0-9\u4e00-\u9fa5\s,\-，、]+?)(?=；|;|\n|$)",
        text,
        re.I,
    )
    value_match = re.search(
        r"(?:评分|同比增长率|增长率|转化率|conversion rate|价格|席位数|values?|数值|指标)\s*[:：=]\s*(-?\d+(?:\.\d+)?(?:\s*[,，、]\s*-?\d+(?:\.\d+)?)+)",
        text,
        re.I,
    )
    if label_match and value_match:
        labels = [_clean_label(x) for x in re.split(r"[,，、]+", label_match.group(1)) if _clean_label(x)]
        values = [_to_float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", value_match.group(1))]
        return list(zip(labels[: len(values)], values[: len(labels)]))

    for part in _METRIC_SPLIT_RE_STABLE.split(text):
        part = part.strip()
        if not part:
            continue
        if re.search(r"(?:19|20)\d{2}\s*年?", part):
            continue
        m = re.search(r"(.+?)\s*[:：=]?\s*(-?\d+(?:\.\d+)?)\s*(?:万元|亿元|万|元|%|人|个|件|台|分)?\s*$", part)
        if not m:
            continue
        label = _clean_label(m.group(1))
        label = re.sub(r"(评分|数值|数量|价格|收入|营收|销售额|同比增长率|增长率|转化率)$", "", label).strip()
        if label and not _is_year_token(label):
            out.append((label, _to_float(m.group(2))))
    return out


def parse_steps(text: str) -> List[str]:
    text = text or ""
    if re.search(r"(?:Pipeline|stages?|conversion rate)", text, re.I):
        return []
    if not re.search(r"流程|步骤|依次|经过|->|=>|→", text):
        return []
    normalized = re.sub(r"->|=>|→", "->", text)
    if "->" in normalized:
        parts = [p.strip() for p in normalized.split("->")]
    else:
        m = re.search(r"(?:依次经过|依次为|流程为|步骤为)(.+)", normalized)
        parts = re.split(r"[,，、;；]", m.group(1)) if m else []
    cleaned: List[str] = []
    for p in parts:
        p = _clean_label(re.sub(r"\d+(?:\.\d+)?\s*(?:万元|亿元|万|元|%|人|个|件|台)?", "", p))
        if p and p not in cleaned:
            cleaned.append(p[:32])
    return cleaned


def parse_hierarchy_chain(text: str) -> List[str]:
    text = text or ""
    if not re.search(r"层级|组织|架构|下设|隶属|上下级|层级链", text):
        return []
    m = re.search(r"(?:层级链|层级|组织结构)\s*[:：]\s*(.+)$", text)
    source = m.group(1) if m else text
    parts = [p.strip() for p in re.split(r"\s*(?:>|/|\\|->|=>|→)\s*", source) if p.strip()]
    if len(parts) >= 2:
        return [_clean_label(p).rstrip("。")[:32] for p in parts]
    chain = re.findall(r"([\u4e00-\u9fa5A-Za-z0-9_-]{2,20})下设", text)
    tail = re.search(r"下设([\u4e00-\u9fa5A-Za-z0-9_-]{2,20})(?:。|$)", text)
    if chain and tail:
        return chain + [tail.group(1)]
    return []


def _parse_row_metric_pairs(body: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for part in _METRIC_SPLIT_RE_STABLE.split(body or ""):
        m = re.search(r"(.+?)\s*[:：=]?\s*(-?\d+(?:\.\d+)?)\s*(?:万元|亿元|万|元|%|人|个|件|台)?\s*$", part.strip())
        if not m:
            continue
        label = _clean_label(m.group(1))
        if label and not re.fullmatch(r"[\d.]+", label):
            out[label] = _to_float(m.group(2))
    return out


def extract_entity_metric_blocks(text: str) -> List[Tuple[str, str]]:
    text = _source_text_for_structured_data(text or "")
    out: List[Tuple[str, str]] = []
    for segment in _SPLIT_RE_STABLE.split(text):
        if not segment.strip():
            continue
        m = re.match(r"\s*([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9产品渠道套餐阶段\s_-]{0,24})\s*[:：=]?\s*(.+)$", segment.strip())
        if not m:
            continue
        entity = _clean_label(m.group(1))
        body = m.group(2).strip()
        if _is_skipped_entity(entity) or len(_parse_row_metric_pairs(body)) < 2:
            continue
        out.append((entity, body))
    return out


def parse_entity_metric_grid(text: str) -> Optional[Dict[str, Any]]:
    source = _source_text_for_structured_data(text or "")

    # Structured matrix: 产品=A,B,C；营收=320,280,360万元；毛利率=38,42,35%
    cat_match = re.search(
        r"(?:产品|渠道|实体|类别|categories?)\s*[:：=]\s*([A-Za-z0-9\u4e00-\u9fa5\s,\-，、]+?)(?=；|;|\n|$)",
        source,
        re.I,
    )
    if cat_match:
        categories = [_clean_label(x) for x in re.split(r"[,，、]+", cat_match.group(1)) if _clean_label(x)]
        metrics: List[str] = []
        cols: List[List[float]] = []
        for m in re.finditer(
            r"([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9\s/_-]{0,20})\s*[:：=]\s*(-?\d+(?:\.\d+)?(?:\s*[,，、]\s*-?\d+(?:\.\d+)?)+)",
            source[cat_match.end() :],
        ):
            name = _clean_label(m.group(1))
            if name in {"单位", "行", "列"}:
                continue
            values = [_to_float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", m.group(2))]
            if len(values) >= len(categories) >= 2:
                metrics.append(name)
                cols.append(values[: len(categories)])
        if len(metrics) >= 2:
            matrix = [[cols[j][i] for j in range(len(metrics))] for i in range(len(categories))]
            return {"categories": categories, "metrics": metrics, "matrix": matrix}

    blocks = extract_entity_metric_blocks(source)
    if len(blocks) < 2:
        return None
    categories: List[str] = []
    rows: List[Dict[str, float]] = []
    for entity, body in blocks:
        metrics_here = _parse_row_metric_pairs(body)
        if len(metrics_here) >= 2:
            categories.append(entity)
            rows.append(metrics_here)
    if len(categories) < 2:
        return None
    metric_keys: List[str] = []
    for row in rows:
        for key in row:
            if key not in metric_keys:
                metric_keys.append(key)
    if len(metric_keys) < 2:
        return None
    matrix = [[row.get(k) for k in metric_keys] for row in rows]
    return {"categories": categories, "metrics": metric_keys, "matrix": matrix}

