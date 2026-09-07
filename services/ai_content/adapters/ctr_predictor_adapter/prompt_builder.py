# -*- coding: utf-8 -*-
r"""
prompt_builder.py — LLM prompt 构造（纯函数）

来源：C:\ideon\mcd-ctr-predictor\ctr_predictor.py 第 205-251 行（build_context_for_llm）。

Phase 1a 范围：
- build_context_for_llm：基准数据汇总字符串，给 LLM 当上下文
- enrich_rows_for_llm：每行拼 baseline CTR + 时段系数到 batch_text，
  拆自旧 call_llm_batch:259-284，Phase 1b 再接 ProviderRouter
"""

from __future__ import annotations
from typing import Optional

from .baseline_lookup import get_baseline, get_baseline_ctr, get_time_multiplier
from .char_utils import get_char_range


def build_context_for_llm(baseline: Optional[dict] = None) -> str:
    """构造 LLM prompt 的基准上下文段。

    来源：ctr_predictor.py:205-251
    输出结构：
    - 各渠道CTR基准
    - 用券效果
    - 时段CTR（小时粒度）
    - 各渠道高CTR标题字数区间（仅参考，prompt 已降权）
    - AARRPlan vs 常规Plan
    - 渠道×预算Owner（仅列高CTR组合）
    """
    bl = get_baseline(baseline=baseline)
    d = bl.get("dimensions", {})
    lines = ["【麦当劳Push CTR基准参考】（CTR数值为小数，0.0355 = 3.55%）"]

    ch_data = d.get("渠道", {}).get("data", {})
    if ch_data:
        lines.append("\n各渠道CTR基准：")
        for k, v in sorted(ch_data.items(), key=lambda x: -x[1]):
            lines.append(f"  {k}: {v*100:.2f}%")

    coupon_data = d.get("渠道_x_是否用券", {}).get("data", {})
    if coupon_data:
        lines.append("\n用券效果（带券 > 不带券）：")
        for k, v in sorted(coupon_data.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"  {k}: {v*100:.2f}%")

    time_data = d.get("时段_小时", {}).get("data", {})
    if time_data:
        lines.append("\n时段CTR（小时粒度，跨渠道加权）：")
        for k, v in sorted(time_data.items(), key=lambda x: int(x[0].replace("时", ""))):
            lines.append(f"  {k}: {v*100:.3f}%")

    char_data = d.get("渠道_x_标题字数", {}).get("data", {})
    if char_data:
        lines.append("\n各渠道高CTR标题字数区间（仅参考，降权）：")
        by_ch: dict = {}
        for k, v in char_data.items():
            ch, rng = k.split("_", 1)
            by_ch.setdefault(ch, []).append((rng, v))
        for ch, items in by_ch.items():
            top3 = sorted(items, key=lambda x: -x[1])[:3]
            lines.append(f"  {ch}: " + " | ".join(f"{rng}({v*100:.2f}%)" for rng, v in top3))

    plan_data = d.get("渠道_x_计划类型", {}).get("data", {})
    if plan_data:
        lines.append("\nAARRPlan vs 常规Plan（AARRPlan为算法精准触达）：")
        for k, v in sorted(plan_data.items(), key=lambda x: -x[1]):
            lines.append(f"  {k}: {v*100:.2f}%")

    owner_data = d.get("渠道_x_预算owner", {}).get("data", {})
    if owner_data:
        lines.append("\n渠道×预算Owner（仅列高CTR组合）：")
        for k, v in sorted(owner_data.items(), key=lambda x: -x[1])[:15]:
            lines.append(f"  {k}: {v*100:.2f}%")

    return "\n".join(lines)


def enrich_rows_for_llm(rows: list, baseline: Optional[dict] = None) -> list:
    """每行拼装 baseline CTR + 时段系数，返回富化后的行列表。

    来源：ctr_predictor.py:259-284（call_llm_batch 的批处理前半段）

    输入：rows = [{"标题", "内容", "渠道", "是否用券", "工作日类型",
                   "发送时间", "计划类型", "预算Owner"}, ...]
    输出：每行新增字段 _bl_str (e.g. "3.572%") 和 _tm (时段系数, float)

    Phase 1b 会把 _bl_str / _tm 喂给 ProviderRouter 拼最终 prompt。
    """
    enriched = []
    for row in rows:
        title = str(row.get("标题", ""))
        channel = str(row.get("渠道", "")).strip()
        coupon = str(row.get("是否用券", "")).strip()
        workday = str(row.get("工作日类型", "")).strip()
        time_s = str(row.get("发送时间", "")).strip()
        plan = str(row.get("计划类型", "")).strip()
        owner = str(row.get("预算Owner", "")).strip()

        plan_v = plan if plan in ("AARRPlan", "常规Plan") else None
        char_range_v = get_char_range(title) if title else None
        bl_ctr = get_baseline_ctr(channel, coupon or None, workday or None,
                                  plan_v, owner or None, char_range_v,
                                  baseline=baseline)
        bl_str = f"{bl_ctr*100:.3f}%" if bl_ctr else "未知"
        tm = get_time_multiplier(time_s, baseline=baseline)

        new_row = dict(row)
        new_row["_bl_str"] = bl_str
        new_row["_tm"] = tm
        # Phase-B demo 回灌：透传 _signature（来自 ctr_prediction_service._candidate_to_row）
        # 此处不生成 signature，仅透传；生成在 services 层（避免 prompt_builder 依赖 core.schemas）
        if "_signature" in row:
            new_row["_signature"] = row["_signature"]
        enriched.append(new_row)
    return enriched