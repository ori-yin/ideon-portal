# -*- coding: utf-8 -*-
r"""
services/llm_config.py — Portal 的 LLM 配置（UI 在线改 / 测试 / 保存）

路径：~/.ideon-portal/llm_settings.yaml — 独立于 mcd-ai-content-platform 的 ~/.mcd-ai/llm_settings.yaml
理由（用户口径 2026-09-04）：「我需要迁移 LLM，但是别把 key 迁移过来」
- portal 用自己的 yaml 文件，避免无意中读出 8530 项目的 api_key
- 用户在 portal 里重新填一次（provider / base_url / model / api_key）

业务调用：tool_routes 通过 load_config() / is_configured() 决定走真 LLM 还是 Demo 占位
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml


# v2.2: portal 独立配置目录（与 mcd-ai-content-platform 的 ~/.mcd-ai 隔离）
CONFIG_PATH = Path.home() / ".ideon-portal" / "llm_settings.yaml"
REQUIRED_FIELDS = ("provider", "base_url", "model", "api_key")


@functools.lru_cache(maxsize=1)
def _load_yaml() -> dict:
    """加载并过滤到 REQUIRED_FIELDS（单进程内缓存，配置改后清缓存）。

    Windows 上 PyYAML 默认走 cp1252 解析会导致中文 mojibake，
    所以用 binary mode 读 + utf-8 decode 强制 UTF-8（utf-8-sig 兼容 BOM）。
    """
    if not CONFIG_PATH.exists():
        return {}
    try:
        with CONFIG_PATH.open("rb") as f:
            raw = f.read()
        text = raw.decode("utf-8-sig", errors="replace")
        data = yaml.safe_load(text) or {}
    except Exception:
        return {}
    return {k: str(data.get(k, "")).strip() for k in REQUIRED_FIELDS}


def reload_cache() -> None:
    """保存后清缓存，下一次 load_config() 读到新值。"""
    _load_yaml.cache_clear()


def load_config() -> dict:
    return dict(_load_yaml())


def missing_fields() -> list:
    cfg = _load_yaml()
    return [k for k in REQUIRED_FIELDS if not cfg.get(k, "")]


def is_configured() -> bool:
    return not missing_fields()


def get_status() -> dict:
    """给 template /api 用的简化状态。"""
    cfg = _load_yaml()
    configured = is_configured()
    return {
        "configured": configured,
        "provider": cfg.get("provider", ""),
        "model": cfg.get("model", ""),
        "base_url": cfg.get("base_url", ""),
        # api_key 不外露，只返回存在性
        "has_key": bool(cfg.get("api_key", "")),
    }


def save_config(cfg: dict) -> None:
    """写 4 字段到 portal 的 yaml（不走项目目录，避免 git 收集 key 历史）。

    Windows 下 write_text 默认会用 cp1252 二次编码中文，所以走 binary + utf-8。
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# Portal LLM 配置（页面右上角 pill 在线配置后保存）\n"
        "# 写到 ~/.ideon-portal/llm_settings.yaml，不进项目目录\n"
        "# 4 字段全部非空启用 LLM 模式，否则走 Demo 占位\n"
        f'provider: "{cfg["provider"]}"\n'
        f'base_url: "{cfg["base_url"]}"\n'
        f'model: "{cfg["model"]}"\n'
        f'api_key: "{cfg["api_key"]}"\n'
    )
    with CONFIG_PATH.open("wb") as f:
        f.write(body.encode("utf-8"))
    reload_cache()


def mask_api_key(api_key: str) -> str:
    """api_key 脱敏：前 4 + **** + 后 4。短于 8 字符全 ****。"""
    if not api_key:
        return ""
    if len(api_key) < 8:
        return "****"
    return api_key[:4] + "****" + api_key[-4:]


# 与 mcd-content-rank/config.py 的 API_PROVIDERS 对齐
# protocol: "openai" / "anthropic" — 决定调哪个 SDK
LLM_PROVIDERS = [
    {"name": "麦当劳AI网关", "base_url": "https://ai-gateway-test.mcdchina.net/v1",
     "protocol": "openai",
     "models": ["gemini-3-flash-preview", "gemini-3-pro-image-preview",
                "deepseek-v3", "claude-sonnet-4.6", "claude-haiku-4.5"]},
    {"name": "MiniMax",     "base_url": "https://api.minimaxi.com/anthropic",
     "protocol": "anthropic",
     "models": ["MiniMax-M3"]},
]


def probe_llm(provider: str, base_url: str, api_key: str, model: str, timeout: int = 30):
    """根据 provider protocol 选 SDK 试探连接。返回 (ok, error_msg)。

    protocol=anthropic (MiniMax) 走 anthropic SDK
    protocol=openai    走 openai SDK，base_url 空走 openai 默认
    """
    protocol = "openai"
    for p in LLM_PROVIDERS:
        if p["name"] == provider:
            protocol = p.get("protocol", "openai")
            break

    effective_url = (base_url or "https://api.openai.com/v1").rstrip("/")
    try:
        if protocol == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, base_url=base_url, timeout=timeout)
            client.messages.create(
                model=model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True, ""
        else:
            import openai
            if base_url:
                client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
            else:
                client = openai.OpenAI(api_key=api_key, timeout=timeout)
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=10,
            )
            return True, ""
    except Exception as e:
        status = getattr(e, "status_code", None)
        msg = (str(e)[:300] or type(e).__name__)
        detail = f"连接失败: {msg}"
        if status:
            detail += f" [HTTP {status}]"
        endpoint = "/v1/messages" if protocol == "anthropic" else "/chat/completions"
        detail += f"\n请求 URL: {effective_url}{endpoint}"
        if model:
            detail += f"\nModel: {model}"
        detail += f"\nProtocol: {protocol}"
        return False, detail