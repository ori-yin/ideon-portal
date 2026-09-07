# -*- coding: utf-8 -*-
r"""
services/analytics/similarity.py — 相似 Plan 检索

PRD §4.2/§4.4：输入 1 条 Plan（或文案片段），从历史中找到 Top-K 相似 Plan。

实现：TF-IDF on _tokens + 余弦相似度。
- 复用 services/text_analyzer.add_tokens（保证词典一致）
- 复用 services/analytics/high_effort_plans.rank_plans 取元数据

性能：单条 query O(N)；N<10000 时纯 numpy 即够用，不引入 faiss。
"""

from __future__ import annotations

from collections import Counter
from math import sqrt
from typing import Optional

import pandas as pd

from services.text_analyzer import add_tokens, load_stopwords, load_single_char_whitelist, banned_words


def _tokenize_query(title: str, body: str, dict_path: Optional[str] = None,
                    stop_path: Optional[str] = None) -> list:
    """复用 text_analyzer.tokenize 切 query（保持词典一致）。"""
    stop = load_stopwords(stop_path)
    white = load_single_char_whitelist(dict_path)
    ban = set(banned_words(stop_path))
    from services.text_analyzer import tokenize
    txt = f"{title or ''} {body or ''}".strip()
    return tokenize(txt, stop, white, ban)


def _tfidf_vectors(docs: list) -> tuple:
    """手工 TF-IDF：返回 (vectors, vocab, idf)。
    docs: list[list[str]]，每条是一条 plan 的 tokens。
    """
    n = len(docs)
    df_counter = Counter()
    for tokens in docs:
        df_counter.update(set(tokens))
    vocab = {w: i for i, w in enumerate(sorted(df_counter))}
    # IDF
    import math
    idf = {w: math.log((n + 1) / (df + 1)) + 1 for w, df in df_counter.items()}
    # TF-IDF（用词频，不归一化，余弦相似度会归一）
    vectors = []
    for tokens in docs:
        tf = Counter(tokens)
        v = [0.0] * len(vocab)
        for w, c in tf.items():
            v[vocab[w]] = c * idf.get(w, 0.0)
        vectors.append(v)
    return vectors, vocab, idf


def _cosine(a: list, b: list) -> float:
    """余弦相似度（手写避免 sklearn 依赖；O(d) d=vocab 大小）。"""
    if not a or not b:
        return 0.0
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (na * nb)


def find_similar_plans(
    df: pd.DataFrame,
    title: str,
    body: str,
    top_k: int = 5,
    min_plans: int = 1,
    dict_path: Optional[str] = None,
    stop_path: Optional[str] = None,
) -> pd.DataFrame:
    """找 Top-K 相似历史 Plan。

    Parameters
    ----------
    df : 已 build() 清洗过的 DataFrame（含 Plan ID / 标题 / 正文 / 触达 / 点击）
    title, body : 待查询文案
    top_k : 返回前 K 条
    min_plans : 历史 plan 最少记录数（默认 1 不过滤）

    Returns
    -------
    DataFrame[plan_id, plan_name, channel, owner, similarity,
              n_records, 触达成功, 点击, 加权CTR%]
    """
    if df is None or df.empty:
        return pd.DataFrame()
    if "Plan ID" not in df.columns:
        return pd.DataFrame()

    # 1) 准备历史 tokens（按 Plan ID 聚合）
    if "_tokens" not in df.columns:
        df = add_tokens(df, dict_path=dict_path, stop_path=stop_path)
    # 按 plan 聚合 tokens
    plan_tokens = {}
    plan_meta = {}
    for pid, sub in df.groupby("Plan ID", dropna=False):
        toks = set()
        for s in sub["_tokens"]:
            toks |= set(s)
        if len(sub) < min_plans:
            continue
        plan_tokens[pid] = list(toks)
        plan_meta[pid] = {
            "plan_name": sub["Plan名称"].iloc[0] if "Plan名称" in sub.columns else "",
            "channel": sub["渠道"].iloc[0] if "渠道" in sub.columns else "",
            "owner": sub["owner"].iloc[0] if "owner" in sub.columns else "",
            "n_records": int(len(sub)),
            "触达成功": int(sub["触达成功"].sum()),
            "点击": int(sub["点击人次"].sum()),
        }

    if not plan_tokens:
        return pd.DataFrame()

    # 2) 切 query
    q_tokens = _tokenize_query(title, body, dict_path, stop_path)

    # 3) TF-IDF 化（query + 所有 plan docs）
    all_docs = [q_tokens] + [plan_tokens[pid] for pid in plan_tokens]
    vectors, vocab, _ = _tfidf_vectors(all_docs)
    q_vec = vectors[0]
    plan_vecs = vectors[1:]

    # 4) 余弦相似度
    rows = []
    pids = list(plan_tokens)
    for i, pid in enumerate(pids):
        sim = _cosine(q_vec, plan_vecs[i])
        if sim <= 0:
            continue
        m = plan_meta[pid]
        rows.append({
            "plan_id": pid,
            "plan_name": m["plan_name"],
            "channel": m["channel"],
            "owner": m["owner"],
            "similarity": round(sim, 4),
            "n_records": m["n_records"],
            "触达成功": m["触达成功"],
            "点击": m["点击"],
            "加权CTR%": round(m["点击"] / m["触达成功"] * 100, 2) if m["触达成功"] > 0 else 0.0,
        })

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows).sort_values("similarity", ascending=False).head(top_k).reset_index(drop=True)
    return out


__all__ = ["find_similar_plans"]