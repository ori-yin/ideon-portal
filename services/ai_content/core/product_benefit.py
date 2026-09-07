# -*- coding: utf-8 -*-
r"""
core/product_benefit.py — 产品类别 + 权益类型 枚举（Phase A.1 · 2026-08-28）

设计（Phase 9 决策）：
- 10 个产品类别（汉堡/小食/饮料/.../限定），覆盖麦当劳主推品类
- 8 个权益类型（折扣/满减/赠品/.../其他）
- 「自定义」输入兜底：UI selectbox 含 "自定义" 选项 + 文本框

不参与 CTR baseline 估算（Phase 9 拍板：直接 baseline 数据稀疏，ROI 低）。
仅影响：①AI 文案生成 prompt 注入 ②产品词典 jieba 词条扩展。

来源：config/product_benefit.yaml v1.0（业务经理维护，可不重启代码改值）。
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Tuple

# 默认路径
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "product_benefit.yaml"

# 兜底枚举（yaml 缺失/解析失败时用此值）
FALLBACK_PRODUCT_CATEGORIES: Tuple[str, ...] = (
    "汉堡", "小食", "饮料", "全餐", "早餐",
    "甜品", "咖啡", "麦满分", "儿童餐", "限定",
)
FALLBACK_BENEFIT_TYPES: Tuple[str, ...] = (
    "折扣", "满减", "赠品", "会员专享",
    "限时优惠", "新品首发", "活动促销", "其他",
)
CUSTOM_LABEL = "自定义"

# 兜底 dict（任一失败路径统一返回），避免 4 处 dict literal 重复
_FALLBACK_CFG: dict = {
    "product_categories": FALLBACK_PRODUCT_CATEGORIES,
    "benefit_types": FALLBACK_BENEFIT_TYPES,
    "custom_label": CUSTOM_LABEL,
}


@functools.lru_cache(maxsize=1)
def load_product_benefit(path: str = str(DEFAULT_PATH)) -> dict:
    """加载 yaml；失败返回兜底枚举（不让 UI 崩）。

    返回 dict：
      {
        "product_categories": tuple[str, ...],
        "benefit_types": tuple[str, ...],
        "custom_label": str,
      }
    """
    p = Path(path)
    if not p.exists():
        return _FALLBACK_CFG
    try:
        import yaml  # PyYAML 在 services/rule_engine 已有依赖
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return _FALLBACK_CFG
    return {
        "product_categories": tuple(data.get("product_categories") or FALLBACK_PRODUCT_CATEGORIES),
        "benefit_types": tuple(data.get("benefit_types") or FALLBACK_BENEFIT_TYPES),
        "custom_label": str(data.get("custom_label") or CUSTOM_LABEL),
    }


def get_product_categories() -> Tuple[str, ...]:
    return load_product_benefit()["product_categories"]


def get_benefit_types() -> Tuple[str, ...]:
    return load_product_benefit()["benefit_types"]


def get_custom_label() -> str:
    return load_product_benefit()["custom_label"]


def options_with_custom(values: Tuple[str, ...]) -> Tuple[str, ...]:
    """返回 selectbox 选项元组：「通用」首位 + 枚举 + 「自定义」末位（Phase 30）。"""
    return ("通用",) + tuple(values) + (CUSTOM_LABEL,)
