# -*- coding: utf-8 -*-
r"""
services/generation_service.py — 文案生成 service

PRD §9 文案生成服务：TaskInput → 3 条候选（A/B/C 策略不同）。
PRD §19.1 Demo 模式：无外部 API 也能完整运行，使用稳定占位候选。

Demo 模式候选（基于 channel + objective 字段，少量差异化，确保 A/B/C 表达不同）：
- A_核心利益直给：突出产品权益
- B_消费场景切入：绑定消费场景
- C_行动号召强化：强化动作词

LLM 模式：调 adapters/llm_adapter.call_llm + prompts/copy_generation.parse_response，
校验 3 条策略不重复、id 必须是 A/B/C、title/body 非空。失败抛 GenerationError。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from core.schemas import (
    TaskInput, Candidate, CANDIDATE_STRATEGIES,
    GenerationRecord, RuleResult, PredictionResult,
)
from prompts import copy_generation
from adapters.llm_adapter import call_llm
from core.llm_gateway import ProviderRouter


# ── 反哺影响生成排序（Handoff §6.2 #6 拍板）─────────────────────
def rank_candidates_by_ctr(
    candidates: list,
    ctr_results: list,
) -> tuple:
    """按 predicted_ctr 降序重排 candidates + ctr_results（同索引）。

    tie-break：CTR 相同时按 title 长度升序（短标题通常点击率高）。
    unavailable（pred_ctr is None）排最后，保持"有预测值的优先"。

    返回 (ranked_candidates, ranked_ctr_results) —— 长度不变，仅顺序改变。
    """
    if len(candidates) != len(ctr_results):
        raise ValueError(
            f"长度不一致：candidates={len(candidates)}, ctr_results={len(ctr_results)}"
        )

    def _sort_key(idx):
        ctr = ctr_results[idx].pred_ctr
        # None 当作 0；自然排到末尾
        ctr_val = ctr if ctr is not None else 0.0
        # 标题长度升序（短的优先）
        title_len = len(candidates[idx].title or "")
        return (-ctr_val, title_len)

    indices = sorted(range(len(candidates)), key=_sort_key)
    return (
        [candidates[i] for i in indices],
        [ctr_results[i] for i in indices],
    )


class GenerationError(Exception):
    """生成失败（PRD §22 异常处理）。"""
    pass


# ── Demo 模式占位候选（PRD §19.1 稳定占位）──────────────────────
def _demo_candidates(task: TaskInput) -> list:
    """3 条稳定占位候选，A/B/C 策略不同。

    Phase A.1 · 2026-08-28：
      - 原 product_benefit 拆为 product_category + benefit_type
      - 演示文本拼接：直接空格连接非空 token；都不空时用稳定兜底短语

    Phase 28 · 2026-09-01：
      - 可选字段值 == "通用" 时，跳过拼接（走通用兜底）
    """

    def _opt(v: str) -> str:
        v = (v or "").strip()
        if not v or v == "通用":
            return ""
        return v

    # A.1：组合成一段"产品-权益"短语，无值时给稳定兜底
    tokens = [t for t in (task.product_category, task.benefit_type) if _opt(t)]
    benefit = " ".join(tokens) if tokens else "新品限时优惠"
    scene = _opt(task.scene) or "日常"
    action = _opt(task.expected_action) or "查看"

    if task.channel == "短信":
        # 短信无标题，标题留空（rule_engine 会按渠道处理）
        return [
            Candidate(
                id="A", strategy="A_核心利益直给",
                title="", body=f"{benefit}，立即查看详情。回T退订",
                reason="短信无标题，正文突出权益+合规退订",
            ),
            Candidate(
                id="B", strategy="B_消费场景切入",
                title="", body=f"{scene}不知道吃什么？{benefit}，点击了解。回T退订",
                reason="场景化开场，关联消费时刻",
            ),
            Candidate(
                id="C", strategy="C_行动号召强化",
                title="", body=f"{benefit}，{action}领取优惠。回T退订",
                reason="结尾用动作词+合规退订",
            ),
        ]

    if task.channel == "企微1v1":
        return [
            Candidate(
                id="A", strategy="A_核心利益直给",
                title="", body=f"专属福利：{benefit}",
                reason="突出「专属」+「福利」命中企微1v1 必带词",
            ),
            Candidate(
                id="B", strategy="B_消费场景切入",
                title="", body=f"{scene}不知道吃什么？{benefit}",
                reason="场景化开场，亲切自然",
            ),
            Candidate(
                id="C", strategy="C_行动号召强化",
                title="", body=f"{benefit}，立即{action}",
                reason="结尾动作词引导下一步",
            ),
        ]

    # APP Push：默认带标题
    return [
        Candidate(
            id="A", strategy="A_核心利益直给",
            title=f"{benefit[:6]}来啦",
            body=f"新品优惠：{benefit}，点击查看详情。",
            reason="直接突出产品和权益，符合 A 策略",
        ),
        Candidate(
            id="B", strategy="B_消费场景切入",
            title=f"{scene}首选",
            body=f"{scene}不知道吃什么？{benefit}，限时优惠中。",
            reason=f"绑定 {scene} 场景，亲切感强",
        ),
        Candidate(
            id="C", strategy="C_行动号召强化",
            title="立即查看",
            body=f"{benefit}，{action}领取专属优惠。",
            reason="结尾用动作词，引导点击",
        ),
    ]


# ── LLM 模式 ───────────────────────────────────────────────────────
def _validate(rows: list) -> list:
    """校验 LLM 返回的 3 条候选。失败抛 GenerationError。"""
    if not isinstance(rows, list):
        raise GenerationError("LLM 返回不是数组")
    if len(rows) < 3:
        raise GenerationError(f"LLM 仅返回 {len(rows)} 条候选（需 3 条）")

    ids = [r.get("id", "") for r in rows[:3]]
    if set(ids) != {"A", "B", "C"}:
        raise GenerationError(f"候选 id 错误：{ids}（需 A/B/C）")

    strategies = [r.get("strategy", "") for r in rows[:3]]
    expected = ("A_核心利益直给", "B_消费场景切入", "C_行动号召强化")
    for i, (s, e) in enumerate(zip(strategies, expected)):
        if s != e:
            raise GenerationError(f"候选 {ids[i]} strategy 不匹配：{s}（需 {e}）")

    for r in rows[:3]:
        if not r.get("body", "").strip():
            raise GenerationError(f"候选 {r.get('id')} body 为空")

    return rows[:3]


def _llm_generate(task: TaskInput, router: ProviderRouter, channel_rules: dict) -> list:
    """LLM 模式生成。失败抛 GenerationError。"""
    sys_prompt = copy_generation.SYSTEM_PROMPT
    user_prompt = copy_generation.build_user_prompt(task, channel_rules)
    full_prompt = f"{sys_prompt}\n\n{user_prompt}"

    # 第 1 次
    raw = router.call(full_prompt)
    parsed = copy_generation.parse_response(raw)

    # 校验失败 → 第 2 次（PRD §9.3 允许有限一次修复）
    try:
        rows = _validate(parsed)
    except GenerationError:
        fix_prompt = (
            f"{full_prompt}\n\n"
            "上一次返回的格式不符合要求，请严格按以下 JSON 数组格式重新输出 3 条：\n"
            "[{\"id\":\"A\",\"strategy\":\"A_核心利益直给\",\"title\":\"...\",\"body\":\"...\",\"reason\":\"...\",\"risk_flags\":[],\"used_input_fields\":[]},"
            "{\"id\":\"B\",\"strategy\":\"B_消费场景切入\",...},"
            "{\"id\":\"C\",\"strategy\":\"C_行动号召强化\",...}]"
        )
        raw2 = router.call(fix_prompt)
        parsed2 = copy_generation.parse_response(raw2)
        rows = _validate(parsed2)

    return [
        Candidate(
            id=r["id"],
            strategy=r["strategy"],
            title=r.get("title", ""),
            body=r.get("body", ""),
            reason=r.get("reason", ""),
            risk_flags=r.get("risk_flags", []),
            used_input_fields=r.get("used_input_fields", []),
            provider=router.provider,
            model=router.model or "",
            prompt_version=copy_generation.VERSION,
        )
        for r in rows
    ]


# ── 主入口 ────────────────────────────────────────────────────────
def generate(
    task: TaskInput,
    router: Optional[ProviderRouter] = None,
    channel_rules: Optional[dict] = None,
) -> list:
    """生成 3 条候选。返回 list[Candidate]，长度 == 3。

    router 为 None 或无 api_key → Demo 模式（PRD §19.1）。
    channel_rules: channel_rules.yaml 加载的 dict（LLM 模式必传，Demo 模式可省）。
    """
    # 必填字段校验（兜底）
    if not task.is_complete:
        missing = [f for f in task.REQUIRED_FIELDS if not getattr(task, f)]
        raise GenerationError(f"必填字段缺失：{missing}")

    # Demo 模式：router 是 None 或无 api_key
    if router is None or not getattr(router, "api_key", None):
        candidates = _demo_candidates(task)
        for c in candidates:
            c.provider = "demo"
            c.model = ""
            c.prompt_version = copy_generation.VERSION
        return candidates

    # LLM 模式
    if channel_rules is None:
        from services.rule_engine import load_rules
        channel_rules, _ = load_rules()
    return _llm_generate(task, router, channel_rules)


# ── 完整保存（PRD §18）────────────────────────────────────────────
def build_record(
    task: TaskInput,
    candidates: list,
    selected_id: str,
    rule_results: Optional[list] = None,
    ctr_results: Optional[list] = None,
    similar_summary: Optional[dict] = None,
) -> GenerationRecord:
    """构造 GenerationRecord（含 created_at + signature）。"""
    from core.schemas import task_signature
    return GenerationRecord(
        task=task,
        candidates=candidates,
        selected_id=selected_id,
        rule_results=rule_results or [],
        ctr_results=ctr_results or [],
        similar_summary=similar_summary or {},
        created_at=datetime.now().isoformat(timespec="seconds"),
        signature=task_signature(task, candidates=candidates, selected_id=selected_id),
    )


# ── 读路径包装（CLAUDE.md §4.1：页面层不直调 repository）───────────
def read_recent(limit: int = 10000) -> list:
    """最近 limit 条 generation_records（按 id DESC，JSON 字段已解析）。

    给 05_feedback 的"与生成记录 join 情况"用——按 signature join 找匹配。
    """
    from repositories import sqlite_repository
    return sqlite_repository.list_all(limit=limit)


__all__ = ["GenerationError", "generate", "build_record", "rank_candidates_by_ctr", "read_recent"]
