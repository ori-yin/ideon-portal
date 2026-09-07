# -*- coding: utf-8 -*-
r"""
column_mapping.py — 列名自动识别（纯函数）

来源：C:\ideon\mcd-ctr-predictor\ctr_predictor.py 第 449-477 行（机械搬迁）。

8 组中文字段别名：标题 / 正文 / 渠道 / 是否用券 / 工作日类型 /
                  发送时间 / 计划类型 / 预算Owner

匹配规则：严格匹配列名（不区分大小写），避免 "title" 误匹配 "subtitle"。
"""

from __future__ import annotations
from typing import Iterable


# ── 别名常量 ────────────────────────────────────────────────────────────
KNOWN_TITLE_ALIASES = ["标题", "文案标题", "title", "标题列", "push_title", "标题title"]
KNOWN_BODY_ALIASES = ["内容", "正文", "文案", "content", "body", "push_content", "正文内容"]
KNOWN_CHANNEL_ALIASES = ["渠道", "channel", "触点", "push_channel"]
KNOWN_COUPON_ALIASES = ["是否用券", "用券", "coupon", "是否有券"]
KNOWN_WORKDAY_ALIASES = ["工作日类型", "工作日", "workday", "日期类型"]
KNOWN_TIME_ALIASES = ["发送时间", "时间", "time", "推送时间", "send_time"]
KNOWN_PLAN_ALIASES = ["计划类型", "plan_type", "计划type", "AARRPlan"]
KNOWN_OWNER_ALIASES = ["预算owner", "owner", "预算Owner", "负责人"]


def auto_detect(columns: Iterable[str], aliases: Iterable[str]) -> Optional[str]:
    """严格匹配列名（不区分大小写），返回首个命中的列名或 None。

    来源：ctr_predictor.py:458-465
    """
    for col in columns:
        for alias in aliases:
            if alias.lower() == str(col).lower():
                return col
    return None


def auto_detect_all(columns: Iterable[str]) -> dict:
    """批量识别 8 组字段。返回 {标准名: 列名} 映射，未识别为 None。

    来源：ctr_predictor.py:467-477
    兼容 pandas DataFrame.columns（直接传 columns 即可，不要传 DataFrame）
    """
    return {
        "标题": auto_detect(columns, KNOWN_TITLE_ALIASES),
        "正文": auto_detect(columns, KNOWN_BODY_ALIASES),
        "渠道": auto_detect(columns, KNOWN_CHANNEL_ALIASES),
        "是否用券": auto_detect(columns, KNOWN_COUPON_ALIASES),
        "工作日类型": auto_detect(columns, KNOWN_WORKDAY_ALIASES),
        "发送时间": auto_detect(columns, KNOWN_TIME_ALIASES),
        "计划类型": auto_detect(columns, KNOWN_PLAN_ALIASES),
        "预算Owner": auto_detect(columns, KNOWN_OWNER_ALIASES),
    }


# 注：Phase 17.6 删除 from_optional() 占位 helper（Phase 1a 起就抛 NotImplementedError，全项目无人调用）