# -*- coding: utf-8 -*-
r"""
feedback_lookup.py — demo 数据回灌（Phase-B · Handoff §6.3 纯工程候选）

约束：
- adapter 不能 import repository（CLAUDE.md §4.1）
  → 本模块直接 import sqlite3，不依赖 repositories/feedback_repository
- DB 缺失/异常必须降级（Demo 模式零依赖红线 Handoff §4）
- 阈值：FEEDBACK_READY_MIN_PLANS = 50（独立于 calibrate_baseline 的 5/20）

调用方：
- adapters/ctr_predictor_adapter/__init__.py:_demo_pred：feedback 回灌分支
- tests/verify.py §44：16 用例验证

v0.1 算法：
- feedback.db 累计 ≥ 50 distinct plans → is_feedback_ready() 返回 True
- _demo_pred 拿到 row["_signature"] 后调 lookup_feedback_ctr(sig)
- 命中（reach > 0）→ 返回真实 CTR（click/reach 小数）
- 未命中 / 异常 → 返回 None，_demo_pred 兜底走 baseline × tm
"""

from __future__ import annotations

import functools
import sqlite3
from pathlib import Path
from typing import Optional


# ── 阈值与路径 ────────────────────────────────────────────────────
FEEDBACK_READY_MIN_PLANS = 50  # 与 calibrate_baseline 的 MIN_PLANS_DEFAULT=5 独立
ROOT = Path(__file__).resolve().parents[2]
FEEDBACK_DB_PATH = ROOT / "data" / "feedback.db"


# ── 全局级查询（maxsize=1） ────────────────────────────────────────
@functools.lru_cache(maxsize=1)
def count_distinct_plans() -> int:
    """SELECT COUNT(DISTINCT task_signature) FROM feedback_records。

    DB 缺失/异常 → 0（Demo 模式零依赖红线，绝不抛异常）。
    """
    if not FEEDBACK_DB_PATH.exists():
        return 0
    try:
        conn = sqlite3.connect(str(FEEDBACK_DB_PATH))
        try:
            cur = conn.execute(
                "SELECT COUNT(DISTINCT task_signature) FROM feedback_records"
            )
            return int(cur.fetchone()[0])
        finally:
            conn.close()
    except Exception:
        return 0


@functools.lru_cache(maxsize=1)
def is_feedback_ready() -> bool:
    """feedback.db 累计 distinct plans ≥ 50 → True。DB 异常 → False。

    lru_cache(maxsize=1) 避免每次 predict_batch 都打 DB（仿 baseline_lookup._load_default_baseline）。
    测试 monkey-patch FEEDBACK_DB_PATH 后需调 cache_clear()（Handoff §7 教训）。
    """
    return count_distinct_plans() >= FEEDBACK_READY_MIN_PLANS


# ── 单签名查询（maxsize=128） ──────────────────────────────────────
@functools.lru_cache(maxsize=128)
def lookup_feedback_ctr(signature: str) -> Optional[float]:
    """按 signature 查 feedback.db，返回 CTR 小数（0.025=2.5%）。

    未命中 / DB 缺失 / 异常 → None（_demo_pred 走 baseline × tm 兜底）。

    SQL 注入防护：参数化 `?`，绝不拼接。
    """
    if not signature or not FEEDBACK_DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(str(FEEDBACK_DB_PATH))
        try:
            row = conn.execute(
                """
                SELECT SUM(reach_success) AS reach, SUM(click_count) AS click
                FROM feedback_records
                WHERE task_signature = ?
                """,
                (signature,),
            ).fetchone()
            reach = int(row[0] or 0)
            click = int(row[1] or 0)
            if reach <= 0:
                return None
            from core.analytics_utils import weighted_ctr
            return weighted_ctr(click, reach, as_percent=False)  # 小数
        finally:
            conn.close()
    except Exception:
        return None


__all__ = [
    "FEEDBACK_READY_MIN_PLANS",
    "FEEDBACK_DB_PATH",
    "count_distinct_plans",
    "is_feedback_ready",
    "lookup_feedback_ctr",
]