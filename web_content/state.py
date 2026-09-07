# -*- coding: utf-8 -*-
r"""
web/state.py — 5 个页面的内存 session state

【重要限制】
单进程内存字典；多用户并发访问会互相覆盖。
生产环境必须替换为：
  - Redis（推荐）
  - FastAPI SessionMiddleware + cookie（轻量）
  - DB-backed session store

DataFrame 不直接放 dict（pandas 对象不能 JSON 化），
而是用 `df_registry` 这个独立 dict 存对象，state 里只放 id 引用。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Optional
import pandas as pd


# ============================================================
# 01 内容工坊
# ============================================================
S_01: dict[str, Any] = {
    "task_input": None,
    "candidates": [],
    "selected_id": "A",
    "rule_results": [],
    "ctr_results": [],
    "similar_summary": {},
    "last_generated_signature": "",
    "show_l1": False,
    "ctr_mode": "baseline_only",
    "last_error": None,
    "ctr_mode_options": ("demo", "baseline_only", "l1_model"),
}


# ============================================================
# 02 内容诊断
# ============================================================
S_02: dict[str, Any] = {
    "title": "",
    "body": "",
    "channel": "APP Push",
    "action": "regen",
    "rule": None,                # dict
    "diagnose": None,            # dict
    "similar_summary": {},
    "similar_rows": [],          # 前 5 条
    "ctr": None,                 # dict
    "rewrites": [],              # list[dict]
    "rewrite_error": "",
    "rewrite_note": "",          # 用户改写备注（传给 LLM 当额外要求）
    "error_msg": "",
}


# ============================================================
# 03 批量评估
# ============================================================
S_03: dict[str, Any] = {
    "filename": "",
    "df_ref": None,              # df_registry key
    "n_rows": 0,
    "has_title": False,
    "has_body": False,
    "has_channel": False,
    "n_valid_channels": 0,
    "n_total_channels": 0,
    "preview_rows": [],          # 前 5 条 list[dict]
    "can_eval": False,
    "save_to_records": False,
    "eval_done": False,
    "result_rows": [],           # list[dict]
    "result_csv_bytes": None,
    "error_msg": "",
    "success_msg": "",
    "n_pass": 0,
    "n_warn": 0,
    "n_blocked": 0,
    "n_ctr_ok": 0,
    "n_err": 0,
    "channel_chips": "",
}


# ============================================================
# 04 历史洞察
# ============================================================
S_04: dict[str, Any] = {
    "filename": "",
    "df_ref": None,
    "n_rows": 0,
    "n_has_copy": None,
    "n_channels": 0,
    "channels": [],
    "date_range": "",
    "error_msg": "",
}


# ============================================================
# 05 真实结果回流
# ============================================================
S_05: dict[str, Any] = {
    "error_msg": "",
    "success_msg": "",
}


# ============================================================
# DataFrame 注册表（04 / 03 共用）
# key: int 引用 id，value: pd.DataFrame
# ============================================================
_df_registry: dict[int, pd.DataFrame] = {}
_df_counter = 0


def store_df(df: pd.DataFrame) -> int:
    """存 DataFrame，返回引用 id。"""
    global _df_counter
    _df_counter += 1
    _df_registry[_df_counter] = df
    return _df_counter


def get_df(ref_id: Optional[int]) -> Optional[pd.DataFrame]:
    """取 DataFrame；ref_id 无效返回 None。"""
    if ref_id is None:
        return None
    return _df_registry.get(ref_id)


def release_df(ref_id: Optional[int]) -> None:
    if ref_id is not None and ref_id in _df_registry:
        del _df_registry[ref_id]


# ============================================================
# 04 历史洞察 per-tab 缓存
# ============================================================
# 切 tab / 调 slider 不变 df 也不变参数时直接命中，避免每次 GET /insights 重算
# rank_plans / word_frequency / emoji_frequency / daily_trend / owner_compare 等。
# key: (df_ref, tab, frozenset(params.items())) — df_ref 变化自动失效（用户上传新文件）。
# 单进程内最多 64 条 LRU，单条 ~10-50 KB → 上限 ~3 MB。
_INSIGHTS_CACHE: "OrderedDict[tuple, Any]" = OrderedDict()
_INSIGHTS_CACHE_MAX = 64


def insights_cache_get(key: tuple) -> Optional[Any]:
    """按 key 取缓存；LRU 命中时移到末尾。miss 返回 None。"""
    if key in _INSIGHTS_CACHE:
        _INSIGHTS_CACHE.move_to_end(key)
        return _INSIGHTS_CACHE[key]
    return None


def insights_cache_put(key: tuple, value: Any) -> None:
    """写缓存；超 max 时 LRU 淘汰最旧条目。"""
    _INSIGHTS_CACHE[key] = value
    _INSIGHTS_CACHE.move_to_end(key)
    while len(_INSIGHTS_CACHE) > _INSIGHTS_CACHE_MAX:
        _INSIGHTS_CACHE.popitem(last=False)


def insights_cache_clear() -> None:
    """上传新文件时调用，清掉所有旧 df 的缓存。"""
    _INSIGHTS_CACHE.clear()


# ============================================================
# Helpers
# ============================================================
def reset_01() -> None:
    """清空 01 state。"""
    for k in list(S_01.keys()):
        if k == "ctr_mode_options":
            continue
        S_01[k] = type(S_01[k])() if isinstance(S_01[k], (list, dict, str)) else None
    S_01["selected_id"] = "A"
    S_01["ctr_mode"] = "baseline_only"
    S_01["last_error"] = None


def form_change_signature(t: dict) -> str:
    keys = (
        "product_category", "benefit_type", "audience", "channel",
        "objective", "stage", "scene", "tone", "expected_action",
        "plan_type", "coupon", "extra_requirements",
    )
    return "|".join(str(t.get(k, "")) for k in keys)
