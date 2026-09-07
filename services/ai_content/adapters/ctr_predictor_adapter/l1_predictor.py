# -*- coding: utf-8 -*-
r"""
adapters/ctr_predictor_adapter/l1_predictor.py — L1 LightGBM 生产接入

Phase 19 设计：
- L1 是 PoC 训练出的 LightGBM 模型（data/lgbm_model_v1.pkl + lgbm_feature_meta.json）
- 与 CTRPredictionAdapter 同口径"四态分明"，便于 UI 层无缝接入：
    - "model":       模型文件 + 元信息齐全 + 特征列对齐 → 返回预测 CTR
    - "demo":        仅作占位（模型暂时不可用，UI 不展示 L1，避免误导）
    - "baseline_only": 模型不可用，回退到 baseline（与 L0 一致口径，便于双轨对比）
    - "unavailable": 严重错误（缺模型/缺元信息/特征列缺失且无法补救）→ UI 静默隐藏
- 默认 silent：调用方不传 show_l1=True 时，predict_l1 返回 (None, "unavailable")，
  UI 不会显示 L1 列；只有管理员开启"显示 L1 实验对比"才真预测。
- 特征工程严格对齐 tools/train_lgbm.py：
    - 数值：title_len / content_len / has_emoji / has_digit / has_question / eff_word_count
    - one-hot：channel / coupon / workday_type
    - cross：ch_x_wd_APP_Push_ / ch_x_wd_企微1v1_ / ch_x_wd_短信_
    - TE：plan_type_te（按训练集的 plan_type_te_map + global_mean）
- logit 目标变换：预测输出在 logit 空间 → 反 sigmoid

约束（CLAUDE.md §4.1）：
- 本模块不得 import 任何 LLM SDK
- 页面层统一通过 ctr_predictor_adapter.__init__ 间接访问
"""

from __future__ import annotations

import json
import pickle
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd


# ── 路径 ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "data" / "lgbm_model_v1.pkl"
META_PATH = ROOT / "data" / "lgbm_feature_meta.json"
EFFECTIVE_WORDS_PATH = ROOT / "data" / "effective_words.json"

# 与 train_lgbm.py 保持一致
EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF"
    r"\U0001F000-\U0001F0FF\U00002B00-\U00002BFF"
    r"\U00002190-\U000021FF\U0000231A-\U0000231B]"
)

# L1 训练时只用了 3 个渠道，企微/小程序等其他渠道 L1 无训练数据 → unavailable
L1_SUPPORTED_CHANNELS = ("APP Push", "企微1v1", "短信")


# ── 工具 ──────────────────────────────────────────────────────────
def _safe_sigmoid(x: float) -> float:
    """logit 反变换：sigmoid(x) = 1 / (1 + e^-x)；clamp 防 0/1 边界。"""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return float("nan")
    x = float(x)
    # 防 overflow
    if x >= 0:
        z = np.exp(-x)
        return float(1.0 / (1.0 + z))
    z = np.exp(x)
    return float(z / (1.0 + z))


def _has_emoji(text: str) -> int:
    if not text:
        return 0
    return 1 if EMOJI_RE.search(str(text)) else 0


def _has_digit(text: str) -> int:
    return 1 if re.search(r"\d", str(text or "")) else 0


def _has_question(text: str) -> int:
    s = str(text or "")
    return 1 if ("？" in s or "?" in s) else 0


def _workday_type_from_str(value) -> str:
    """把外部传入的 workday 规范化成 '' | '工作日' | '非工作日'。

    接受：
    - "工作日" / "非工作日"：直接透传
    - ISO 日期字符串 / pd.Timestamp / datetime：按 weekday 判
    - None / "" / 其他：返回 ''（不进入 one-hot）
    """
    if value is None or value == "":
        return ""
    if value in ("工作日", "非工作日"):
        return str(value)
    try:
        ts = pd.to_datetime(value)
        if pd.notna(ts):
            return "非工作日" if ts.weekday() >= 5 else "工作日"
    except Exception:
        pass
    return ""


def _normalize_coupon(coupon) -> str:
    """用券字段归一：未知/None/空 → '未知'，其余原样。"""
    if coupon is None or coupon == "" or coupon == "未知":
        return "未知"
    return str(coupon)


def _normalize_channel(channel) -> str:
    if channel is None or channel == "":
        return ""
    return str(channel)


@lru_cache(maxsize=1)
def _load_effective_words() -> Tuple[str, ...]:
    """高效词命中词典（与 train_lgbm 共用 data/effective_words.json）。"""
    if not EFFECTIVE_WORDS_PATH.exists():
        return tuple()
    try:
        with open(EFFECTIVE_WORDS_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        return tuple(doc.get("top_words", []))
    except Exception:
        return tuple()


def _count_eff_words(title: str) -> int:
    """jieba 切词 + 交集；jieba 不可用时退化子串匹配（与 train_lgbm 一致）。"""
    words = _load_effective_words()
    if not title or not words:
        return 0
    try:
        import jieba
        toks = set(jieba.lcut(str(title)))
        return len(toks & set(words))
    except Exception:
        s = str(title)
        return sum(1 for w in words if w in s)


# ── 模型 + 元信息加载（懒加载 + lru_cache 兜底）────────────────────
@lru_cache(maxsize=1)
def _load_model_and_meta() -> Tuple[Optional[object], Optional[dict]]:
    """加载 pkl + meta；失败返回 (None, None) 不抛异常。

    返回值约定：
    - (booster, meta)：模型 + 元信息都齐全
    - (None, None)：不可用（缺文件 / 损坏 / 元信息缺失）
    """
    if not MODEL_PATH.exists() or not META_PATH.exists():
        return None, None
    try:
        with open(MODEL_PATH, "rb") as f:
            booster = pickle.load(f)
        with open(META_PATH, encoding="utf-8") as f:
            meta = json.load(f)
        # 最低必要字段校验
        if not isinstance(meta, dict) or "feature_columns" not in meta:
            return None, None
        return booster, meta
    except Exception:
        return None, None


# ── 四态 status ─────────────────────────────────────────────────
def predict_l1_status() -> str:
    """返回 L1 当前可用状态（UI 调试 & sidebar 显示用）。

    - "model":         模型 + meta 都在，且 feature_columns 非空
    - "baseline_only": 模型缺（或 meta 缺）→ 业务侧无可预测
    - "unavailable":   当前实现不会到这里（model/baseline_only 已穷尽业务态）；
                      保留字以备未来 schema 校验失败
    """
    booster, meta = _load_model_and_meta()
    if booster is not None and meta is not None:
        return "model"
    return "baseline_only"


# ── 单条特征构造 ─────────────────────────────────────────────
def _build_feature_row(
    *,
    title: str,
    body: str,
    channel: str,
    plan_type: Optional[str],
    coupon: Optional[str],
    workday: Optional[str],
    meta: dict,
) -> Optional[pd.DataFrame]:
    """构造与训练时完全一致的 1 行特征矩阵；列不对齐 → 返回 None（业务侧降级）。"""
    feat = pd.DataFrame([{
        "title_len": len(title or ""),
        "content_len": len(body or ""),
        "has_emoji": _has_emoji(title),
        "has_digit": _has_digit(title),
        "has_question": _has_question(title),
        "eff_word_count": _count_eff_words(title),
    }])

    ch = _normalize_channel(channel)
    cp = _normalize_coupon(coupon)
    wd = _workday_type_from_str(workday)

    # 渠道 one-hot（空值→ 不产生 dummy 列，训练时也无 unknown 渠道）
    ch_dummies = pd.get_dummies(pd.Series([ch]), prefix="channel", dtype=int)
    ch_dummies.columns = [c.replace(" ", "_") for c in ch_dummies.columns]
    feat = pd.concat([feat, ch_dummies], axis=1)

    # 用券 one-hot（默认 "未知"）
    cp_dummies = pd.get_dummies(pd.Series([cp]), prefix="coupon", dtype=int)
    cp_dummies.columns = [c.replace(" ", "_") for c in cp_dummies.columns]
    feat = pd.concat([feat, cp_dummies], axis=1)

    # 工作日 one-hot（默认 '' → 不产生 dummy 列）
    if wd:
        wd_dummies = pd.get_dummies(pd.Series([wd]), prefix="workday_type", dtype=int)
        wd_dummies.columns = [c.replace(" ", "_") for c in wd_dummies.columns]
        feat = pd.concat([feat, wd_dummies], axis=1)

    # 渠道×工作日 cross（空值→ 不产生）
    if ch and wd:
        ch_x_wd = pd.get_dummies(
            pd.Series([f"{ch}_{wd}"]), prefix="ch_x_wd", dtype=int,
        )
        ch_x_wd.columns = [c.replace(" ", "_") for c in ch_x_wd.columns]
        feat = pd.concat([feat, ch_x_wd], axis=1)

    # 计划类型 target encoding（按训练集 map + global_mean）
    te_map = meta.get("plan_type_te_map", {})
    global_mean = meta.get("plan_type_global_mean", 0.01)
    pt_raw = plan_type if plan_type and plan_type != "未知" else None
    pt_value = te_map.get(pt_raw, global_mean) if pt_raw else global_mean
    feat["plan_type_te"] = float(pt_value)

    # 对齐训练时特征列：缺列补 0，多余列丢掉
    target_cols = list(meta["feature_columns"])
    for c in target_cols:
        if c not in feat.columns:
            feat[c] = 0
    feat = feat[target_cols]
    return feat


# ── 单条预测（主入口）───────────────────────────────────────
def predict_l1(
    *,
    title: str,
    body: str = "",
    channel: str,
    plan_type: Optional[str] = None,
    coupon: Optional[str] = None,
    workday: Optional[str] = None,
) -> Tuple[Optional[float], str]:
    """L1 单条预测。返回 (pred_ctr 或 None, status)。

    status 四态：
    - "model":         预测成功，pred_ctr 是 CTR 小数（如 0.025 = 2.5%）
    - "baseline_only": 模型或元信息缺失 → (None, "baseline_only")
    - "unavailable":   渠道不在 L1 训练范围内（小程序 / 站内信 / 微信模板等）
                       或特征构造失败 → (None, "unavailable")

    注意：返回 None 表示无值；不要把 (None, "model") 当作有效预测。
    """
    booster, meta = _load_model_and_meta()
    if booster is None or meta is None:
        return None, "baseline_only"

    # 渠道校验：训练集只覆盖 3 个渠道，其他渠道 L1 学不到
    ch = _normalize_channel(channel)
    if ch not in L1_SUPPORTED_CHANNELS:
        return None, "unavailable"

    feat = _build_feature_row(
        title=title or "",
        body=body or "",
        channel=ch,
        plan_type=plan_type,
        coupon=coupon,
        workday=workday,
        meta=meta,
    )
    if feat is None or feat.empty:
        return None, "unavailable"

    try:
        y_logit = booster.predict(feat)[0]
        ctr = _safe_sigmoid(y_logit)
        if np.isnan(ctr) or ctr < 0 or ctr > 1:
            return None, "unavailable"
        return float(ctr), "model"
    except Exception:
        # 任何推理异常都不抛 — 静默降级（双轨场景下 L0/L1 双跑，L1 失败不影响主流程）
        return None, "unavailable"


# ── 批量（双轨对比用，UI 调用）────────────────────────────
def predict_l1_batch(rows: list) -> list:
    """批量预测，返回 [(pred_ctr, status), ...]，长度 == len(rows)。

    row 期望包含：title / body / channel / plan_type / coupon / workday
    缺字段自动 fallback 到默认值（避免 KeyError）。
    """
    booster, meta = _load_model_and_meta()
    if booster is None or meta is None:
        return [(None, "baseline_only")] * len(rows)

    results = []
    for r in rows:
        results.append(predict_l1(
            title=r.get("title", "") or "",
            body=r.get("body", "") or "",
            channel=r.get("channel", "") or "",
            plan_type=r.get("plan_type"),
            coupon=r.get("coupon"),
            workday=r.get("workday"),
        ))
    return results


__all__ = [
    "predict_l1",
    "predict_l1_batch",
    "predict_l1_status",
    "L1_SUPPORTED_CHANNELS",
]