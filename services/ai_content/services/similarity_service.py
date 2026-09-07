# -*- coding: utf-8 -*-
r"""
services/similarity_service.py — 历史相似 Plan 检索 service 包装

复用 services/analytics/similarity.find_similar_plans（TF-IDF + 余弦）。

入口：
- 01 内容创作页：生成 3 条候选后，对每条找 top_k 相似历史 Plan（PRD §7.6）
- 02 文案诊断页：对单条文案找相似历史 Plan

df 为 None 时返回空 DataFrame（无历史数据可查）。
"""

from __future__ import annotations

from typing import Optional
import pandas as pd

from services.analytics.similarity import find_similar_plans
from services.data_loader import build, load_sheet


def _load_default_df(file_bytes: Optional[bytes] = None) -> pd.DataFrame:
    """加载默认历史数据：优先用传入的 file_bytes，否则尝试 data/ 默认文件。"""
    if file_bytes is not None:
        try:
            df, _meta = build(file_bytes)
            return df
        except Exception:
            return pd.DataFrame()
    # 无 file_bytes：返回空 df，UI 层显示"无历史数据"
    return pd.DataFrame()


def find_similar(
    title: str,
    body: str,
    channel: str = "",
    file_bytes: Optional[bytes] = None,
    top_k: int = 3,
) -> pd.DataFrame:
    """返回 top_k 相似历史 Plan DataFrame。无数据时返回空 DataFrame。

    列：plan_id / title / body / channel / similarity / ctr / reach（具体列名以 find_similar_plans 为准）
    """
    df = _load_default_df(file_bytes)
    if df.empty:
        return pd.DataFrame()
    try:
        return find_similar_plans(df, title, body, top_k=top_k)
    except Exception:
        return pd.DataFrame()


def summarize_similar(df: pd.DataFrame) -> dict:
    """把相似 DataFrame 聚合成 dict，给 UI 直接展示。

    返回：{"count": N, "avg_ctr": float | None, "top_terms": list[str]}
    无数据：{"count": 0, "avg_ctr": None, "top_terms": []}
    """
    if df is None or df.empty:
        return {"count": 0, "avg_ctr": None, "top_terms": []}
    count = len(df)
    avg_ctr = None
    if "ctr" in df.columns or "加权CTR%" in df.columns:
        col = "ctr" if "ctr" in df.columns else "加权CTR%"
        try:
            avg_ctr = float(df[col].mean())
        except Exception:
            avg_ctr = None
    top_terms: list = []
    if "title" in df.columns:
        # 简单取标题前 3 个不同关键词（去重 + 取前 5 字）
        seen = set()
        for t in df["title"].astype(str).tolist():
            for kw in t[:5]:
                if kw and kw not in seen:
                    seen.add(kw)
                    top_terms.append(kw)
                    if len(top_terms) >= 6:
                        break
            if len(top_terms) >= 6:
                break
    return {"count": count, "avg_ctr": avg_ctr, "top_terms": top_terms}


__all__ = ["find_similar", "summarize_similar"]
