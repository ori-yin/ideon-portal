# -*- coding: utf-8 -*-
r"""
services/text_analyzer.py — 文案分析纯函数层

抽自 C:\ideon\mcd-copy-analyzer\analyzer.py（CLAUDE.md §5 复用清单）。
脱 Streamlit 改造：
- @st.cache_data → @functools.lru_cache（仿 adapters/ctr_predictor_adapter/baseline_lookup.py）
- dict_counts(staging_dict, staging_ban)：session_state 改参数注入，UI 层从 st.session_state 取出传入

红线：
- 业务层不依赖 st.session_state（本文件是纯函数；UI 注入 staging）
- CTR 一律 plan 加权：sum(点击) / sum(触达成功) * 100
- 词典路径：默认从本项目 data/ 读（旧项目路径不依赖）
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Optional

import jieba
import pandas as pd


# ── 路径默认（data/ 与本项目同级目录） ────────────────────────────────
_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DICT_PATH = _DEFAULT_DATA_DIR / "custom_dict.txt"
_STOP_PATH = _DEFAULT_DATA_DIR / "stopwords.txt"

# jieba 自定义词典频次：5000 足以让长词赢过默认词典（防切碎）；词性默认按名词处理，不显式存
_DEFAULT_FREQ = 5000

_CJK = re.compile(r"[一-鿿]")
_DIGIT = re.compile(r"^\d+(\.\d+)?$")
# 常见 emoji 区段（表情/符号/箭头/装饰），逐字符提取
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF"
    "\U00002B00-\U00002BFF\U00002190-\U000021FF\U0000231A-\U0000231B\U00002700-\U000027BF]",
    flags=re.UNICODE,
)

# jieba 单例：避免每次 init 重新读盘
_dict_loaded = False


# ── emoji 工具 ────────────────────────────────────────────────────────
def extract_emojis(text) -> list:
    """提取文本里的 emoji 字符列表。"""
    if not text:
        return []
    return _EMOJI.findall(str(text))


def count_emojis(text) -> int:
    """文本里 emoji 的数量。"""
    return len(extract_emojis(text))


def first_emoji_pos(text) -> int:
    """文本里第一个 emoji 出现的位置（0-based 字符下标）；无 emoji 返回 -1。"""
    s = str(text or "")
    for i, ch in enumerate(s):
        if _EMOJI.match(ch):
            return i
    return -1


# ── 词典/停用词读取（替 @st.cache_data → @functools.lru_cache） ────────
@functools.lru_cache(maxsize=1)
def load_stopwords(dict_path: Optional[str] = None) -> frozenset:
    """读取停用词。"""
    p = Path(dict_path) if dict_path else _STOP_PATH
    if not p.exists():
        return frozenset()
    out = set()
    with open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            out.add(ln)
    return frozenset(out)


@functools.lru_cache(maxsize=1)
def banned_words(dict_path: Optional[str] = None) -> tuple:
    """停用词里以「#禁词」起头的段；其他都是普通停用词。返回 tuple（frozenset 不能存 set）。"""
    p = Path(dict_path) if dict_path else _STOP_PATH
    if not p.exists():
        return ()
    out, in_ban = [], False
    with open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            s = ln.strip()
            if s.startswith("#"):
                in_ban = (s == "#禁词")
                continue
            if in_ban and s:
                out.append(s)
    return tuple(out)


@functools.lru_cache(maxsize=1)
def load_single_char_whitelist(dict_path: Optional[str] = None) -> frozenset:
    """custom_dict 里的单字词（如 券），分词后即便长度1也保留。"""
    p = Path(dict_path) if dict_path else _DICT_PATH
    if not p.exists():
        return frozenset()
    keep = set()
    with open(p, encoding="utf-8") as f:
        for ln in f:
            w = ln.strip().split(" ")[0] if ln.strip() else ""
            if len(w) == 1:
                keep.add(w)
    return frozenset(keep)


# ── 词典 staging 接口（替代旧 dict_counts 的 session_state trick） ─────
def dict_counts(staging_dict: Optional[list] = None, staging_ban: Optional[list] = None) -> Tuple[int, int]:
    """侧栏 caption 用：(自定义词典词数, 禁词数)。

    优先返回 UI 注入的 staging（实时看到 dialog 加词后的变化），
    否则读文件（带 lru_cache，避免 OneDrive 每次重读）。

    Usage (UI 层):
        n_d, n_b = dict_counts(
            staging_dict=st.session_state.get("_dict_staging"),
            staging_ban=st.session_state.get("_dict_ban_staging"),
        )
    """
    if staging_dict is not None and staging_ban is not None:
        return len(staging_dict), len(staging_ban)
    # 退化：读文件 + 缓存
    return _dict_counts_disk()


@functools.lru_cache(maxsize=1)
def _dict_counts_disk() -> Tuple[int, int]:
    return len(dict_words()), len(banned_words())


# ── jieba 初始化 / 词典读写 ────────────────────────────────────────────
def init_jieba(dict_path: Optional[str] = None) -> None:
    """加载自定义词典（幂等）。"""
    global _dict_loaded
    p = Path(dict_path) if dict_path else _DICT_PATH
    if not _dict_loaded and p.exists():
        jieba.load_userdict(str(p))
        _dict_loaded = True


def dict_words(dict_path: Optional[str] = None) -> list:
    """当前自定义词典的词列表。"""
    p = Path(dict_path) if dict_path else _DICT_PATH
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return [ln.strip().split(" ")[0] for ln in f if ln.strip()]


def dict_words_full(dict_path: Optional[str] = None) -> list:
    """返回 [(word, freq), ...] 用于编辑器展示与回写。词性字段已删除（jieba 默认按名词处理）。"""
    p = Path(dict_path) if dict_path else _DICT_PATH
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for ln in f:
            parts = ln.strip().split(" ")
            if not parts or not parts[0]:
                continue
            word = parts[0]
            freq = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else _DEFAULT_FREQ
            rows.append((word, freq))
    return rows


def save_custom_dict(rows: dict, dict_path: Optional[str] = None) -> None:
    """rows = [(word, freq), ...] 或 [word, ...]，去空去重后写回。freq 统一用 _DEFAULT_FREQ。"""
    p = Path(dict_path) if dict_path else _DICT_PATH
    seen, out = set(), []
    for r in rows:
        w = (r[0] if isinstance(r, (list, tuple)) else r).strip()
        if not w or w in seen:
            continue
        seen.add(w)
        out.append(w)
    with open(p, "w", encoding="utf-8") as f:
        for w in out:
            f.write(f"{w}\n")


def save_banned_words(words: dict, dict_path: Optional[str] = None) -> None:
    """整段重写禁词区。words 为词列表。
    - 文件原本没有 #禁词 段：自动创建段并写入（修复：之前直接 return 导致首次保存丢失）
    - 空列表 + 原无 #禁词 段：noop
    - 空列表 + 原有 #禁词 段：移除整段
    """
    p = Path(dict_path) if dict_path else _STOP_PATH
    txt = p.read_text(encoding="utf-8") if p.exists() else ""
    body, sep, _ = txt.partition("#禁词\n")
    head = body.rstrip() + "\n\n" if body.strip() else ""
    cleaned = [w.strip() for w in words if w and w.strip()]
    if not cleaned:
        # 空列表：原有段则移除，否则 noop
        if sep:
            with open(p, "w", encoding="utf-8") as f:
                f.write(head)
        return
    new_block = "#禁词\n" + "".join(f"{w}\n" for w in cleaned)
    with open(p, "w", encoding="utf-8") as f:
        f.write(head + new_block)


def dict_mtime(dict_path: Optional[str] = None, stop_path: Optional[str] = None) -> Tuple[float, float]:
    """两个词典文件的 mtime 元组（custom_dict.txt + stopwords.txt），
    禁词改 stopwords.txt 也必须让 tokenized 缓存失效。
    """
    dp = Path(dict_path) if dict_path else _DICT_PATH
    sp = Path(stop_path) if stop_path else _STOP_PATH
    d = dp.stat().st_mtime if dp.exists() else 0.0
    s = sp.stat().st_mtime if sp.exists() else 0.0
    return (d, s)


def reload_jieba() -> None:
    """词典变更后强制重载（清 lru_cache）。"""
    global _dict_loaded
    _dict_loaded = False
    init_jieba()
    # 词典文件改了，lru_cache 也得清
    load_stopwords.cache_clear()
    banned_words.cache_clear()
    load_single_char_whitelist.cache_clear()
    _dict_counts_disk.cache_clear()


# ── 切词 / 加列 ───────────────────────────────────────────────────────
def tokenize(text, stopwords: list, whitelist: list, banned: Optional[list] = None) -> list:
    """切词 + 过滤：去停用词/纯数字/纯符号 emoji；单字仅保留白名单；禁词彻底丢弃。"""
    if not text:
        return []
    init_jieba()
    banned = set(banned or [])
    stop = set(stopwords)
    white = set(whitelist)
    out = []
    for tok in jieba.lcut(str(text)):
        t = tok.strip()
        if not t or t in banned:
            continue
        if t in stop or _DIGIT.match(t):
            continue
        if not (_CJK.search(t) or t.isalnum()):
            continue
        if len(t) == 1 and t not in white:
            continue
        out.append(t)
    return out


def add_tokens(df: pd.DataFrame, cols=("标题", "正文"), dict_path: Optional[str] = None,
               stop_path: Optional[str] = None) -> pd.DataFrame:
    """给每行加 _tokens（frozenset）/ _emojis（frozenset）/ _len（标题+正文字数）。

    另加 `_tokens_joined` / `_emojis_joined`（"|token1|token2|" 形式），
    供 compare_token / compare_tokens 走 str.contains 向量化查词（避免行 apply，48k+ 行提速 50-100x）。
    注意 frozenset 迭代顺序不稳定，joined 列仅用于 contains 查询，不能作为稳定 key。
    """
    stop = load_stopwords(stop_path)
    white = load_single_char_whitelist(dict_path)
    banned = set(banned_words(stop_path))
    have = [c for c in cols if c in df.columns]

    def _row(r):
        txt = " ".join(str(r[c]) for c in have)
        tokens = tokenize(txt, stop, white, banned)
        emojis = extract_emojis(txt)
        return pd.Series({
            "_tokens": frozenset(tokens),
            "_tokens_joined": "|" + "|".join(tokens) + "|" if tokens else "",
            "_emojis": frozenset(emojis),
            "_emojis_joined": "|" + "|".join(emojis) + "|" if emojis else "",
            "_len": len(txt.replace(" ", "")),
        })

    df = df.copy()
    df[["_tokens", "_tokens_joined", "_emojis", "_emojis_joined", "_len"]] = df.apply(_row, axis=1)
    return df


# ── CTR 加权 / 词频 / 对比 ─────────────────────────────────────────────
def _weighted_ctr(sub: pd.DataFrame) -> float:
    """从子集 DataFrame 求 plan 加权 CTR；Phase 17 复用 core.analytics_utils。"""
    from core.analytics_utils import weighted_ctr
    reach = float(sub["触达成功"].sum())
    click = float(sub["点击人次"].sum())
    return weighted_ctr(click, reach)


def _freq(df: pd.DataFrame, col: str, label: str, plan_col: str = "Plan ID",
          min_plans: int = 1, sort_by: str = "触达成功") -> pd.DataFrame:
    """通用词频排行（col=_tokens 或 _emojis）。每词并列 含/不含 加权 CTR。"""
    if df is None or df.empty:
        return pd.DataFrame()
    if col not in df.columns:
        df = add_tokens(df)
    has_plan = plan_col in df.columns
    tot_reach = float(df["触达成功"].sum())
    tot_click = float(df["点击人次"].sum())
    agg = {}
    for _, r in df.iterrows():
        reach, click = r.get("触达成功", 0), r.get("点击人次", 0)
        pid = r.get(plan_col) if has_plan else None
        # 注：r[col] 是 frozenset，迭代安全
        for w in r[col]:
            a = agg.setdefault(w, {"freq": 0, "reach": 0, "click": 0, "plans": set()})
            a["freq"] += 1
            a["reach"] += reach
            a["click"] += click
            if pid is not None:
                a["plans"].add(pid)
    recs = []
    for w, a in agg.items():
        n_plans = len(a["plans"]) if has_plan else a["freq"]
        if n_plans < min_plans:
            continue
        in_ctr = round(a["click"] / a["reach"] * 100, 2) if a["reach"] > 0 else 0.0
        out_reach = tot_reach - a["reach"]
        out_click = tot_click - a["click"]
        out_ctr = round(out_click / out_reach * 100, 2) if out_reach > 0 else 0.0
        recs.append({label: w, "词频": a["freq"], "plan数": n_plans,
                     "含CTR%": in_ctr, "不含CTR%": out_ctr,
                     "差值": round(in_ctr - out_ctr, 2),
                     "触达成功": int(a["reach"]), "点击": int(a["click"])})
    out = pd.DataFrame(recs)
    if not out.empty and sort_by in out.columns:
        out = out.sort_values([sort_by, "词频"], ascending=False).reset_index(drop=True)
    return out


def word_frequency(df: pd.DataFrame, plan_col: str = "Plan ID", min_plans: int = 1,
                   sort_by: str = "触达成功") -> pd.DataFrame:
    """全词降序排行。返回 DataFrame[词, 词频, plan数, 触达成功, 点击, 含CTR%, 不含CTR%, 差值]。"""
    return _freq(df, "_tokens", "词", plan_col, min_plans, sort_by)


def emoji_frequency(df: pd.DataFrame, plan_col: str = "Plan ID", min_plans: int = 1,
                    sort_by: str = "触达成功") -> pd.DataFrame:
    """emoji 降序排行。返回 DataFrame[emoji, 词频, plan数, 触达成功, 点击, CTR%]。"""
    return _freq(df, "_emojis", "emoji", plan_col, min_plans, sort_by)


def compare_token(df: pd.DataFrame, token: str, col: str = "_tokens",
                  plan_col: str = "Plan ID") -> dict:
    """某词/emoji 含 vs 不含 的 plan 加权 CTR + 样本量。df=None 时返回空结果。

    Phase 51：向量化 — 优先用 `_tokens_joined` / `_emojis_joined` 列走 str.contains，
    比行级 df[col].apply(lambda s: token in s) 在 48k+ 行提速 50-100x。
    老列 _tokens / _emojis 仍保留（其它模块可能用），缺失 joined 列时自动降级回 apply。
    """
    if df is None or df.empty:
        return {"word": token, "含": {"n_records": 0, "n_plans": 0, "reach": 0, "click": 0, "ctr": 0.0},
                "不含": {"n_records": 0, "n_plans": 0, "reach": 0, "click": 0, "ctr": 0.0}}
    if col not in df.columns:
        df = add_tokens(df)
    joined_col = "_tokens_joined" if col == "_tokens" else (
        "_emojis_joined" if col == "_emojis" else None
    )
    if joined_col and joined_col in df.columns:
        # 向量化：f"|{token}|" 走 str.contains regex=False，| 分隔防部分匹配（"免费" 不会撞 "免费送"）
        needle = f"|{token}|"
        mask = df[joined_col].str.contains(needle, regex=False, na=False)
    else:
        # 老路径：行 apply（frozenset O(1) 查）
        mask = df[col].apply(lambda s: token in s)
    has_plan = plan_col in df.columns

    def _block(sub):
        return {
            "n_records": int(len(sub)),
            "n_plans": int(sub[plan_col].nunique()) if has_plan else int(len(sub)),
            "reach": int(sub["触达成功"].sum()),
            "click": int(sub["点击人次"].sum()),
            "ctr": _weighted_ctr(sub),
        }

    return {"word": token, "含": _block(df[mask]), "不含": _block(df[~mask])}


def compare_tokens(df: pd.DataFrame, tokens: list, col: str = "_tokens",
                   plan_col: str = "Plan ID") -> Optional[dict]:
    """多词 AND 查询：含=全部命中，不含=至少少一个。
    tokens: list[str]，如 ["免费", "麦旋风"]
    df=None 时返回 None。
    """
    if df is None or df.empty:
        return None
    if col not in df.columns:
        df = add_tokens(df)
    tokens = [t.strip() for t in tokens if t and t.strip()]
    if not tokens:
        return None
    mask = df[col].apply(lambda s: all(t in s for t in tokens))
    has_plan = plan_col in df.columns

    def _block(sub):
        return {
            "n_records": int(len(sub)),
            "n_plans": int(sub[plan_col].nunique()) if has_plan else int(len(sub)),
            "reach": int(sub["触达成功"].sum()),
            "click": int(sub["点击人次"].sum()),
            "ctr": _weighted_ctr(sub),
        }

    return {"words": tokens, "含": _block(df[mask]), "不含": _block(df[~mask])}


# ── 本地诊断 / 评分 / 问题 / 建议 ─────────────────────────────────────
def local_diagnose(title: str, body: str, df: Optional[pd.DataFrame] = None,
                   min_plans: int = 3, top_n: int = 8,
                   dict_path: Optional[str] = None,
                   stop_path: Optional[str] = None) -> dict:
    """本地诊断：切文案 + 与历史高频高 CTR 词交叉。0 token。
    返回 dict：title/body/len_*/emoji_count/hit_words/miss_top。
    """
    stop = load_stopwords(stop_path)
    white = load_single_char_whitelist(dict_path)
    banned = set(banned_words(stop_path))
    txt = f"{title or ''} {body or ''}".strip()
    toks = tokenize(txt, stop, white, banned)
    emojis = extract_emojis(txt)
    cur_set = set(toks) | set(emojis)

    if df is None or df.empty:
        # 无数据时返回基础诊断，hit/miss 为空
        return {
            "title": title or "",
            "body": body or "",
            "len_title": len(title or ""),
            "len_body": len(body or ""),
            "emoji_count": len(emojis),
            "tokens": toks,
            "hit_words": [],
            "miss_top": [],
        }

    wf = word_frequency(df, min_plans=min_plans)
    eff = wf[wf["差值"] > 0].copy() if "差值" in wf.columns else wf.head(0)

    if eff.empty:
        hit, miss_top = [], []
    else:
        eff_words = eff[eff.columns[0]].tolist()
        hit = [w for w in eff_words if w in cur_set]
        miss = [w for w in eff_words if w not in cur_set]
        miss_top = miss[:top_n]

    return {
        "title": title or "",
        "body": body or "",
        "len_title": len(title or ""),
        "len_body": len(body or ""),
        "emoji_count": len(emojis),
        "tokens": toks,
        "hit_words": hit,
        "miss_top": miss_top,
    }


def load_frameworks(path: Optional[str] = None) -> dict:
    """读 data/frameworks.json（高 CTR 文案骨架常量）。"""
    p = Path(path) if path else (_DEFAULT_DATA_DIR / "frameworks.json")
    if not p.exists():
        return {"frameworks": [], "channel_baselines": {}, "source": ""}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _has_any(text: str, kws: list) -> bool:
    return any(kw in text for kw in kws)


def match_frameworks(title: str, body: str, channel: str, frameworks: list,
                     top_n: int = 3) -> list:
    """按渠道匹配框架，返回 [(matched_framework, violations), ...]。

    violations: 违反的规则列表（字符串），便于 UI 标红。
    每个框架的 keywords 按"标签组"分组；命中至少 2 个标签组即视为匹配。
    """
    text = f"{title or ''} {body or ''}".strip()
    out = []
    for fw in frameworks:
        if fw.get("channel") != channel:
            continue
        rules = fw.get("rules") or {}
        kws = fw.get("keywords") or {}

        # 规则违反检查（即使匹配也要展示违规）
        violations = []
        if rules.get("forbid_digit") and re.search(r"\d", title or ""):
            violations.append("标题含数字（该框架禁忌）")
        if rules.get("require_emoji") and not extract_emojis(title or ""):
            violations.append("标题缺 emoji（该框架必带）")
        if rules.get("require_digit") and not re.search(r"\d", text):
            violations.append("文案缺数字（该框架必带）")
        max_len = rules.get("title_len_max")
        if max_len and len(title or "") > max_len:
            violations.append(f"标题超过 {max_len} 字")

        # 标签组命中（关键词字典的每个 key 是一个"标签组"）
        hit_groups = sum(1 for _, lst in kws.items() if _has_any(text, lst))
        if hit_groups < 2:
            continue

        out.append((fw, violations))
        if len(out) >= top_n:
            break
    return out


# ── 评分 / 问题 / 建议 ────────────────────────────────────────────────
def _score_title_len(n: int) -> int:
    """标题字数合理性（满分 12）：8-15 字最优。"""
    if n == 0: return 0
    if 8 <= n <= 15: return 12
    if 6 <= n <= 17: return 8
    if 4 <= n <= 20: return 4
    return 0


def _score_body_len(n: int) -> int:
    """正文字数合理性（满分 13）：20-50 字最优。"""
    if n == 0: return 0
    if 20 <= n <= 50: return 13
    if 10 <= n <= 80: return 8
    if 5 <= n <= 120: return 4
    return 0


def _score_emoji(n: int) -> int:
    """emoji 数量（满分 15）：1-2 个最优。"""
    if 1 <= n <= 2: return 15
    if n == 3: return 8
    if n >= 4: return 4
    return 0  # 0 个


def _score_hit(n_hit: int) -> int:
    """命中高效词（满分 30）：线性 1-3 词封顶。"""
    return min(n_hit * 12, 30)


def diagnose_score(title: str, body: str, df: Optional[pd.DataFrame] = None,
                   target_ch: Optional[str] = None,
                   fw_data: Optional[dict] = None,
                   min_plans: int = 3) -> dict:
    """综合评分 0-100 + 评级 + 4 项分项 + 预测 CTR 判断。

    返回 {"score": int, "grade": "优秀/良好/需优化/重写",
          "breakdown": {"标题字数": pts, "正文字数": pts, "Emoji": pts,
                        "命中高效词": pts, "框架命中": pts or None},
          "baseline_ctr": float|None, "predicted_ctr": float|None,
          "ctr_delta_pct": float|None}.
    """
    diag = local_diagnose(title, body, df, min_plans=min_plans)
    bd = {
        "标题字数": _score_title_len(diag["len_title"]),
        "正文字数": _score_body_len(diag["len_body"]),
        "Emoji": _score_emoji(diag["emoji_count"]),
        "命中高效词": _score_hit(len(diag["hit_words"])),
        "框架命中": None,
    }
    if target_ch and fw_data:
        matches = match_frameworks(title, body, target_ch, fw_data.get("frameworks", []))
        bd["框架命中"] = 30 if matches else 0

    # P3：维度权重（从 config/dimension_weights.yaml 读，缺维度默认 1.0）
    weights = load_dimension_weights().get("dimensions", {})
    score = sum((v or 0) * weights.get(k, 1.0) for k, v in bd.items())
    if score >= 85:
        grade = "优秀"
    elif score >= 70:
        grade = "良好"
    elif score >= 50:
        grade = "需优化"
    else:
        grade = "重写"

    # 预测 CTR：以渠道均值为基线，评分 70 分对应基线（clamp 0.5x~1.5x）
    baseline_ctr = None
    predicted_ctr = None
    ctr_delta_pct = None
    if df is not None and not df.empty and "点击人次" in df.columns and "触达成功" in df.columns:
        total_click = float(df["点击人次"].sum())
        total_reach = float(df["触达成功"].sum())
        if total_reach > 0:
            baseline_ctr = total_click / total_reach * 100
            raw = baseline_ctr * (score / 70)
            predicted_ctr = max(0.5 * baseline_ctr, min(1.5 * baseline_ctr, raw))
            ctr_delta_pct = (predicted_ctr - baseline_ctr) / baseline_ctr * 100

    return {
        "score": score, "grade": grade, "breakdown": bd, "diag": diag,
        "baseline_ctr": baseline_ctr, "predicted_ctr": predicted_ctr,
        "ctr_delta_pct": ctr_delta_pct,
    }


def diagnose_problems(title: str, body: str, diag: dict,
                      target_ch: Optional[str] = None,
                      fw_data: Optional[dict] = None) -> list:
    """问题清单：每条 {tag: "缺失/异常", label, current, suggested, so_what}。
    tag 用于前端样式（缺失=bad 红，异常=warn 黄）。
    """
    out = []
    if diag["len_title"] == 0:
        out.append({"tag": "缺失", "label": "标题",
                    "current": "空", "suggested": "填 8-15 字",
                    "so_what": "标题是用户第一眼看到的——空标题无法吸引点击"})
    elif diag["len_title"] < 8:
        out.append({"tag": "异常", "label": "标题过短",
                    "current": f"{diag['len_title']} 字",
                    "suggested": "8-15 字",
                    "so_what": "标题太短无法完整传达利益点，点击率下降"})
    elif diag["len_title"] > 15:
        out.append({"tag": "异常", "label": "标题过长",
                    "current": f"{diag['len_title']} 字",
                    "suggested": "8-15 字",
                    "so_what": "标题超过 15 字在企微列表里会被截断"})

    if diag["len_body"] == 0:
        out.append({"tag": "缺失", "label": "正文",
                    "current": "空", "suggested": "填 20-50 字",
                    "so_what": "正文承接标题——空正文让用户没有下一步动作"})
    elif diag["len_body"] < 20:
        out.append({"tag": "异常", "label": "正文过短",
                    "current": f"{diag['len_body']} 字",
                    "suggested": "20-50 字",
                    "so_what": "正文太短无法补充利益点或紧迫感"})
    elif diag["len_body"] > 80:
        out.append({"tag": "异常", "label": "正文过长",
                    "current": f"{diag['len_body']} 字",
                    "suggested": "20-50 字",
                    "so_what": "正文过长用户读不完就被划走"})

    if diag["emoji_count"] == 0:
        out.append({"tag": "缺失", "label": "Emoji",
                    "current": "0 个", "suggested": "1-2 个",
                    "so_what": "emoji 在企微列表里提升视觉吸引力"})
    elif diag["emoji_count"] >= 4:
        out.append({"tag": "异常", "label": "Emoji 过多",
                    "current": f"{diag['emoji_count']} 个",
                    "suggested": "1-2 个",
                    "so_what": "emoji 过多显得杂乱，反而降低点击"})

    if not diag["hit_words"]:
        out.append({"tag": "缺失", "label": "高效词",
                    "current": "0 个命中",
                    "suggested": f"加入 {len(diag['miss_top'])} 个候选词",
                    "so_what": "历史高 CTR 文案常用词 = 提升点击的语言抓手"})

    if target_ch and fw_data:
        matches = match_frameworks(title, body, target_ch, fw_data.get("frameworks", []))
        if not matches:
            out.append({"tag": "缺失", "label": "高 CTR 框架",
                        "current": f"未命中（{target_ch}）",
                        "suggested": "看下方 P1 建议",
                        "so_what": f"{target_ch} 有专属骨架模板——未命中通常掉 30%+ CTR"})
    return out


def diagnose_suggestions(diag: dict, problems: list) -> Tuple[list, list]:
    """P1/P2 优先级建议：每条 {pri: "P1"/"P2", title, action, items}。"""
    p1, p2 = [], []

    # P1: 影响最大
    if not diag["hit_words"] and diag["miss_top"]:
        p1.append({
            "pri": "P1", "title": "加入高效词",
            "action": "在标题或正文加入这些词（按历史差值降序）：",
            "items": diag["miss_top"][:5],
        })

    framework_problem = next((p for p in problems if p["label"] == "高 CTR 框架"), None)
    if framework_problem:
        p1.append({
            "pri": "P1", "title": "对齐高 CTR 框架",
            "action": "按渠道骨架模板重写（招呼+专属+利益 / 数字+产品+套餐等）：",
            "items": ["查看下方「文案框架速查」section"],
        })

    body_short = next((p for p in problems if p["label"] == "正文过短"), None)
    if body_short:
        p1.append({
            "pri": "P1", "title": "补充正文",
            "action": "用利益点 + 紧迫感填到 20-50 字：",
            "items": ["限时", "专享", "立即领取", "错过等下次"],
        })

    # P2: 锦上添花
    if diag["emoji_count"] == 0:
        p2.append({
            "pri": "P2", "title": "添加 Emoji",
            "action": "1-2 个 emoji 提升视觉吸引力：",
            "items": ["🍔", "🎁", "⭐", "coupon"],
        })
    title_short = next((p for p in problems if p["label"] == "标题过短"), None)
    if title_short:
        p2.append({
            "pri": "P2", "title": "丰满标题",
            "action": "把利益点加到标题里（8-15 字）：",
            "items": ["限时", "免费", "专享", "立减"],
        })
    return p1, p2


# ── P3 维度权重（来自 config/dimension_weights.yaml） ─────────────
@functools.lru_cache(maxsize=1)
def load_dimension_weights() -> dict:
    """读 config/dimension_weights.yaml；缺失/异常 → 兜底（等权 1.0）。

    返回 {"dimensions": {dim: w, ...}, "baseline_modifiers": {dim: w, ...}, ...}
    测试 monkey-patch 后需调 load_dimension_weights.cache_clear()（Handoff §7）。
    """
    p = Path(__file__).resolve().parent.parent / "config" / "dimension_weights.yaml"
    if not p.exists():
        return {"dimensions": {}, "baseline_modifiers": {}}
    try:
        import yaml  # PyYAML 已在 services/rule_engine.py:54 使用（Handoff §7）
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        # 兜底段缺失时补空 dict，避免 diagnose_score KeyError
        doc.setdefault("dimensions", {})
        doc.setdefault("baseline_modifiers", {})
        return doc
    except Exception:
        return {"dimensions": {}, "baseline_modifiers": {}}


__all__ = [
    # emoji 工具
    "extract_emojis", "count_emojis", "first_emoji_pos",
    # 词典 / 停用词
    "load_stopwords", "banned_words", "load_single_char_whitelist",
    "dict_counts", "init_jieba", "dict_words", "dict_words_full",
    "save_custom_dict", "save_banned_words", "dict_mtime", "reload_jieba",
    # 切词 / 加列
    "tokenize", "add_tokens", "_weighted_ctr",
    # 词频 / 对比
    "word_frequency", "emoji_frequency", "compare_token", "compare_tokens",
    # 诊断 / 评分 / 问题 / 建议
    "local_diagnose", "load_frameworks", "match_frameworks", "load_dimension_weights",
    "diagnose_score", "diagnose_problems", "diagnose_suggestions",
]