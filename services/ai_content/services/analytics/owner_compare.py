# -*- coding: utf-8 -*-
r"""
services/analytics/owner_compare.py — Owner 对比分析

PRD §4.4：Owner 对比（按预算 Owner 分组看人均 Plan 数 / 加权 CTR / 字数 / 高效词命中率）。

输入：build() 后的 DataFrame（含 owner / Plan ID / 触达 / 点击 / 标题 / 正文 / _tokens）
输出：DataFrame[owner, n_plans, n_records, 触达成功, 点击, 加权CTR%,
                标题字数均值, 正文字数均值, 高效词命中率%]
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from core.analytics_utils import weighted_ctr
from services.text_analyzer import word_frequency


def owner_compare(
    df: pd.DataFrame,
    owner_col: str = "owner",
    plan_col: str = "Plan ID",
    min_plans: int = 1,
    min_reach: int = 100,
    dict_path: Optional[str] = None,
    stop_path: Optional[str] = None,
) -> pd.DataFrame:
    """按 owner 分组对比。

    Parameters
    ----------
    df : 已 build() 清洗过的 DataFrame
    owner_col : owner 列名（默认"owner"，别名"预算owner"/"bu"）
    plan_col : plan ID 列
    min_plans : owner 下 plan 数 < 该值过滤（避免单人偶然样本）
    min_reach : owner 总触达 < 该值过滤
    dict_path / stop_path : 词典路径（计算高效词命中率用）

    Returns
    -------
    DataFrame[owner, n_plans, n_records, 触达成功, 点击, 加权CTR%,
              标题字数均值, 正文字数均值, 高效词命中率%]
    """
    if df is None or df.empty:
        return pd.DataFrame()

    for c in ("触达成功", "点击人次"):
        if c not in df.columns:
            return pd.DataFrame()
    if owner_col not in df.columns:
        return pd.DataFrame()

    work = df.dropna(subset=[owner_col])
    if work.empty:
        return pd.DataFrame()

    # 全局高效词（差值 > 0 的词）—— 用于命中率分母
    wf = word_frequency(work, min_plans=3, plan_col=plan_col)
    if wf.empty or "差值" not in wf.columns:
        eff_words: set = set()
    else:
        eff_words = set(wf[wf["差值"] > 0][wf.columns[0]].tolist())

    rows = []
    has_title = "标题" in work.columns
    has_body = "正文" in work.columns
    has_plan = plan_col in work.columns

    for owner, sub in work.groupby(owner_col, dropna=False):
        reach = int(sub["触达成功"].sum())
        click = int(sub["点击人次"].sum())
        if reach < min_reach:
            continue
        n_plans = int(sub[plan_col].nunique()) if has_plan else int(len(sub))
        if n_plans < min_plans:
            continue

        title_len_mean = round(sub["标题"].astype(str).str.len().mean(), 1) if has_title else 0.0
        body_len_mean = round(sub["正文"].astype(str).str.len().mean(), 1) if has_body else 0.0

        # 高效词命中率：本 owner 的 plan 平均覆盖了多少高效词（占全集高效词的比例）
        if eff_words and has_plan and plan_col in sub.columns:
            owner_word_set: set = set()
            for _, sub2 in sub.groupby(plan_col):
                # 这里需要 _tokens；若没有则 add_tokens
                if "_tokens" in sub2.columns:
                    for s in sub2["_tokens"]:
                        owner_word_set |= set(s)
                else:
                    owner_word_set |= set()  # 没 tokens 跳过
            hit_rate = round(len(owner_word_set & eff_words) / len(eff_words) * 100, 1) if eff_words else 0.0
        else:
            hit_rate = 0.0

        rows.append({
            "owner": owner,
            "n_plans": n_plans,
            "n_records": int(len(sub)),
            "触达成功": reach,
            "点击": click,
            "加权CTR%": weighted_ctr(click, reach),
            "标题字数均值": title_len_mean,
            "正文字数均值": body_len_mean,
            "高效词命中率%": hit_rate,
        })

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows).sort_values("加权CTR%", ascending=False).reset_index(drop=True)
    return out


__all__ = ["owner_compare"]