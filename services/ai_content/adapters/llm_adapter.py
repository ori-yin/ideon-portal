# -*- coding: utf-8 -*-
r"""
adapters/llm_adapter.py — 文案诊断 / 改写 LLM 适配层

抽自 C:\ideon\mcd-copy-analyzer\ai_service.py（Handoff §3.1 复用清单）。
改造点：
- 不直接 import openai SDK，由调用方注入 core.ProviderRouter（CLAUDE.md §4.1 红线）
- _parse_json 复用 core/llm_gateway.ProviderRouter.parse_json_response（统一 JSON 解析）
- build_user_prompt / fingerprint / SYSTEM_PROMPT 纯函数直接搬
- PROVIDERS 改为 base_url + models + default_model 元数据（不绑 SDK）

口径：
- 输入：title / body + analyzer.local_diagnose 返回的 dict
- 输出：dict(score=1-10, issues=[], rewrites=[{title, body}, ...]) 或 {"error": "..."}
"""

from __future__ import annotations

import json
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm_gateway import ProviderRouter


# ── Provider 元数据（按 PRD §15 架构：base_url + models，不绑 SDK） ────
PROVIDERS = {
    "MiniMax": {
        "base_url": "https://api.minimax.chat/v1",
        "models": ["MiniMax-M3", "abab6.5s-chat", "abab6.5-chat"],
        "default_model": "MiniMax-M3",
    },
    "openai": {
        "base_url": None,  # 用 SDK 默认
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
        "default_model": "gpt-4o-mini",
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct"],
        "default_model": "Qwen/Qwen2.5-7B-Instruct",
    },
    "qianfan": {
        "base_url": "https://qianfan.baidubce.com/v2/coding",
        "models": ["ernie-4.5-8k", "ernie-speed"],
        "default_model": "ernie-speed",
    },
}


SYSTEM_PROMPT = """你是麦当劳企微 1v1 文案顾问。给一线运营反馈。

输入会包含：
- 用户新写的 标题 / 正文
- 本地预计算：字数、emoji 数、历史「高效词」命中情况（这些词在历史 plan 中出现频率高且 CTR 高）

输出 JSON（不要 markdown 围栏，不要解释前缀）：
{
  "score": 1-10 整数分（10 = 文案精准抓人且能引导点击，1 = 跑题无信息量）,
  "issues": [ "问题 1", "问题 2" ],
  "rewrites": [
    {"title": "...", "body": "..."},
    {"title": "...", "body": "..."}
  ]
}

评分维度（必须基于历史高效词命中+文本结构综合判断）：
- 标题：≤15 字优先、含数字/emoji/紧迫词、明确利益点
- 正文：≤60 字阅读门槛、emoji 1-2 个不过度、有优惠/动作号召
- 历史高效词利用：题目命中历史高效词加分，缺关键利益点扣分
- 不要编造历史中没有的事实；改写保持产品真实。

只返回 JSON。"""


def build_user_prompt(title: str, body: str, local: dict) -> str:
    """拼装用户 prompt。local 是 analyzer.local_diagnose 返回的 dict。"""
    hit = "、".join(local.get("hit_words", [])) or "（无）"
    miss = "、".join(local.get("miss_top", [])[:8]) or "（无）"
    em = local.get("emoji_count", 0)
    return (
        f"【标题】{title or '（未填）'}\n"
        f"【正文】{body or '（未填）'}\n"
        f"【字数】标题 {len(title)} / 正文 {len(body)} 字；emoji {em} 个\n"
        f"【历史高效词命中】{hit}\n"
        f"【历史高频高 CTR 但本次未出现的词】{miss}"
    )


def fingerprint(title: str, body: str, provider: str, model: str, local: dict) -> tuple:
    """缓存指纹：所有可能影响 AI 输出的入参。"""
    return (
        title, body, provider, model,
        tuple(local.get("hit_words", [])),
        local.get("emoji_count"),
        len(title), len(body),
    )


def parse_json_response(raw: str) -> Optional[dict]:
    """鲁棒 JSON 解析（兼容 ai_service 旧 _parse_json 行为）：单条 dict。

    复用 core/llm_gateway 的 parse_json_response（数组）路径：先尝试解析单 dict，
    失败再用正则抓 dict。
    """
    if not raw:
        return None
    # 1) 剥 <think> 块（DeepSeek/MiniMax 等返回的隐藏思考）
    s = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    s = re.sub(r"^```(?:json)?\s*", "", s.strip())
    s = re.sub(r"\s*```$", "", s)
    # 抓首个 dict
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        s = m.group(0)
    # 鲁棒尝试
    for candidate in (s, s.replace("'", '"').replace(",}", "}").replace(",]", "]")):
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def call_llm(router: "ProviderRouter", title: str, body: str, local: dict,
             provider: Optional[str] = None, model: Optional[str] = None) -> dict:
    """调 LLM 返回 dict；失败返回 {"error": "..."}。

    router 由调用方注入（CLAUDE.md §4.1 红线：adapters 不直接 import SDK）。
    provider/model 参数覆盖 router 默认值（便于 UI 让用户临时切）。
    """
    if router is None or not getattr(router, "api_key", None):
        return {"error": "未配置 API Key"}

    provider_name = provider or router.provider
    if provider_name not in PROVIDERS:
        return {"error": f"未知 provider：{provider_name}"}
    cfg = PROVIDERS[provider_name]
    used_model = model or router.model or cfg["default_model"]
    if used_model not in cfg["models"]:
        used_model = cfg["default_model"]

    # 拼完整 prompt（system + user）
    full_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"{build_user_prompt(title, body, local)}"
    )

    raw = router.call(full_prompt, model=used_model)
    # router.call 失败时会返回 {"_error": "..."} 字符串，parse_json_response 能识别
    parsed = parse_json_response(raw)
    if not parsed:
        return {"error": "返回非 JSON，已显示原文", "raw": raw}
    if isinstance(parsed, dict) and "_error" in parsed:
        return {"error": str(parsed["_error"]), "raw": raw}
    parsed.setdefault("score", None)
    parsed.setdefault("issues", [])
    parsed.setdefault("rewrites", [])
    return parsed


__all__ = [
    "PROVIDERS",
    "SYSTEM_PROMPT",
    "build_user_prompt",
    "fingerprint",
    "parse_json_response",
    "call_llm",
]