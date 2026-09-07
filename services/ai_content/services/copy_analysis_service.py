# -*- coding: utf-8 -*-
r"""
services/copy_analysis_service.py — 文案本地诊断 service 包装

复用 services/text_analyzer.diagnose_score（PRD §13.3 单条文案诊断）。
在此基础上补齐 problems（问题清单）和 suggestions（p1/p2 改写建议）字段。

返回 dict 含：score / grade / breakdown / diag / baseline_ctr / predicted_ctr /
             ctr_delta_pct / problems / suggestions
"""

from __future__ import annotations

from typing import Optional
import pandas as pd

from services.text_analyzer import diagnose_score, diagnose_problems


def diagnose(
    title: str,
    body: str,
    channel: Optional[str] = None,
    df: Optional[pd.DataFrame] = None,
    min_plans: int = 3,
) -> dict:
    """单条文案诊断。

    返回 dict：
    - score: 0-100
    - grade: 优秀 / 良好 / 需优化 / 重写
    - breakdown: 各维度得分
    - diag: local_diagnose dict（{len_title, len_body, emoji_count, hit_words, miss_top}）
    - baseline_ctr / predicted_ctr / ctr_delta_pct: 无历史数据时为 None
    - problems: list[{tag, label, current, suggested, so_what}]
    - suggestions: (p1_list, p2_list)
    """
    try:
        result = diagnose_score(title, body, df=df, target_ch=channel, min_plans=min_plans)
    except Exception as e:
        return {
            "score": None,
            "grade": "—",
            "breakdown": {},
            "diag": {"error": str(e)},
            "baseline_ctr": None,
            "predicted_ctr": None,
            "ctr_delta_pct": None,
            "problems": [],
            "suggestions": ([], []),
        }

    diag = result.get("diag") or {}
    problems = []
    try:
        problems = diagnose_problems(title, body, diag, target_ch=channel)
    except Exception:
        problems = []

    # 简化 suggestions：p1=改写方向，p2=本地诊断提示
    p1 = []
    p2 = []
    score = result.get("score", 0) or 0
    if score < 70:
        p1.append("考虑重写以提高文案评分")
    if diag.get("emoji_count", 0) == 0:
        p2.append("加入 1-2 个 emoji 提升视觉吸引力")
    if len(diag.get("hit_words") or []) == 0:
        p2.append("尝试加入历史高效词")

    result["problems"] = problems
    result["suggestions"] = (p1, p2)
    return result


__all__ = ["diagnose"]
