# -*- coding: utf-8 -*-
r"""
core/analytics_utils.py — 通用分析工具函数（聚合 CTR 计算）

Phase 17 新增：消除全项目"round(click / reach * 100, 2) if reach > 0 else 0.0"
公式在 services/analytics/ + repositories/ + tools/ + pages/ 7+ 处重复。
提供：
- weighted_ctr(click, reach, as_percent=True) -> float：标量 plan 加权 CTR
- weighted_ctr_series(click_s, reach_s, as_percent=True) -> pd.Series：批量版
"""

from __future__ import annotations

from typing import Union

import pandas as pd


Number = Union[int, float]


def weighted_ctr(click: Number, reach: Number, as_percent: bool = True) -> float:
    """标量 plan 加权 CTR。

    安全除零：reach ≤ 0 → 返回 0.0。
    as_percent=True → 返回百分数（如 3.5 表示 3.5%）；False → 返回小数（如 0.035）。
    """
    if not reach or reach <= 0:
        return 0.0
    raw = click / reach
    return round(raw * 100, 2) if as_percent else round(raw, 6)


def weighted_ctr_series(
    click_s: pd.Series,
    reach_s: pd.Series,
    as_percent: bool = True,
) -> pd.Series:
    """批量 plan 加权 CTR（与标量版语义一致；reach ≤ 0 → 0.0）。

    实现：先把 reach=0 → NaN（避开除零），算 ratio，最后 fillna(0.0)。
    不能先 .round() 后 .fillna()——pandas NA 不支持 round。
    """
    reach = reach_s.replace(0, pd.NA)
    raw = click_s / reach
    out = (raw * 100) if as_percent else raw
    return out.fillna(0.0).round(2 if as_percent else 6)


__all__ = ["weighted_ctr", "weighted_ctr_series"]