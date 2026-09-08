# -*- coding: utf-8 -*-
r"""
services/llm_config.py — Portal 的 LLM 配置（UI 在线改 / 测试 / 保存）

v3.5 LLM 全局生效（方案 B）：canonical 路径 ~/.ideon/llm_settings.yaml
- 写：portal 写 ~/.ideon/（单点权威，所有子项目读这一份）
- 读：先 ~/.ideon/，回退 ~/.ideon-portal/（v3.4 之前 portal 自己的位置，零数据丢失）
- 启动时如果 ~/.ideon/ 不存在但 ~/.ideon-portal/ 存在，自动 copy（用户不用重配）
- 旧 ~/.ideon-portal/llm_settings.yaml 保留不动，作为历史 fallback 兜底

业务调用：tool_routes 通过 load_config() / is_configured() 决定走真 LLM 还是 Demo 占位
"""

from __future__ import annotations

import functools
import shutil
from pathlib import Path

import yaml


# v3.5 canonical 路径（portal + mcd-ai 共享）
CONFIG_PATH = Path.home() / ".ideon" / "llm_settings.yaml"
# v3.4 之前 portal 自己的路径（v3.5 起回退 fallback）
LEGACY_PATH = Path.home() / ".ideon-portal" / "llm_settings.yaml"
REQUIRED_FIELDS = ("provider", "base_url", "model", "api_key")


def _migrate_legacy_if_needed() -> None:
    """首次启动：~/.ideon/ 不存在 + ~/.ideon-portal/ 存在 → 自动 copy。
    用户不用重配；后续 mcd-ai 等子项目也能读到。
    """
    if CONFIG_PATH.exists():
        return
    if not LEGACY_PATH.exists():
        return
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEGACY_PATH, CONFIG_PATH)
    except Exception:
        # 迁移失败不阻塞（fallback 读 LEGACY_PATH 仍能工作）
        pass


@functools.lru_cache(maxsize=1)
def _load_yaml() -> dict:
    """加载并过滤到 REQUIRED_FIELDS（单进程内缓存，配置改后清缓存）。

    优先 canonical ~/.ideon/，回退 LEGACY_PATH ~/.ideon-portal/（仅在 canonical 不存在时）。
    canonical 存在但解析失败时 raise，避免用户配置更新被旧 LEGACY_PATH 静默覆盖。
    Windows 上 PyYAML 默认走 cp1252 解析会导致中文 mojibake，
    所以用 binary mode 读 + utf-8 decode 强制 UTF-8（utf-8-sig 兼容 BOM）。
    """
    _migrate_legacy_if_needed()

    def _read_one(path: Path) -> dict:
        with path.open("rb") as f:
            raw = f.read()
        text = raw.decode("utf-8-sig", errors="replace")
        data = yaml.safe_load(text) or {}
        return {k: str(data.get(k, "")).strip() for k in REQUIRED_FIELDS}

    # canonical 存在 → 必读它，解析失败 raise（不让用户的更新悄悄丢）
    if CONFIG_PATH.exists():
        try:
            return _read_one(CONFIG_PATH)
        except yaml.YAMLError as e:
            raise RuntimeError(f"解析 {CONFIG_PATH} 失败（YAML 格式错），避免回退到旧 LEGACY_PATH 静默丢数据: {e}") from e
        except Exception as e:
            raise RuntimeError(f"读取 {CONFIG_PATH} 失败: {e}") from e

    # canonical 不存在时，LEGACY_PATH 才作为兜底（v3.4 → v3.5 迁移过渡期）
    if LEGACY_PATH.exists():
        try:
            return _read_one(LEGACY_PATH)
        except Exception:
            return {}
    return {}


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