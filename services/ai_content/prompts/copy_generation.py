# -*- coding: utf-8 -*-
r"""
prompts/copy_generation.py — 生成 3 条候选的 Prompt 模板

PRD §10 Prompt 版本管理：
- Prompt 放独立目录（prompts/）
- 每次修改升级 VERSION
- 保存记录时记 prompt_version（GenerationRecord.candidates[*].prompt_version）

PRD §7.2 三策略（A/B/C 不得重复）：
- A_核心利益直给：直接说明产品/权益/优惠
- B_消费场景切入：从具体场景和用户需求进入
- C_行动号召强化：强化目标动作（不虚构紧迫性）

PRD §3.3 AI 只生成候选 — Prompt 强调"候选不直接投放"。
"""

from __future__ import annotations

from core.schemas import TaskInput


VERSION = "v1.2"


SYSTEM_PROMPT = """你是麦当劳企微 1v1 / Push 文案顾问。基于输入的"经营任务"生成 3 条候选内容。

输出 JSON 数组（不要 markdown 围栏、不要解释前缀、不要换行包裹）：
[
  {
    "id": "A",
    "strategy": "A_核心利益直给",
    "title": "...",
    "body": "...",
    "reason": "为什么这条匹配任务",
    "risk_flags": [],
    "used_input_fields": ["product_category", "benefit_type", "campaign_stage", ...]
  },
  {"id": "B", "strategy": "B_消费场景切入", ...},
  {"id": "C", "strategy": "C_行动号召强化", ...}
]

硬约束：
- 严格 3 条，id 必须是 A、B、C
- 3 条 strategy 文本必须分别为：A_核心利益直给 / B_消费场景切入 / C_行动号召强化（不得重复）
- title / body 不得为空
- 不编造未输入的事实（不得虚构价格 / 日期 / 库存）
- 如有"额外要求"（不得使用某词 / 必须包含某词），必须严格执行
- 文案是候选，最终由业务人员人工确认后才能投放
- 真实使用品牌"麦当劳"或产品名时按业务侧确认的输入使用，不要凭空加
"""


def build_user_prompt(task: TaskInput, channel_rules: dict) -> str:
    """拼装 user prompt。channel_rules 是 config/channel_rules.yaml 加载的 dict。

    Phase A.1 · 2026-08-28：
      - 原 product_benefit 字段拆为 product_category + benefit_type 两行
      - 任一为空时该行不拼（避免 prompt 里出现"产品类别："空值）
      - 都不为空时拼 2 行（产品类别 / 权益类型）

    Phase 28 · 2026-09-01：
      - 必填 3 项（audience / channel / tone）硬拼
      - 其余字段：值为空 或 等于 "通用" 时整行不拼（让 AI 自由发挥）
    """

    def _opt(v: str) -> str:
        """可选字段：空 或 「通用」 → ''；否则原样。"""
        v = (v or "").strip()
        if not v or v == "通用":
            return ""
        return v

    rules = channel_rules.get(task.channel, {})
    title_max = rules.get("title_max", 15)
    body_max = rules.get("body_max", 60)
    emoji_max = rules.get("emoji_max", 2)

    parts = [
        "【经营任务】",
        # 必填 3 项：始终硬拼（pipeline 依赖）
        f"目标人群：{task.audience}",
        f"投放渠道：{task.channel}",
        f"内容语气：{task.tone}",
    ]
    # 可选项：空或「通用」时整行不拼（让 AI 自由发挥）
    if _opt(task.stage):
        parts.append(f"活动阶段：{task.stage}")
    if _opt(task.scene):
        parts.append(f"消费场景：{task.scene}")
    if _opt(task.product_category):
        parts.append(f"产品类别：{task.product_category}")
    if _opt(task.benefit_type):
        parts.append(f"权益类型：{task.benefit_type}")
    if _opt(task.objective):
        parts.append(f"投放目标：{task.objective}")
    if _opt(task.expected_action):
        parts.append(f"期望动作：{task.expected_action}")
    if _opt(task.plan_type):
        parts.append(f"Plan 类型：{task.plan_type}")
    if _opt(task.coupon):
        parts.append(f"是否用券：{task.coupon}")
    if _opt(task.text_has_coupon):
        parts.append(f"文案含券词：{task.text_has_coupon}")
    if _opt(task.planned_send_date):
        parts.append(f"计划投放日期：{task.planned_send_date}")
    if task.extra_requirements:
        parts.append(f"额外要求：{task.extra_requirements}")

    parts.append("")
    parts.append("【渠道字数约束】")
    parts.append(f"标题上限：{title_max} 字（0 表示不需要独立标题）")
    parts.append(f"正文字数上限：{body_max} 字")
    parts.append(f"emoji 上限：{emoji_max} 个")
    parts.append("注意：渠道字数超出会被程序判定为阻断项，请严格控制。")
    return "\n".join(parts)


def parse_response(raw: str) -> list:
    """从 LLM 原始响应解析 3 条候选 JSON 数组。

    返回：list[dict]，长度 == 3；失败返回 [{"error": "..."}] 单元素 list。
    注：调用方负责长度对齐。
    """
    import json
    import re

    if not raw:
        return [{"error": "空响应"}]
    s = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    s = re.sub(r"\s*```$", "", s)
    m = re.search(r"\[.*\]", s, re.DOTALL)
    if m:
        s = m.group(0)
    try:
        rows = json.loads(s)
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return [{"error": "响应不是数组"}]
        for r in rows:
            r.setdefault("id", "")
            r.setdefault("strategy", "")
            r.setdefault("title", "")
            r.setdefault("body", "")
            r.setdefault("reason", "")
            r.setdefault("risk_flags", [])
            r.setdefault("used_input_fields", [])
        return rows
    except Exception as e:
        return [{"error": f"JSON失败: {str(e)[:80]}"}]


__all__ = ["VERSION", "SYSTEM_PROMPT", "build_user_prompt", "parse_response"]
