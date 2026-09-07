# -*- coding: utf-8 -*-
r"""
services/feedback_service.py — 真实投放结果回流 service

PRD §回流闭环（docs/feedback-ctr.md）：
- CSV/Excel → list[dict]（回流数据行）
- signature 计算（与 core/schemas.task_signature 一致）
- 写入 repositories/feedback_repository

数据契约：
- 必填列：task_signature / channel / reach_success / click_count
- 可选列：coupon / plan_type / sent_date / order_count
- 没有 signature 时按业务字段自动算（channel + coupon + plan_type）
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd

from core.schemas import task_signature as _core_task_signature, TaskInput
from core.csv_utils import read_table


# 列名别名（兼容多种命名）
_COL_ALIASES = {
    "task_signature": ["task_signature", "signature", "签名", "指纹"],
    "channel":        ["channel", "渠道"],
    "coupon":         ["coupon", "是否用券"],
    "plan_type":      ["plan_type", "计划类型", "plantype"],
    "sent_date":      ["sent_date", "发送日期", "日期"],
    "reach_success":  ["reach_success", "reach", "触达成功", "触达"],
    "click_count":    ["click_count", "click", "点击", "点击人次"],
    "order_count":    ["order_count", "order", "下单", "下单人次"],
    "title":          ["title", "标题"],
    "body":           ["body", "内容", "正文"],
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_feedback_file(file_bytes: bytes, filename: str = "") -> pd.DataFrame:
    """读 CSV/Excel → DataFrame。列名标准化 + 类型转换。

    Phase 17.5 改：底层走 core.csv_utils.read_table() 复用统一 CSV reader。
    """
    # task_signature/channel 是字符串类型，不能像 reach/click 那样填 0；用 read_table 默认填空
    # 后再覆盖类型转换逻辑
    df = read_table(
        file_bytes, filename,
        col_aliases=_COL_ALIASES,
        required_cols=("task_signature", "channel"),
    )

    # 必填列填空（数值列填 0）
    for col in ("reach_success", "click_count"):
        if col not in df.columns:
            df[col] = 0

    # 类型转换
    df["channel"] = df["channel"].astype(str).fillna("").str.strip()
    df["task_signature"] = df["task_signature"].astype(str).fillna("").str.strip()
    for col in ("reach_success", "click_count", "order_count"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "sent_date" in df.columns:
        df["sent_date"] = pd.to_datetime(df["sent_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    return df


def autofill_signature(df: pd.DataFrame) -> pd.DataFrame:
    """如果 task_signature 为空，按 channel + coupon + plan_type 兜底算。

    仅在没有 title/body/字数桶的情况下用，所以 fingerprint 只是"维度组合"
    而非真正的文案指纹——P2 校准时仍优先 join generation_records。
    """
    import hashlib

    if "task_signature" not in df.columns:
        return df

    def _mk(row):
        sig = str(row.get("task_signature") or "").strip()
        if sig:
            return sig
        ch = str(row.get("channel") or "")
        cp = str(row.get("coupon") or "未知")
        pt = str(row.get("plan_type") or "未知")
        raw = f"{ch}|{cp}|{pt}|auto"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    df["task_signature"] = df.apply(_mk, axis=1)
    return df


def to_records(
    df: pd.DataFrame,
    source: str = "",
) -> List[Dict[str, Any]]:
    """DataFrame → list[dict]，可直接写入 feedback_repository。

    Phase 16 · 2026-08-27 新增 text_has_coupon 推断：
    - 如果 DataFrame 有"标题"列，调 classify_coupon_in_text 推断每行的"是"/"否"
    - 无"标题"列则 text_has_coupon = None（calibrate_baseline 会跳过该维度聚合）
    """
    df = autofill_signature(df)
    # Phase 16+17.5：若有 title 列则推断 text_has_coupon（懒加载避免循环依赖）。
    # 批量向量化版本（classify_coupon_batch）比逐行 apply 快 50-100x。
    inferred_text = None
    if "title" in df.columns or "body" in df.columns:
        from core.text_classifier import classify_coupon_batch
        title_s = df["title"] if "title" in df.columns else pd.Series([""] * len(df))
        body_s = df["body"] if "body" in df.columns else pd.Series([""] * len(df))
        results = classify_coupon_batch(title_s, body_s)
        inferred_text = [v if v in ("是", "否") else None for v in results]

    out: list = []
    now = _now_iso()
    for i, (_, row) in enumerate(df.iterrows()):
        r = {
            "task_signature": str(row.get("task_signature") or "").strip(),
            "channel":        str(row.get("channel") or "").strip(),
            "coupon":         str(row.get("coupon") or "") or None,
            "plan_type":      str(row.get("plan_type") or "") or None,
            "sent_date":      str(row.get("sent_date") or "") or None,
            "reach_success":  int(row.get("reach_success") or 0),
            "click_count":    int(row.get("click_count") or 0),
            "order_count":    int(row.get("order_count") or 0),
            "source":         source,
            "imported_at":    now,
            "text_has_coupon": (inferred_text[i] if inferred_text is not None else None),
        }
        out.append(r)
    return out


def validate_records(records: List[Dict[str, Any]]) -> List[str]:
    """批量校验：返回错误信息列表（空 list 表示全部合法）。"""
    errs: list = []
    for i, r in enumerate(records):
        if not r.get("task_signature"):
            errs.append(f"行 {i+1}: task_signature 为空")
        if not r.get("channel"):
            errs.append(f"行 {i+1}: channel 为空")
        if int(r.get("reach_success") or 0) <= 0:
            errs.append(f"行 {i+1}: reach_success 必须 > 0")
        if int(r.get("click_count") or 0) < 0:
            errs.append(f"行 {i+1}: click_count 不能 < 0")
    return errs


def import_feedback(
    file_bytes: bytes,
    filename: str = "",
    source_label: str = "",
) -> Dict[str, Any]:
    """一站式：解析 + 校验 + 写入。返回 {"n": N, "errors": [...], "df": DataFrame}。"""
    df = parse_feedback_file(file_bytes, filename)
    records = to_records(df, source=source_label or filename or "upload")
    errors = validate_records(records)
    if errors:
        return {"n": 0, "errors": errors, "df": df, "records": records}

    from repositories import feedback_repository
    n = feedback_repository.save_batch(records)
    return {"n": n, "errors": [], "df": df, "records": records}


# ── 读路径包装（CLAUDE.md §4.1：页面层不直调 repository）───────────
def count() -> int:
    """feedback.db 总记录数。"""
    from repositories import feedback_repository
    return feedback_repository.count()


def aggregate_by_signature() -> dict:
    """按 task_signature 聚合（plan 加权 CTR / n_records / date range）。"""
    from repositories import feedback_repository
    return feedback_repository.aggregate_by_signature()


def read_recent(limit: int = 50) -> List[dict]:
    """最近 limit 条回流记录（按 id DESC）。"""
    from repositories import feedback_repository
    return feedback_repository.list_all(limit=limit)


__all__ = [
    "parse_feedback_file",
    "autofill_signature",
    "to_records",
    "validate_records",
    "import_feedback",
    "count",
    "aggregate_by_signature",
    "read_recent",
]