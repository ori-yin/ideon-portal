# -*- coding: utf-8 -*-
r"""
core/text_classifier.py — 文案内容分类器（Phase 12 #11 用券双字段）

功能：
- classify_coupon_in_text(title, body) → "是"/"否"
  判断标题/正文是否含券词（优惠券/折扣/链接等）

复用：
- 关键词词典在 config/coupon_keywords.yaml（v1.0）
- 风格对齐 core/data_window.classify_date_type（纯函数 + lru_cache 加载 yaml）

不消费：
- form 字段"实际是否用券"（plan 维度）—— 用 TaskInput.coupon
- baseline_lookup 的渠道 × 用券维度 —— 走 `渠道_x_是否用券`
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Optional


DEFAULT_KEYWORDS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "coupon_keywords.yaml"
)


@functools.lru_cache(maxsize=1)
def _load_keywords(path: str = str(DEFAULT_KEYWORDS_PATH)) -> list:
    """加载优惠券关键词词典（discount + coupon + link 三类合并成 pattern 列表）。"""
    p = Path(path)
    if not p.exists():
        return []
    try:
        import yaml
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    patterns = []
    for cat in ("discount", "coupon", "link"):
        for kw in doc.get(cat, []) or []:
            try:
                patterns.append(re.compile(kw))
            except re.error:
                # yaml 配错正则时跳过这一条，不阻塞其他
                continue
    return patterns


def classify_coupon_in_text(
    title: Optional[str],
    body: Optional[str] = None,
    keywords_path: Optional[str] = None,
) -> str:
    """判断标题/正文是否含券词。

    返回："是" / "否"（与 form `coupon` 字段口径一致，便于 baseline_lookup 复用）。

    参数：
    - title: 文案标题（短信/企微可为空）
    - body: 文案正文
    - keywords_path: 自定义词典路径（默认 config/coupon_keywords.yaml）

    边界：
    - title + body 都为空 → "否"
    - 任一关键词命中 → "是"
    """
    patterns = _load_keywords(keywords_path) if keywords_path else _load_keywords()
    if not patterns:
        return "否"
    text = " ".join([t for t in (title or "", body or "") if t])
    if not text.strip():
        return "否"
    for p in patterns:
        if p.search(text):
            return "是"
    return "否"


def classify_coupon_batch(
    title_s: "pd.Series",
    body_s: "pd.Series",
    keywords_path: Optional[str] = None,
) -> list[str]:
    """批量版：把多条 (title, body) 一次判完，比逐行 apply 快 50-100x。

    Phase 17.5 优化：把多个 keyword 正则合并成 1 个大的，再用 Series.str.contains 向量化匹配。
    输入：pd.Series（等长）；输出：list[str]，与输入行一一对应。
    """
    try:
        import pandas as pd
    except ImportError:
        # pandas 不在则 fallback 逐行（理论上不会发生）
        return [classify_coupon_in_text(t, b, keywords_path)
                for t, b in zip(title_s.tolist(), body_s.tolist())]

    patterns = _load_keywords(keywords_path) if keywords_path else _load_keywords()
    n = len(title_s)
    if not patterns:
        return ["否"] * n

    # 合并 pattern（用 | 连接；每个用非捕获组包裹避免优先级问题）
    combined_re = re.compile("|".join(f"(?:{p.pattern})" for p in patterns))
    # title + body 拼一起后 strip
    combined_text = (title_s.fillna("").astype(str)
                     + " "
                     + body_s.fillna("").astype(str)).str.strip()
    # 向量化匹配；na=False 让空字符串视作 False
    mask = combined_text.str.contains(combined_re, regex=True, na=False)
    return ["是" if m else "否" for m in mask]


__all__ = ["classify_coupon_in_text", "classify_coupon_batch"]
