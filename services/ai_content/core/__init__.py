# -*- coding: utf-8 -*-
r"""
core/ — 基础层（CLAUDE.md §3）

- schemas:        dataclass 契约（PredictionResult / TaskInput / etc.）
- llm_gateway:    统一 LLM 调用（ProviderRouter，adapters/ 通过此模块调 LLM）

红线：
- 页面层 / services/ 不得直接 import openai/anthropic，必须走 llm_gateway
"""

from .schemas import PredictionResult, ResultType, VALID_RESULT_TYPES
from .llm_gateway import ProviderRouter, ANTHROPIC_PROVIDERS, OPENAI_PROVIDERS, ALL_PROVIDERS

__all__ = [
    "PredictionResult",
    "ResultType",
    "VALID_RESULT_TYPES",
    "ProviderRouter",
    "ANTHROPIC_PROVIDERS",
    "OPENAI_PROVIDERS",
    "ALL_PROVIDERS",
]