# -*- coding: utf-8 -*-
r"""
services/analytics/daily_trend.py — 每日趋势分析

PRD §4.4：每日趋势（按日聚合触达 / 点击 / 加权 CTR + 周环比）。

输入：build() 后的 DataFrame（含发送日期 / 触达成功 / 点击人次）
输出：DataFrame[date, n_records, 触达成功, 点击, 加权CTR%, 周环比%]
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from core.analytics_utils import weighted_ctr as _weighted_ctr


def daily_aggregate(
    df: pd.DataFrame,
    date_col: str = "发送日期",
    channel_col: Optional[str] = "渠道",
    owner_col: Optional[str] = "owner",
    min_reach: int = 100,
) -> pd.DataFrame:
    """按日聚合：触达 / 点击 / 加权 CTR。

    Parameters
    ----------
    df : 已 build() 清洗过的 DataFrame
    date_col : 日期列名（默认"发送日期"，已转 datetime）
    channel_col : 可选渠道列（提供则按渠道拆分；None 则全量）
    owner_col : 可选 owner 列（提供则按 owner 拆分；None 则全量）
    min_reach : 单日触达 < 该值的日子不参与周环比（噪声过滤）

    Returns
    -------
    DataFrame：[date, (channel|owner)?, n_records, 触达成功, 点击, 加权CTR%, 周环比%]
    """
    if df is None or df.empty:
        return pd.DataFrame()

    for c in ("触达成功", "点击人次"):
        if c not in df.columns:
            return pd.DataFrame()

    if date_col not in df.columns:
        return pd.DataFrame()

    # 过滤日期为空的行
    work = df.dropna(subset=[date_col]).copy()
    if work.empty:
        return pd.DataFrame()

    work["_date"] = work[date_col].dt.date

    # 决定分组键
    group_keys = ["_date"]
    if channel_col and channel_col in work.columns:
        group_keys.append(channel_col)
    if owner_col and owner_col in work.columns:
        group_keys.append(owner_col)

    g = work.groupby(group_keys, dropna=False)
    rows = []
    for keys, sub in g:
        if not isinstance(keys, tuple):
            keys = (keys,)
        d = dict(zip(group_keys, keys))
        reach = int(sub["触达成功"].sum())
        click = int(sub["点击人次"].sum())
        rows.append({
            "date": d["_date"],
            **({"channel": d[channel_col]} if channel_col and channel_col in work.columns else {}),
            **({"owner": d[owner_col]} if owner_col and owner_col in work.columns else {}),
            "n_records": int(len(sub)),
            "触达成功": reach,
            "点击": click,
            "加权CTR%": _weighted_ctr(click, reach),
        })

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    # 周环比：相对 7 天前同 channel/owner 的 CTR
    if len(out) >= 8:
        out["_ctr_shift"] = out["加权CTR%"].shift(7)
        # 分母为 0 → NA；计算时产生 NA 列，pandas round() 不接受 NA → 报 TypeError
        # 修：先用 nullable Float64 类型存，round 前 drop NA
        shifted = out["_ctr_shift"].replace(0, pd.NA)
        ratio_pct = (out["加权CTR%"] - shifted) / shifted * 100
        ratio_pct = ratio_pct.astype("Float64")  # nullable，NA 不会被 round 报错
        out["周环比%"] = ratio_pct.round(2)
        out = out.drop(columns=["_ctr_shift"])

    return out


def daily_summary(df: pd.DataFrame, date_col: str = "发送日期") -> dict:
    """趋势汇总：总触达 / 总点击 / 平均 CTR / 峰值日 / 谷值日。

    用于 PRD §4.4「每日趋势」卡顶部 KPI。
    """
    if df is None or df.empty or date_col not in df.columns:
        return {}
    work = df.dropna(subset=[date_col]).copy()
    if work.empty:
        return {}
    total_reach = int(work["触达成功"].sum())
    total_click = int(work["点击人次"].sum())
    overall_ctr = _weighted_ctr(total_click, total_reach)

    daily_ctr = work.groupby(work[date_col].dt.date).apply(
        lambda s: _weighted_ctr(int(s["点击人次"].sum()), int(s["触达成功"].sum())),
        include_groups=False,
    )
    if daily_ctr.empty:
        return {}

    peak_date = daily_ctr.idxmax()
    peak_ctr = float(daily_ctr.max())
    trough_date = daily_ctr.idxmin()
    trough_ctr = float(daily_ctr.min())

    return {
        "总触达": total_reach,
        "总点击": total_click,
        "整体CTR%": overall_ctr,
        "峰值日": peak_date,
        "峰值CTR%": peak_ctr,
        "谷值日": trough_date,
        "谷值CTR%": trough_ctr,
        "日均CTR%": round(float(daily_ctr.mean()), 2),
        "活跃天数": int(len(daily_ctr)),
    }


__all__ = ["daily_aggregate", "daily_summary"]