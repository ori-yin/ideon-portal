# -*- coding: utf-8 -*-
r"""
core/csv_utils.py — CSV/Excel 通用读取 + 列名别名标准化

Phase 17.5 抽：消除 services/feedback_service.py 与 services/batch_evaluation_service.py
两处重复的"pd.read_csv/Excel + 扩展名分发 + _COL_ALIASES 重命名"模板代码。
data_loader.load_sheet() 走 openpyxl 主表路径独立保留，不归本模块。

接口：
- read_table(file_bytes, filename="", col_aliases=None, required_cols=None) -> pd.DataFrame
"""

from __future__ import annotations

from io import BytesIO
from typing import Mapping, Optional, Sequence

import pandas as pd


# 链式 fallback：utf-8-sig 自动去 BOM（兼容 Notepad 导出）→ 常见 GBK 兼容中文
_CSV_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "gbk", "gb18030")


def _read_csv_with_encoding_fallback(file_bytes: bytes) -> pd.DataFrame:
    """链式尝试常见编码，直到一个能 decode 为止。"""
    last_err: Exception | None = None
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(BytesIO(file_bytes), encoding=enc)
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            continue
    raise ValueError(
        f"CSV 编码无法识别（已尝试 {', '.join(_CSV_ENCODINGS)}），请另存为 UTF-8 后再上传"
    ) from last_err


def read_table(
    file_bytes: bytes,
    filename: str = "",
    col_aliases: Optional[Mapping[str, Sequence[str]]] = None,
    required_cols: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """读 CSV/Excel → DataFrame，列名按 col_aliases 标准化，必填列缺失填空串。

    - 自动识别 .csv / .xlsx / .xls（其他扩展名先试 csv，失败 fallback excel）
    - 列名匹配：精确小写相等 → rename 到标准 target 名
    - required_cols 中缺失列填空串（保证下游访问 .title / .body / .channel 不报 KeyError）
    """
    name = (filename or "").lower()
    if name.endswith(".csv"):
        df = _read_csv_with_encoding_fallback(file_bytes)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(BytesIO(file_bytes))
    else:
        try:
            df = _read_csv_with_encoding_fallback(file_bytes)
        except Exception:
            df = pd.read_excel(BytesIO(file_bytes))

    if col_aliases:
        rename: dict = {}
        lower_cols = {str(c).strip().lower(): c for c in df.columns}
        for target, aliases in col_aliases.items():
            if target in df.columns:
                continue
            for a in aliases:
                a_low = str(a).strip().lower()
                if a_low in lower_cols:
                    rename[lower_cols[a_low]] = target
                    break
        if rename:
            df = df.rename(columns=rename)

    if required_cols:
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""
            else:
                df[col] = df[col].astype(str).fillna("").str.strip()

    return df


__all__ = ["read_table"]