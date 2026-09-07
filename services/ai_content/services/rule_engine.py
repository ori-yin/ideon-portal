# -*- coding: utf-8 -*-
r"""
services/rule_engine.py — 硬规则检查引擎

PRD §3.4 硬规则由程序判断（不依赖 LLM）：
- 渠道字数
- 必填字段
- 禁用词或风险词
- 未经输入的数字 / 日期 / 优惠 / 库存信息（首版用保守检查：含数字/日期提示 warn）
- 重复文案
- 格式错误
- 是否存在阻断项

PRD §8.4 / §11 规则三态：
- pass（绿）：通过
- warn（黄）：提醒
- fail（红）：阻断（命中即不推荐正式使用，PRD §8.5）

输出 RuleResult（core/schemas.py）：
- items: list[RuleItem(category, severity, message, suggestion)]
- status: pass/warn/fail（聚合）
- has_blocking: bool（has fail）

配置化（PRD §11.4）：
- 渠道规则：config/channel_rules.yaml
- 品牌规则：config/brand_rules.yaml
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

import yaml

from core.schemas import (
    Candidate, RuleItem, RuleResult,
    SEVERITY_PASS, SEVERITY_WARN, SEVERITY_FAIL,
)


CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_rules(
    channel_path: Optional[str] = None,
    brand_path: Optional[str] = None,
) -> Tuple[dict, dict]:
    """加载渠道 + 品牌规则 YAML。"""
    cp = channel_path or str(CONFIG_DIR / "channel_rules.yaml")
    bp = brand_path or str(CONFIG_DIR / "brand_rules.yaml")
    with open(cp, "r", encoding="utf-8") as f:
        channel_cfg = yaml.safe_load(f) or {}
    with open(bp, "r", encoding="utf-8") as f:
        brand_cfg = yaml.safe_load(f) or {}
    return channel_cfg, brand_cfg


# ── 字数检查 ──────────────────────────────────────────────────────────
def _check_length(title: str, body: str, channel_rules: dict) -> list:
    """检查字数是否超限。channel_rules 是单渠道 dict（已经按 channel 拆过）。"""
    items = []
    cr = channel_rules

    # 标题长度
    title_max = cr.get("title_max")
    if title_max and title_max > 0:
        tl = len(title)
        if tl > title_max:
            items.append(RuleItem(
                category="字数",
                severity=SEVERITY_FAIL,
                message=f"标题 {tl} 字，超过上限 {title_max}",
                suggestion=f"请删减至 {title_max} 字以内",
            ))
        elif tl == 0:
            # 渠道要求标题但为空
            if cr.get("require_title"):
                items.append(RuleItem(
                    category="字数",
                    severity=SEVERITY_FAIL,
                    message=f"该渠道要求标题，但当前为空",
                    suggestion="请补充标题",
                ))
        else:
            items.append(RuleItem(
                category="字数",
                severity=SEVERITY_PASS,
                message=f"标题 {tl} 字（在上限 {title_max} 内）",
            ))
    else:
        # 渠道不要求独立标题；空标题不扣分
        if title:
            items.append(RuleItem(
                category="字数",
                severity=SEVERITY_WARN,
                message="该渠道不要求独立标题，当前却有标题",
                suggestion="可考虑去掉标题只用正文",
            ))
        else:
            items.append(RuleItem(
                category="字数",
                severity=SEVERITY_PASS,
                message="该渠道不需要标题，符合",
            ))

    # 正文长度
    body_max = cr.get("body_max")
    bl = len(body)
    if body_max and bl > body_max:
        items.append(RuleItem(
            category="字数",
            severity=SEVERITY_FAIL,
            message=f"正文 {bl} 字，超过上限 {body_max}",
            suggestion=f"请删减至 {body_max} 字以内",
        ))
    else:
        items.append(RuleItem(
            category="字数",
            severity=SEVERITY_PASS,
            message=f"正文 {bl} 字（在上限 {body_max} 内）",
        ))

    # emoji 数
    emoji_max = cr.get("emoji_max")
    if emoji_max is not None:
        emoji_count = sum(1 for c in body if _is_emoji(c)) + sum(1 for c in title if _is_emoji(c))
        if emoji_count > emoji_max:
            items.append(RuleItem(
                category="字数",
                severity=SEVERITY_WARN,
                message=f"emoji {emoji_count} 个，超过渠道上限 {emoji_max}",
                suggestion=f"请减至 {emoji_max} 个以内",
            ))
        else:
            items.append(RuleItem(
                category="字数",
                severity=SEVERITY_PASS,
                message=f"emoji {emoji_count} 个（上限 {emoji_max}）",
            ))
    return items


def _is_emoji(ch: str) -> bool:
    """粗略判断单个字符是否是 emoji。"""
    if not ch:
        return False
    cp = ord(ch)
    return (
        0x1F300 <= cp <= 0x1FAFF  # emoji 主区
        or 0x2600 <= cp <= 0x27BF  # 符号 / dingbats
        or 0x1F000 <= cp <= 0x1F1FF  # 扑克 / 麻将
    )


# ── 必带词检查 ────────────────────────────────────────────────────────
def _check_required(title: str, body: str, channel: str, brand_rules: dict) -> list:
    items = []
    required = brand_rules.get("required_terms", {}).get(channel, [])
    if not required:
        return [RuleItem(
            category="必带词",
            severity=SEVERITY_PASS,
            message="该渠道无必带词要求",
        )]
    text = title + body
    hit = [t for t in required if t in text]
    miss = [t for t in required if t not in text]
    if miss and not hit:
        items.append(RuleItem(
            category="必带词",
            severity=SEVERITY_WARN,
            message=f"未命中该渠道的必带词：{', '.join(miss)}",
            suggestion="考虑加入命中词以提高相关性",
        ))
    elif miss:
        items.append(RuleItem(
            category="必带词",
            severity=SEVERITY_PASS,
            message=f"命中 {len(hit)}/{len(required)} 个必带词；缺：{', '.join(miss)}",
        ))
    else:
        items.append(RuleItem(
            category="必带词",
            severity=SEVERITY_PASS,
            message=f"命中全部 {len(required)} 个必带词",
        ))
    return items


# ── 通用词表检查（Phase 17.5 抽）────────────────────────────────
def _run_term_check(
    terms: list,
    text: str,
    category: str,
    hit_severity: str,
    empty_msg: str,
    pass_msg: str,
    hit_msg: str,
    suggestion: str = "",
) -> list:
    """Phase 17.5 抽：_check_banned / _check_risk 共享的"取词表 → 遍历命中"模板。

    - terms 空 → 返回 [RuleItem(category, PASS, empty_msg)]
    - 命中 → 返回 [RuleItem(category, hit_severity, hit_msg)] + 可选 suggestion
    - 未命中 → 返回 [RuleItem(category, PASS, pass_msg)]
    """
    if not terms:
        return [RuleItem(category=category, severity=SEVERITY_PASS, message=empty_msg)]
    hits = [t for t in terms if t in text]
    if hits:
        item = RuleItem(
            category=category,
            severity=hit_severity,
            message=hit_msg.format(terms=", ".join(hits)),
        )
        if suggestion:
            item.suggestion = suggestion
        return [item]
    return [RuleItem(category=category, severity=SEVERITY_PASS, message=pass_msg)]


# ── 禁词检查 ──────────────────────────────────────────────────────────
def _check_banned(title: str, body: str, brand_rules: dict) -> list:
    return _run_term_check(
        terms=brand_rules.get("banned_terms", []),
        text=title + body,
        category="禁词",
        hit_severity=SEVERITY_FAIL,
        empty_msg="当前无禁词",
        pass_msg="未命中禁词",
        hit_msg="命中禁词：{terms}",
        suggestion="请删除或替换为中性表达",
    )


# ── 风险词检查 ────────────────────────────────────────────────────────
def _check_risk(title: str, body: str, brand_rules: dict) -> list:
    return _run_term_check(
        terms=brand_rules.get("risk_terms", []),
        text=title + body,
        category="风险词",
        hit_severity=SEVERITY_WARN,
        empty_msg="当前无风险词",
        pass_msg="未命中风险词",
        hit_msg="命中风险词：{terms}",
        suggestion="可考虑用更安全的中性表达",
    )


# ── 标点 / 格式检查 ────────────────────────────────────────────────────
def _check_format(title: str, body: str) -> list:
    """粗略格式检查：标题不全是数字/标点、连续感叹号不超 3 个。"""
    items = []
    t = title.strip()
    if not t:
        return items
    # 标题全是数字 / 全是 emoji / 全是标点
    if re.fullmatch(r"[\d\s\W]+", t) and not any(_is_emoji(c) for c in t):
        items.append(RuleItem(
            category="格式",
            severity=SEVERITY_WARN,
            message="标题全是数字或标点，缺乏信息量",
            suggestion="加入文字或利益点",
        ))
    # 连续感叹号 / 问号
    if re.search(r"[!?！？]{4,}", title + body):
        items.append(RuleItem(
            category="格式",
            severity=SEVERITY_WARN,
            message="连续 4 个以上感叹号/问号，过于激烈",
            suggestion="减少标点重复",
        ))
    if not items:
        items.append(RuleItem(
            category="格式",
            severity=SEVERITY_PASS,
            message="格式正常",
        ))
    return items


# ── 重复检查（A/B/C 三条之间两两相似度）────────────────────────────
def _check_duplicates(text: str, others: list) -> list:
    """检查当前文案是否与 others 列表里的文案过于相似。"""
    items = []
    if not others:
        return [RuleItem(
            category="重复",
            severity=SEVERITY_PASS,
            message="无对照文案",
        )]
    # 简单 Jaccard 相似度（字符集合）
    text_set = set(text)
    max_sim = 0.0
    for o in others:
        o_set = set(o)
        if not text_set and not o_set:
            continue
        union = text_set | o_set
        inter = text_set & o_set
        sim = len(inter) / len(union) if union else 0
        max_sim = max(max_sim, sim)
    if max_sim >= 0.85:
        items.append(RuleItem(
            category="重复",
            severity=SEVERITY_WARN,
            message=f"与其它候选相似度 {max_sim:.0%}，过于接近",
            suggestion="建议重新生成差异更大的版本",
        ))
    else:
        items.append(RuleItem(
            category="重复",
            severity=SEVERITY_PASS,
            message=f"与其它候选相似度 {max_sim:.0%}，差异足够",
        ))
    return items


# ── 主入口 ──────────────────────────────────────────────────────────
def check_one(
    title: str,
    body: str,
    channel: str,
    channel_rules: dict,
    brand_rules: dict,
    other_candidates_text: Optional[list] = None,
) -> RuleResult:
    """单条文案规则检查。

    channel_rules: load_rules() 返回的第一个 dict
    brand_rules:   load_rules() 返回的第二个 dict
    other_candidates_text: 其它候选的 (title+body) 列表，用于重复检查；首条 None 表示无
    """
    cr = channel_rules.get("channels", {}).get(channel, {})
    items: list = []
    items.extend(_check_length(title, body, cr))
    items.extend(_check_required(title, body, channel, brand_rules))
    items.extend(_check_banned(title, body, brand_rules))
    items.extend(_check_risk(title, body, brand_rules))
    items.extend(_check_format(title, body))
    if other_candidates_text:
        items.extend(_check_duplicates(title + body, other_candidates_text))
    return RuleResult(items=items)


def check_candidates(
    candidates: list,
    channel: str,
    channel_rules: dict,
    brand_rules: dict,
) -> list:
    """批量规则检查：3 条候选两两对照。

    candidates: list[Candidate]（Phase 13 后直接读 c.title / c.body，无 edited 字段）
    返回：list[RuleResult]，与 candidates 一一对应。
    """
    texts = [c.title + c.body for c in candidates]
    results = []
    for i, c in enumerate(candidates):
        others = texts[:i] + texts[i+1:]
        r = check_one(
            c.title, c.body, channel, channel_rules, brand_rules,
            other_candidates_text=others,
        )
        results.append(r)
    return results


__all__ = [
    "load_rules",
    "check_one",
    "check_candidates",
]
