# -*- coding: utf-8 -*-
r"""
core/data_window.py — 数据取数时间窗口工具 + 工作日类型分类

两套工具：
1. resolve_bi_dt_window() —— v3.1 取数时间基准
   依据 docs/ctr-kpi-definition-proposal-v0.2.md §3：
   - 回收真实 CTR 时，时间基准按 bi_dt T-1 快照
   - 当天 12 点前的查询 → 必须避开当天未生成的快照，用 INTERVAL 2 取前天
   - 当天 12 点后 → 可用 T-1（即昨天的快照）

2. classify_date_type() —— 工作日 / 非工作日 2 值分类（Phase 11 · 2026-08-27 用户简化拍板）
   口径（Handoff §6.2 #12）：
   - 周一~周五 → 工作日
   - 周六、周日 → 非工作日
   - 法定节假日、调休 暂不支持（待用户后续按需扩展，见 Handoff §6.2 第三梯队）

用法：
    from core.data_window import resolve_bi_dt_window, classify_today_type
    bi_dt = resolve_bi_dt_window()                       # 当前时间
    bi_dt = resolve_bi_dt_window(now=dt)                 # 指定时间（测试用）
    today_type = classify_today_type()                   # 今天的工作日类型
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, Union


# 注：Phase 17.6 删除 SNAPSHOT_CUTOFF_HOUR 常量（Phase 6 P3 应删未删；调用方都已硬编码 12 或不传）


def resolve_bi_dt_window(
    now: Optional[datetime] = None,
    cutoff_hour: int = 12,
) -> str:
    """计算取数用的 bi_dt（YYYY-MM-DD 字符串）。

    返回：
    - 当前时间 ≥ cutoff_hour → T-1（昨天）
    - 当前时间 < cutoff_hour → T-2（前天，INTERVAL 2）

    参数：
    - now: 给定当前时间；None 用 datetime.now()
    - cutoff_hour: 快照生成截止小时（默认 12 点）
    """
    if now is None:
        now = datetime.now()
    days_back = 1 if now.hour >= cutoff_hour else 2
    return (now - timedelta(days=days_back)).date().isoformat()


DateLike = Union[date, datetime, str]


def classify_date_type(target: DateLike) -> str:
    """按指定日期返回「工作日」或「非工作日」。

    口径：周一~周五 → "工作日"；周六、周日 → "非工作日"。
    不处理法定节假日和调休（Handoff §6.2 #12 用户简化拍板 2026-08-27）。

    参数：
    - target: date / datetime / "YYYY-MM-DD" 字符串

    异常：
    - ValueError: 字符串格式错误
    """
    if isinstance(target, str):
        d = datetime.strptime(target, "%Y-%m-%d").date()
    elif isinstance(target, datetime):
        d = target.date()
    else:
        d = target
    return "非工作日" if d.weekday() >= 5 else "工作日"


def classify_today_type() -> str:
    """按今天（系统本地日期）返回「工作日」或「非工作日」。"""
    return classify_date_type(date.today())


__all__ = [
    "resolve_bi_dt_window",
    "classify_date_type",
    "classify_today_type",
]