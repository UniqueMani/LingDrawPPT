import re
from dataclasses import dataclass
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

