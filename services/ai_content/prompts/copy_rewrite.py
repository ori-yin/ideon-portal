# -*- coding: utf-8 -*-
r"""
prompts/copy_rewrite.py — 改写候选文案的 Prompt 模板

PRD §7.5 候选操作 P1：
- 仅重新生成此版本
- 缩短 / 更直接 / 更有场景感 / 强化行动号召 / 根据风险提示改写 / 根据历史高表现表达改写

按 action 类型映射 system prompt 策略。
"""

from __future__ import annotations


VERSION = "v1.0"


_STRATEGY = {
    "shorten": (
        "缩短：把标题控制在 12 字内、正文控制在 40 字内，去掉冗余修饰。"
        "保留核心利益点和动作号召。不得因缩短丢失关键信息。"
    ),
    "direct": (
        "更直接：去掉铺垫和场景描述，第一句话直接说产品/权益/优惠。"
        "适合追求点击率的场景。不得虚构紧迫性。"
    ),
    "scene": (
        "更有场景感：用具体的消费场景开头（早餐/午餐/下午茶/晚餐/夜宵/周末），"
        "让用户一眼看到「这就是在说我」。语气自然、不夸张。"
    ),
    "cta": (
        "强化行动号召：在结尾加明确的动作词（立即查看 / 马上领取 / 点击了解）。"
        "不得编造「仅剩XX份」「马上截止」等虚构紧迫信息。"
    ),
    "safer": (
        "根据风险提示改写：消除原文的过度承诺、法规风险词、虚假紧迫。"
        "用更安全的中性表达替换。"
    ),
    "regen": (
        "重新生成：基于同样的任务输入，生成一条与原文表达明显不同的候选。"
        "可以保留原 strategy 也可以换，但不得与原文意思完全一致。"
    ),
}


SYSTEM_PROMPT_TEMPLATE = """你是麦当劳文案顾问。改写一条候选文案。

策略：{strategy}

输入会包含原标题 / 正文 / 经营任务上下文。

输出 JSON（不要 markdown 围栏）：
{{"title": "...", "body": "...", "reason": "为什么这样改"}}

硬约束：
- 输出只包含 title / body / reason 三个字段
- 不得编造未输入的产品、价格、日期、库存
- 严格遵守渠道字数上限（见上下文）
"""


def build_user_prompt(
    action: str,
    title: str,
    body: str,
    channel_max: dict,
    extra_context: str = "",
) -> str:
    """拼装改写 user prompt。action ∈ {shorten, direct, scene, cta, safer, regen}。"""
    strategy = _STRATEGY.get(action, _STRATEGY["regen"])
    parts = [
        "【原文】",
        f"标题：{title}",
        f"正文：{body}",
        "",
        "【渠道字数约束】",
        f"标题上限：{channel_max.get('title_max', 15)} 字",
        f"正文字数上限：{channel_max.get('body_max', 60)} 字",
        f"emoji 上限：{channel_max.get('emoji_max', 2)} 个",
    ]
    if extra_context:
        parts.append("")
        parts.append("【额外上下文】")
        parts.append(extra_context)
    parts.append("")
    parts.append(f"【改写策略】{strategy}")
    return "\n".join(parts)


def get_system_prompt(action: str) -> str:
    """按 action 类型返回对应 system prompt。"""
    strategy = _STRATEGY.get(action, _STRATEGY["regen"])
    return SYSTEM_PROMPT_TEMPLATE.format(strategy=strategy)


def parse_response(raw: str) -> dict:
    """解析单条改写结果 dict。失败返回 {"error": "..."}。

    失败信息走 unsafe_allow_html（pages/02:435），str(e) 经 _sanitize_error
    兜底屏蔽 sk-/Bearer 模式（防御性；Phase 23 与 llm_gateway 同源）。
    """
    import json
    import re

    from core.llm_gateway import _sanitize_error  # 复用 sanitizer，避免散落

    if not raw:
        return {"error": "空响应"}
    s = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    s = re.sub(r"\s*```$", "", s)
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        s = m.group(0)
    try:
        d = json.loads(s)
        if not isinstance(d, dict):
            return {"error": "响应不是 dict"}
        d.setdefault("title", "")
        d.setdefault("body", "")
        d.setdefault("reason", "")
        return d
    except Exception as e:
        return {"error": f"JSON失败: {_sanitize_error(str(e))[:80]}"}


__all__ = ["VERSION", "get_system_prompt", "build_user_prompt", "parse_response"]
