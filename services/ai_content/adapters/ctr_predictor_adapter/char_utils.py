# -*- coding: utf-8 -*-
r"""
char_utils.py — 标题字数工具（纯函数）

来源：C:\ideon\mcd-ctr-predictor\ctr_predictor.py 第 159-201 行（机械搬迁）。

Phase 1a 变更：
- OPTIMAL_CHARS 不再硬编码，从 baseline JSON 的 optimal_chars 字段读
  （CLAUDE.md §4.3：消除双源维护）
- count_chars / get_char_range 保持纯函数
- suggest_char_range 增加 baseline 参数（默认从 JSON 读）
"""

from __future__ import annotations
from typing import Optional

from .baseline_lookup import get_baseline


def count_chars(text: str) -> int:
    """字符数（不含空白两端）。来源：ctr_predictor.py:159-160"""
    return len(str(text).strip())


def get_char_range(title: str) -> str:
    """标题字数所属区间（"5-6字" / "7-8字" / ... / "23-24字" / "N字"）。
    来源：ctr_predictor.py:163-185
    """
    n = count_chars(title)
    if n <= 6:
        return "5-6字"
    elif n <= 8:
        return "7-8字"
    elif n <= 10:
        return "9-10字"
    elif n <= 12:
        return "11-12字"
    elif n <= 14:
        return "13-14字"
    elif n <= 16:
        return "15-16字"
    elif n <= 18:
        return "17-18字"
    elif n <= 20:
        return "19-20字"
    elif n <= 22:
        return "21-22字"
    elif n <= 24:
        return "23-24字"
    return f"{n}字"


def suggest_char_range(channel: str, title: str, baseline: Optional[dict] = None) -> str:
    """基于渠道建议字数区间给出诊断文案。

    来源：ctr_predictor.py:188-201
    数据来源：baseline.optimal_chars（ctr_predictor.py 中的 OPTIMAL_CHARS 常量已废弃）
    """
    n = count_chars(title)
    bl = get_baseline(baseline=baseline)
    optimal = bl.get("optimal_chars", {}).get(channel.strip(), None)
    if not optimal:
        return ""
    lo_s, hi_s = optimal.split("-")
    lo_n = int(lo_s.replace("字", ""))
    hi_n = int(hi_s.replace("字", ""))
    if lo_n <= n <= hi_n:
        return f"字数{n}字，在{optimal}最优区间内"
    elif n < lo_n:
        return f"字数{n}字，偏短{lo_n - n}字，建议{optimal}"
    else:
        return f"字数{n}字，偏长{n - hi_n}字，建议{optimal}"