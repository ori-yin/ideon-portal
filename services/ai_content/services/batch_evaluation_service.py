# -*- coding: utf-8 -*-
r"""
services/batch_evaluation_service.py — 批量文案评估 service

PRD §4.3 入口 C：上传 CSV/Excel 批量文案清单，逐条
- 规则检查（rule_engine.check_one）
- CTR 入口 B（ctr_prediction_service.predict_one）
- 优化建议（基于规则结果 + CTR 偏差）

与 records.db 区分：批量评估不落库（只读入口 C）。如果用户要保存，导出 CSV 后人工决定。

口径：
- 必填列：title + body + channel（三列最少）
- 兼容别名：标题/Title、content/Body/正文 等
- 渠道必须命中 CHANNELS，否则该行记 error 跳过
"""

from __future__ import annotations

import io
from typing import List, Dict, Any, Optional

import pandas as pd

from core.schemas import CHANNELS, RuleResult, PredictionResult
from services.rule_engine import load_rules, check_one
from services.ctr_prediction_service import predict_one
from core.csv_utils import read_table


# 列名别名（兼容多种命名）
_COL_ALIASES = {
    "title":  ["标题", "title", "标题文案", "headline", "subject"],
    "body":   ["正文", "body", "文案内容", "content", "text", "内容"],
    "channel": ["渠道", "channel", "投放渠道"],
    "plan_type": ["计划类型", "plan_type", "plan类型", "plantype"],
    "coupon": ["是否用券", "coupon", "用券"],
    "workday_type": ["工作日类型", "workday_type", "workday"],
}


def parse_batch_file(file_bytes: bytes, filename: str = "") -> pd.DataFrame:
    """读 CSV/Excel 文件 → DataFrame。自动识别 .csv / .xlsx。

    返回的列：title / body / channel（其他列原样保留）。
    Phase 17.5 改：底层走 core.csv_utils.read_table()。
    """
    return read_table(
        file_bytes, filename,
        col_aliases=_COL_ALIASES,
        required_cols=("title", "body", "channel"),
    )


def _build_suggestion(rule: RuleResult, ctr: PredictionResult) -> str:
    """拼一句优化建议（30 字内）。"""
    parts: list = []
    if rule.has_blocking:
        parts.append("存在阻断项")
    if ctr.result_type == "demo" and ctr.pred_ctr is not None and ctr.baseline_ctr is not None:
        diff = (ctr.pred_ctr - ctr.baseline_ctr) * 100
        if diff < -1:
            parts.append(f"低于基准 {abs(diff):.1f}pp")
        elif diff > 1:
            parts.append(f"高于基准 {diff:.1f}pp")
    if not parts:
        if ctr.suggestion:
            parts.append(ctr.suggestion[:20])
        else:
            parts.append("规则通过")
    return " · ".join(parts)[:60]


def evaluate_batch(
    df: pd.DataFrame,
    ctr_mode: str = "demo",
    progress_cb: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """批量评估 DataFrame。

    输入列：title / body / channel（其它列原样保留以便后续导出）
    返回：list[dict]，每行包含：
        - row_index / title / body / channel
        - rule_status / rule_fail_count / rule_warn_count
        - ctr_result_type / ctr_pred / ctr_baseline / ctr_confidence / ctr_error
        - suggestion（30 字内）
        - error（行级异常信息）
    progress_cb: 可选回调 fn(done, total)
    """
    channel_rules, brand_rules = load_rules()
    n = len(df)
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        r = df.iloc[i]
        title = str(r.get("title", "") or "")
        body = str(r.get("body", "") or "")
        channel = str(r.get("channel", "") or "")
        plan_type = str(r.get("plan_type", "") or "") or None
        coupon = str(r.get("coupon", "") or "") or None
        workday = str(r.get("workday_type", "") or "") or None

        out: Dict[str, Any] = {
            "row_index": i,
            "title": title,
            "body": body,
            "channel": channel,
            "rule_status": "",
            "rule_fail_count": 0,
            "rule_warn_count": 0,
            "ctr_result_type": "",
            "ctr_pred": None,
            "ctr_baseline": None,
            "ctr_confidence": None,
            "ctr_error": "",
            "suggestion": "",
            "error": "",
        }

        # 行级必填校验
        if not body:
            out["error"] = "正文为空"
            if progress_cb:
                progress_cb(i + 1, n)
            rows.append(out)
            continue
        if channel not in CHANNELS:
            out["error"] = f"渠道「{channel}」不在 {CHANNELS}"
            if progress_cb:
                progress_cb(i + 1, n)
            rows.append(out)
            continue

        try:
            rule = check_one(title, body, channel, channel_rules, brand_rules)
            out["rule_status"] = rule.status
            out["rule_fail_count"] = len(rule.fails)
            out["rule_warn_count"] = len(rule.warns)
        except Exception as e:
            out["error"] = f"规则检查失败：{e}"

        try:
            ctr = predict_one(title=title, body=body, channel=channel,
                              plan_type=plan_type, coupon=coupon, workday=workday, mode=ctr_mode)
            out["ctr_result_type"] = ctr.result_type
            out["ctr_pred"] = ctr.pred_ctr
            out["ctr_baseline"] = ctr.baseline_ctr
            out["ctr_confidence"] = ctr.confidence
            out["ctr_error"] = ctr.error or ""
        except Exception as e:
            out["ctr_error"] = f"CTR 失败：{e}"

        # 建议
        try:
            ctr_obj = PredictionResult(
                result_type=out["ctr_result_type"] or "unavailable",
                pred_ctr=out["ctr_pred"],
                baseline_ctr=out["ctr_baseline"],
                confidence=out["ctr_confidence"],
                error=out["ctr_error"] or None,
            )
            out["suggestion"] = _build_suggestion(rule, ctr_obj)
        except Exception:
            out["suggestion"] = ""

        rows.append(out)
        if progress_cb:
            progress_cb(i + 1, n)
    return rows


def rows_to_dataframe(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """评估结果 list → DataFrame，便于展示和导出。"""
    return pd.DataFrame(rows)


# ── records.db 落档（用户主动勾选，详 Phase 22 D）─────────────────
def batch_signature(row: Dict[str, Any]) -> str:
    """批量评估行的 signature（与 core.schemas.task_signature 字段一致）。

    字段：channel/coupon/plan_type/audience/stage/scene + 标题桶/正文桶
    batch 缺 audience/stage/scene → 空串
    SHA1 截前 12 位
    """
    import hashlib
    title = str(row.get("title", "") or "")
    body = str(row.get("body", "") or "")
    title_bucket = f"{(len(title) // 5) * 5}"
    body_bucket = f"{(len(body) // 10) * 10}"
    raw = (
        f"{row.get('channel', '')}|{row.get('coupon', '')}|"
        f"{row.get('plan_type', '')}|{row.get('audience', '')}|"
        f"{row.get('stage', '')}|{row.get('scene', '')}|"
        f"{title_bucket}|{body_bucket}"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def save_predictions_to_records(
    rows: List[Dict[str, Any]],
    db_path: Optional[str] = None,
) -> int:
    """把批量评估结果落档到 records.db。

    每条 row 包成单候选 GenerationRecord 写入（id="A"，strategy="batch_eval"）。
    仅保存 CTR 预测成功的行（ctr_result_type 非空）；签名 = batch_signature(row)。
    返回成功写入条数。
    """
    import json
    from datetime import datetime
    from repositories.sqlite_repository import save

    n_saved = 0
    now = datetime.now().isoformat(timespec="seconds")
    for r in rows:
        if not r.get("ctr_result_type"):
            continue
        try:
            task = {
                "channel": r.get("channel", ""),
                "plan_type": r.get("plan_type") or "未知",
                "coupon": r.get("coupon") or "未知",
                "audience": "",
                "stage": "",
                "scene": "",
            }
            cand = {
                "id": "A",
                "strategy": "batch_eval",
                "title": r.get("title", ""),
                "body": r.get("body", ""),
            }
            ctr_dict = {
                "result_type": r.get("ctr_result_type", ""),
                "pred_ctr": r.get("ctr_pred"),
                "baseline_ctr": r.get("ctr_baseline"),
                "confidence": r.get("ctr_confidence"),
                "error": r.get("ctr_error") or None,
                "source": f"batch_{r.get('ctr_result_type', 'unknown')}",
            }
            row_dict = {
                "task_json": json.dumps(task, ensure_ascii=False),
                "candidates_json": json.dumps([cand], ensure_ascii=False),
                "rule_results_json": None,
                "ctr_results_json": json.dumps([ctr_dict], ensure_ascii=False),
                "similar_summary_json": None,
                "selected_id": "A",
                "created_at": now,
                "signature": batch_signature(r),
            }
            save(row_dict, db_path=db_path)
            n_saved += 1
        except Exception:
            # 单行失败不影响其他行
            continue
    return n_saved


def rows_to_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    """评估结果 → CSV bytes（UTF-8 BOM，Excel 兼容）。"""
    df = rows_to_dataframe(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    return buf.getvalue()


__all__ = [
    "parse_batch_file",
    "evaluate_batch",
    "rows_to_dataframe",
    "rows_to_csv_bytes",
]