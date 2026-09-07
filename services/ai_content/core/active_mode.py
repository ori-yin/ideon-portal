# -*- coding: utf-8 -*-
"""core/active_mode.py — L1 漂移自动回退用的 active_mode.txt 读写。

用途：
- tools/monitor_l1_drift.py 检测到漂移时写文件，覆盖默认 CTR 模式
- pages/01 内容工坊.py 启动时读文件，决定 sidebar 默认值

文件位置：data/active_mode.txt
合法内容：'demo' | 'baseline_only' | 'l1_model'
文件不存在 / 内容非法 → 读不到，调用方 fallback 到 env CTR_MODE → demo
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
ACTIVE_MODE_PATH = ROOT / "data" / "active_mode.txt"

ALLOWED_MODES = frozenset({"demo", "baseline_only", "l1_model"})


def read_active_mode(path: Path = ACTIVE_MODE_PATH) -> Optional[str]:
    """读 active_mode.txt，返回合法 mode 或 None。"""
    if not path.exists():
        return None
    try:
        mode = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return mode if mode in ALLOWED_MODES else None


def write_active_mode(mode: str, path: Path = ACTIVE_MODE_PATH) -> None:
    """写 mode 到 active_mode.txt。"""
    if mode not in ALLOWED_MODES:
        raise ValueError(f"invalid mode: {mode!r}（需 ∈ {sorted(ALLOWED_MODES)}）")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mode, encoding="utf-8")


def clear_active_mode(path: Path = ACTIVE_MODE_PATH) -> bool:
    """删除文件（如果存在），返回是否真的删了。"""
    if path.exists():
        path.unlink()
        return True
    return False
