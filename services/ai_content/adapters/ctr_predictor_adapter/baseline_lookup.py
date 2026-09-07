# -*- coding: utf-8 -*-
r"""
baseline_lookup.py — CTR baseline 查找（纯函数）

来源：C:\ideon\mcd-ctr-predictor\ctr_predictor.py 第 54-120 行（机械搬迁）。

Phase 1a 约束：
- 移除 @st.cache_data（CLAUDE.md §3 架构：cache_adapter 替 Streamlit 缓存）
- baseline dict 通过参数注入，避免模块级全局读取
- lazy load 单进程内 lru_cache 仅作性能优化，可被注入 baseline 覆盖

v3.1 口径（2026-08-26 业务拍板；Q1 去重点击 / Q2 触达成功 / Q3 plan 全周期不截断
/ Q4 跨渠道不聚合 / Q5 暂回退 min_reach 兜底 / bi_dt T-1 12 点前 INTERVAL 2；
详 docs/ctr-kpi-definition-proposal-v0.2.md）。本模块只读 baseline JSON 数值字段；
definition 注释在 data/ctr_baseline.json "_definition_note"，**不参与**
get_baseline_ctr 查询逻辑（避免硬编码口径）。
"""

from __future__ import annotations
import json
import re
import functools
from pathlib import Path
from typing import Optional


DEFAULT_BASELINE_PATH = Path(__file__).resolve().parents[2] / "data" / "ctr_baseline.json"


@functools.lru_cache(maxsize=1)
def _load_default_baseline() -> dict:
    """加载内置默认 baseline JSON（单进程内缓存）。"""
    p = DEFAULT_BASELINE_PATH
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_baseline(path: Optional[str] = None, baseline: Optional[dict] = None) -> dict:
    """获取 baseline dict。优先级：参数 baseline > 参数 path > 内置默认。"""
    if baseline is not None:
        return baseline
    if path is not None:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return {}
    return _load_default_baseline()


def get_baseline_ctr(
    channel: str,
    coupon: Optional[str] = None,
    workday: Optional[str] = None,
    plan_type: Optional[str] = None,
    owner: Optional[str] = None,
    char_range: Optional[str] = None,
    text_has_coupon: Optional[str] = None,
    baseline: Optional[dict] = None,
) -> Optional[float]:
    """按优先级回退查找 CTR：标题字数 > 计划类型 > Owner > 用券(实际) > 文案含券词 > 工作日 > 渠道整体。

    来源：ctr_predictor.py:54-85
    Phase 12 改动：
    - L76 修 "普通Plan"→"常规Plan" bug（baseline JSON 实际用"常规Plan"，
      之前这条永远走 fallback）
    - 新增 text_has_coupon 参数（Phase 12 #11 用券双字段之一；
      baseline JSON 暂无"渠道_x_文案含券词"维度 key → 走兜底）
    """
    ch = channel.strip()
    d = get_baseline(baseline=baseline).get("dimensions", {})

    # 标题字数优先
    if char_range and f"{ch}_{char_range}" in d.get("渠道_x_标题字数", {}).get("data", {}):
        return _apply_dimension_weights(
            d["渠道_x_标题字数"]["data"][f"{ch}_{char_range}"], "渠道_x_标题字数")

    # 渠道 × 计划类型
    if plan_type in ("AARRPlan", "常规Plan") and f"{ch}_{plan_type}" in d.get("渠道_x_计划类型", {}).get("data", {}):
        return _apply_dimension_weights(
            d["渠道_x_计划类型"]["data"][f"{ch}_{plan_type}"], "渠道_x_计划类型")

    # 渠道 × 预算owner
    if owner and f"{ch}_{owner}" in d.get("渠道_x_预算owner", {}).get("data", {}):
        return _apply_dimension_weights(
            d["渠道_x_预算owner"]["data"][f"{ch}_{owner}"], "渠道_x_预算owner")

    # 渠道 × 实际是否用券（form 字段，plan 维度）
    if coupon in ("是", "否"):
        v = d.get("渠道_x_是否用券", {}).get("data", {}).get(f"{ch}_{coupon}")
        if v:
            return _apply_dimension_weights(v, "渠道_x_是否用券")

    # 渠道 × 标题正文是否带券词（文案粒度，Phase 12 #11）
    if text_has_coupon in ("是", "否"):
        v = d.get("渠道_x_文案含券词", {}).get("data", {}).get(f"{ch}_{text_has_coupon}")
        if v:
            return _apply_dimension_weights(v, "渠道_x_文案含券词")

    # 渠道 × 工作日类型
    if workday in ("工作日", "非工作日"):
        v = d.get("渠道_x_工作日类型", {}).get("data", {}).get(f"{ch}_{workday}")
        if v:
            return _apply_dimension_weights(v, "渠道_x_工作日类型")

    # 渠道整体
    return _apply_dimension_weights(
        d.get("渠道", {}).get("data", {}).get(ch, None), "渠道")


def get_time_multiplier(time_str: str, baseline: Optional[dict] = None) -> float:
    """时段系数（0.5 ~ 2.5）。四级回退：HH:MM > 区间 > HH时 > 任意数字。

    来源：ctr_predictor.py:88-120
    区间分支必须在 HH时 之前（否则 "8-10时" 会被抢先匹配成 10）。
    """
    if not time_str:
        return 1.0
    s = str(time_str).strip()
    hour = None
    m = re.search(r"(\d{1,2})\s*:\s*\d{1,2}", s)
    if m:
        hour = int(m.group(1))
    else:
        m = re.search(r"(\d{1,2})\s*[-~]\s*(\d{1,2})", s)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            hour = (lo + hi) // 2 if lo <= hi else (hi + lo) // 2
        else:
            m = re.search(r"(\d{1,2})\s*时", s)
            if m:
                hour = int(m.group(1))
            else:
                m = re.search(r"(\d{1,2})", s)
                if m:
                    hour = int(m.group(1))
    if hour is None or not (0 <= hour <= 23):
        return 1.0
    td = get_baseline(baseline=baseline).get("dimensions", {}).get("时段_小时", {}).get("data", {})
    if not td:
        return 1.0
    vals = list(td.values())
    overall_avg = sum(vals) / len(vals) if vals else 0.002
    hour_ctr = td.get(f"{hour}时", overall_avg)
    mult = hour_ctr / overall_avg if overall_avg else 1.0
    return max(0.5, min(2.5, mult))


# ── P3 维度级 baseline 微调（来自 config/dimension_weights.yaml） ──
@functools.lru_cache(maxsize=1)
def _load_dimension_modifiers() -> dict:
    """读 dimension_weights.yaml 的 baseline_modifiers 段；缺失/异常 → {}。"""
    p = Path(__file__).resolve().parents[2] / "config" / "dimension_weights.yaml"
    if not p.exists():
        return {}
    try:
        import yaml
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return doc.get("baseline_modifiers", {}) or {}
    except Exception:
        return {}


def _apply_dimension_weights(raw_bl: Optional[float], dim_key: str) -> Optional[float]:
    """维度级微调：raw_bl * weight（weight ∈ [0.5, 2.0]，缺维度默认 1.0）。

    不破坏 get_baseline_ctr 6 维回退优先级，仅对回退后的 raw_bl 乘 modifier。
    raw_bl 为 None 时透传 None（_demo_pred / _baseline_only_pred 拿 None 显示"无基准"）。
    """
    if raw_bl is None:
        return None
    w = float(_load_dimension_modifiers().get(dim_key, 1.0))
    w = max(0.5, min(2.0, w))  # clamp 防止越界
    return round(raw_bl * w, 5)