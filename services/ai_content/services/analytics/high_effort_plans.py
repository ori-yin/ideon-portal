# -*- coding: utf-8 -*-
r"""
services/analytics/high_effort_plans.py — 高效 Plan 排行

PRD §4.4：高效 Plan 排行（按 plan 加权 CTR 降序）。
按 Plan ID 聚合触达 / 点击 / 加权 CTR，附带 plan 名称 / 渠道 / owner 等元数据。

输入：build() 后的 DataFrame（含 Plan ID / 触达成功 / 点击人次）
输出：DataFrame[Plan ID, Plan名称, 渠道, owner, n_records, n_records_per_day,
                触达成功, 点击, 加权CTR%, 字数均值, 高效词命中数]
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from core.analytics_utils import weighted_ctr


# 默认阈值：plan 触达 >= 1000 视为有效样本；plan < 3 视为低样本过滤
DEFAULT_MIN_REACH = 1000
DEFAULT_MIN_PLANS = 3


def _weighted_ctr(click_s: pd.Series, reach_s: pd.Series) -> pd.Series:
    """Series 版 plan 加权 CTR：click/reach*100，安全除零。"""
    reach = reach_s.replace(0, pd.NA)
    out = (click_s / reach * 100).round(2)
    return out.fillna(0.0)


def rank_plans(
    df: pd.DataFrame,
    min_reach: int = DEFAULT_MIN_REACH,
    min_plans: int = DEFAULT_MIN_PLANS,
    top_n: Optional[int] = None,
    sort_by: str = "加权CTR%",
    plan_col: str = "Plan ID",
    date_col: str = "发送日期",
) -> pd.DataFrame:
    """按 plan 加权 CTR 排行。

    Parameters
    ----------
    df : 已 build() 清洗过的 DataFrame
    min_reach : 触达成功 < 该值的 plan 直接过滤（避免小 plan CTR 失真）
    min_plans : 触达样本 plan 数 < 该值的 plan 直接过滤（默认 3）
    top_n : 返回前 N 条（None 则全返回）
    sort_by : 排序列，默认"加权CTR%"，可选"触达成功"等

    Returns
    -------
    DataFrame：列 = [plan_id, plan_name, channel, owner, n_records,
                     n_days, reach, click, ctr, title_len_mean, body_len_mean,
                     hit_word_count]
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if plan_col not in df.columns:
        return pd.DataFrame()

    # 必备列检查
    for c in ("触达成功", "点击人次"):
        if c not in df.columns:
            return pd.DataFrame()

    g = df.groupby(plan_col, dropna=False)
    rows = []
    has_date = date_col in df.columns
    has_title = "标题" in df.columns
    has_body = "正文" in df.columns

    for plan_id, sub in g:
        reach = int(sub["触达成功"].sum())
        click = int(sub["点击人次"].sum())
        if reach < min_reach:
            continue
        if len(sub) < min_plans:
            continue

        plan_name = sub["Plan名称"].iloc[0] if "Plan名称" in sub.columns else ""
        channel = sub["渠道"].iloc[0] if "渠道" in sub.columns else ""
        owner = sub["owner"].iloc[0] if "owner" in sub.columns else ""
        # n_days：CSV 上来 发送日期 常是字符串，.dt.date 会 AttributeError；这里容错降级
        if has_date and pd.api.types.is_datetime64_any_dtype(sub[date_col]):
            n_days = sub[date_col].dt.date.nunique()
        else:
            n_days = 0
        title_len_mean = round(sub["标题"].astype(str).str.len().mean(), 1) if has_title else 0.0
        body_len_mean = round(sub["正文"].astype(str).str.len().mean(), 1) if has_body else 0.0
        # 高效词命中数（依赖 _tokens 已加）
        if "_tokens" in sub.columns:
            tok_set = set()
            for s in sub["_tokens"]:
                tok_set |= set(s)
            hit_n = len(tok_set)
        else:
            hit_n = 0

        rows.append({
            "plan_id": plan_id,
            "plan_name": plan_name,
            "channel": channel,
            "owner": owner,
            "n_records": int(len(sub)),
            "n_days": int(n_days) if n_days else 0,
            "触达成功": reach,
            "点击": click,
            "加权CTR%": weighted_ctr(click, reach),
            "标题字数均值": title_len_mean,
            "正文字数均值": body_len_mean,
            "覆盖高效词数": hit_n,
        })

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    if sort_by in out.columns:
        out = out.sort_values(sort_by, ascending=False).reset_index(drop=True)
    if top_n is not None:
        out = out.head(top_n)
    return out


__all__ = ["rank_plans", "DEFAULT_MIN_REACH", "DEFAULT_MIN_PLANS"]