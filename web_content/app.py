# -*- coding: utf-8 -*-
r"""
web/app.py — FastAPI 入口（MCD AI 内容平台 · v2 全量迁移版）

【项目位置】C:\ideon\mcd-ai-content-platform\web\
【迁移完成度】5/5 页面（00-05）已全部从 Streamlit 迁过来

【启动】
  cd web
  pip install -r requirements.txt
  uvicorn app:app --reload --port 8530
  访问 http://localhost:8530/

【路由清单】
  页面 GET：
    /                00 首页
    /01              01 内容工坊
    /02              02 内容诊断
    /03              03 内容预测
    /04              04 历史洞察
    /05              05 真实结果回流

  API POST（HTMX 表单提交）：
    /api/studio/generate     生成 3 条候选
    /api/studio/select       选择候选（A/B/C）
    /api/studio/ctr-mode     切换 CTR 主流程模式
    /api/studio/l1-toggle    显示/隐藏 L1 实验对比
    /api/diagnosis/diagnose     开始诊断
    /api/diagnosis/rewrite      生成 AI 改写候选
    /api/batch/upload       上传 CSV/Excel
    /api/batch/evaluate     启动批量评估
    /api/batch/download     下载 CSV 结果
    /api/insights/upload       上传历史数据
    /api/feedback/upload       导入回流数据

  GET /health             健康检查

【业务层复用】
  所有 service / repository / prompt 全部走父目录（PROJECT_ROOT），
  不重写业务逻辑，保证单源一致性。
"""

from __future__ import annotations

import io
import os
import sys
import csv
import json
import time
import hmac
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ============================================================
# 路径：双 sys.path 同时挂 portal 根 + services/ai_content
# - portal 根：让 from services.ai_content.xxx / from llm_config 工作
# - services/ai_content：业务模块内部仍用 from core/services/adapters/prompts
#   的 mcd-ai 风格相对 import，需要把 ai_content 当成"伪 mcd-ai 根"加进去
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

PROJECT_ROOT = BASE_DIR.parent  # portal 根
AI_CONTENT_ROOT = PROJECT_ROOT / "services" / "ai_content"

for _p in (PROJECT_ROOT, AI_CONTENT_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ============================================================
# 业务层 import（在 sys.path injection 后）
# ============================================================
# 业务层：与业务模块同源（mcd-ai 风格 from core/services/adapters/prompts），
# sys.path 里有 services/ai_content/，所以直接相对引用，跨 namespace package 不踩坑
from core.schemas import (
    TaskInput,
    CHANNELS,
    TARGET_AUDIENCE,
    OBJECTIVES,
    STAGES,
    SCENES,
    TONES,
    ACTIONS,
    PLAN_TYPES,
    COUPON_FLAGS,
)
from core.product_benefit import (
    get_product_categories,
    get_benefit_types,
    get_custom_label,
    options_with_custom,
)
from core.analytics_utils import weighted_ctr

from services.rule_engine import load_rules, check_one, check_candidates
from services.ctr_prediction_service import predict_one, predict_for_candidates
from services.similarity_service import find_similar, summarize_similar
from services.copy_analysis_service import diagnose as svc_diagnose
from services.generation_service import generate, GenerationError, rank_candidates_by_ctr
from services.batch_evaluation_service import (
    parse_batch_file,
    evaluate_batch,
    rows_to_dataframe,
    rows_to_csv_bytes,
    save_predictions_to_records,
)
from services.text_analyzer import (
    add_tokens,
    word_frequency,
    emoji_frequency,
    compare_token,
)
from services.analytics.high_effort_plans import rank_plans
from services.analytics.similarity import find_similar_plans
from services.analytics.daily_trend import daily_aggregate, daily_summary
from services.analytics.owner_compare import owner_compare
from services.feedback_service import (
    import_feedback,
    count as feedback_count,
    aggregate_by_signature,
    read_recent as feedback_read_recent,
)
from services.generation_service import read_recent as gen_read_recent
from services.data_loader import build as data_loader_build

from adapters.ctr_predictor_adapter import predict_l1, predict_l1_status, L1_SUPPORTED_CHANNELS

from prompts import copy_rewrite

# web_content 内部 state（相对引用；portal app.py include_router 时 sys.path 包含 web_content）
from . import state
from .state import (
    S_01, S_02, S_03, S_04, S_05,
    store_df, get_df, release_df, reset_01, form_change_signature,
    insights_cache_get, insights_cache_put, insights_cache_clear,
)


# ============================================================
# LLM 路由器（v3.4：接 portal 的 ~/.ideon-portal/llm_settings.yaml）
# - 不用 ai_content.core.llm_gateway.ProviderRouter（它只接受 minimax/openai/siliconflow/qianfan）
# - portal 配置允许任意中文 provider（"麦当劳AI网关"）+ 自定义 base_url
# - 自己实现 _PortalRouter 兼容 mcd-ai ProviderRouter 接口（call/provider/model/api_key）
# ============================================================
from llm_config import load_config as _portal_load_config, LLM_PROVIDERS as _PORTAL_LLM_PROVIDERS


def get_llm_status() -> dict:
    """返回 {configured, model} 给 base_context()（llm_pill.html 顶部状态用）。"""
    from llm_config import get_status as _llm_get_status  # portal 根目录 llm_config
    s = _llm_get_status()
    return {
        "configured": s.get("configured", False),
        "model": s.get("model") or "未配置",
    }


class _PortalRouter:
    """简单 LLM 路由器：兼容 mcd-ai ProviderRouter 接口（call/provider/model/api_key）。

    portal LLM 配置允许任意中文 provider + 自定义 base_url，按 protocol 字段选 openai/anthropic SDK。
    """
    def __init__(self, provider: str, model: str, api_key: str,
                 protocol: str = "openai", base_url: str | None = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.protocol = protocol
        self.base_url = base_url

    def call(self, prompt: str, model: str | None = None) -> str:
        """调 LLM 返回文本。失败返回 _error dict 字符串（与 ProviderRouter 一致）。"""
        import json as _json
        used_model = model or self.model
        try:
            if self.protocol == "anthropic":
                import anthropic
                client = anthropic.Anthropic(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=60.0,
                )
                resp = client.messages.create(
                    model=used_model,
                    max_tokens=4000,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}],
                )
                text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
                return "\n".join(text_parts).strip()
            else:
                import openai
                if self.base_url:
                    client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=60.0)
                else:
                    client = openai.OpenAI(api_key=self.api_key, timeout=60.0)
                resp = client.chat.completions.create(
                    model=used_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=4000,
                )
                return resp.choices[0].message.content.strip()
        except Exception as e:
            cls = e.__class__.__name__
            if "Authentication" in cls or "Permission" in cls:
                msg = "API鉴权失败（检查 api_key）"
            elif "RateLimit" in cls:
                msg = "API限流（稍后重试）"
            elif "Timeout" in cls:
                msg = "API超时"
            elif "Connection" in cls:
                msg = "API网络错误"
            elif "BadRequest" in cls:
                msg = "API请求格式错误"
            else:
                msg = f"API异常: {cls}"
            return _json.dumps({"_error": msg}, ensure_ascii=False)


def _build_llm_router():
    """从 portal ~/.ideon-portal/llm_settings.yaml 构造 LLM 路由器。

    容错：yaml 缺失 / api_key 空 → None（api_01_generate 走 Demo 占位）。
    SDK 未装 / API 异常 → router.call 返回 _error dict，不抛异常让页面崩。
    """
    cfg = _portal_load_config() or {}
    if not cfg.get("api_key") or not cfg.get("provider"):
        return None
    # 按 provider 找 protocol（找不到默认 openai；用户配 base_url 时也走 openai 协议）
    protocol = "openai"
    for p in _PORTAL_LLM_PROVIDERS:
        if p["name"] == cfg["provider"]:
            protocol = p.get("protocol", "openai")
            break
    return _PortalRouter(
        provider=str(cfg["provider"]).strip(),
        model=cfg.get("model", ""),
        api_key=cfg["api_key"],
        protocol=protocol,
        base_url=cfg.get("base_url", "") or None,
    )


# ============================================================
# Jinja filters
# ============================================================
def _jinja_safe(v):
    """表格 cell 转字符串：None/NaN → '—'。"""
    if v is None:
        return "—"
    try:
        if isinstance(v, float) and v != v:  # NaN
            return "—"
    except Exception:
        pass
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        # 不强制转 int；保留浮点精度
        pass
    return v


# ============================================================
# 模板引擎（portal 已有 /static mount + Cache-Control middleware，
# web_content 只暴露页面 + API，不重复挂载）
# ============================================================
router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["safe_cell"] = _jinja_safe

# 性能优化 P0 B · 2026-09-03：关 auto_reload + 开 LRUCache
# 默认 auto_reload=True → 每次 render 都 stat 模板文件检查更新；cache=None → 不缓存编译后的模板。
# 生产模式关掉可省 ~1ms × 每次 render（实测 5 次 nt.stat ~1ms 累计）。
# 设 MCD_DEBUG=1 可恢复 dev 热重载。
import os as _os
_DEBUG = _os.environ.get("MCD_DEBUG", "0") == "1"
templates.env.auto_reload = _DEBUG
if not _DEBUG:
    templates.env.cache = {}  # dict 缓存编译后的模板；项目模板 < 50 个，无界安全


# ============================================================
# 导航配置（单一来源）
# ============================================================
# 导航：v3.4 集成到 ideon-portal 后只保留内容工坊 + 历史洞察
# home/diagnosis/batch/feedback/settings 已迁移走或由 portal 接管
NAV_PAGES = [
    {"id": "studio", "route": "/studio", "name": "内容工坊",
     "subtitle": "LLM 生成 + CTR 预测 + 规则校验", "icon": "edit"},
    {"id": "insights", "route": "/insights", "name": "历史洞察",
     "subtitle": "Plan 排行 · 高低表现词 · 每日趋势", "icon": "chart"},
]


# ============================================================
# base_context：所有页面共享的导航/LLM 状态注入
# ============================================================
def base_context(active_id: str) -> dict:
    current = next((p for p in NAV_PAGES if p["id"] == active_id), NAV_PAGES[0])
    llm = get_llm_status()
    return {
        "nav_pages": NAV_PAGES,
        "active_id": active_id,
        "page_title": current["name"],
        "page_subtitle": current["subtitle"],
        "llm_configured": llm["configured"],
        "llm_model": llm["model"],
    }


# ============================================================
# 01 内容工坊
# ============================================================
def _01_context() -> dict:
    """构造 01 页面的完整上下文。"""
    ctx = base_context("studio")

    # options
    product_cats = get_product_categories()
    benefit_types = get_benefit_types()
    custom_label = get_custom_label()
    ctx.update({
        "product_categories": options_with_custom(product_cats),
        "benefit_types": options_with_custom(benefit_types),
        "audience_opts": TARGET_AUDIENCE,
        "objective_opts": OBJECTIVES,
        "stage_opts": STAGES,
        "tone_opts": TONES,
        "channel_opts": CHANNELS,
        "scene_opts": SCENES,
        "action_opts": ACTIONS,
        "plan_type_opts": PLAN_TYPES,
        "coupon_opts": COUPON_FLAGS,
        "ctr_mode_options": S_01["ctr_mode_options"],
        # 状态
        "task_input": S_01["task_input"] or {},
        "candidates": S_01["candidates"],
        "selected_id": S_01["selected_id"],
        "rule_results": S_01["rule_results"],
        "ctr_results": S_01["ctr_results"],
        "similar_summary": S_01["similar_summary"],
        "show_l1": S_01["show_l1"],
        "ctr_mode": S_01["ctr_mode"],
        "last_error": S_01["last_error"],
    })
    # 派生：选中候选 + 其规则/CTR
    sel_id = S_01["selected_id"]
    cand_idx = next(
        (i for i, c in enumerate(S_01["candidates"]) if c.get("id") == sel_id),
        0,
    ) if S_01["candidates"] else 0
    ctx["selected_cand"] = (
        S_01["candidates"][cand_idx] if S_01["candidates"] else {}
    )
    ctx["selected_rule"] = (
        S_01["rule_results"][cand_idx]
        if S_01["rule_results"] and cand_idx < len(S_01["rule_results"])
        else None
    )
    ctx["selected_ctr"] = (
        S_01["ctr_results"][cand_idx]
        if S_01["ctr_results"] and cand_idx < len(S_01["ctr_results"])
        else None
    )
    # 派生 task（用于右侧 channel/stage/objective 模板）
    ctx["task"] = S_01["task_input"] or {}
    # L1 派生（Phase 19 双轨开关）
    l1_ctr = None
    if S_01["show_l1"] and S_01["task_input"] and S_01["candidates"]:
        sel = ctx["selected_cand"]
        if sel:
            try:
                pred, status_l1 = predict_l1(
                    title=sel.get("title", ""),
                    body=sel.get("body", ""),
                    channel=S_01["task_input"].get("channel", "APP Push"),
                    plan_type=S_01["task_input"].get("plan_type", "未知"),
                    coupon=S_01["task_input"].get("coupon", "未知"),
                    workday=S_01["task_input"].get("planned_send_date"),
                )
                l1_ctr = {"pred_ctr": pred, "status": status_l1}
            except Exception:
                l1_ctr = None
    ctx["l1_ctr"] = l1_ctr
    ctx["l1_status_msg"] = (
        f"L1 状态：{predict_l1_status()}；支持渠道：{'、'.join(L1_SUPPORTED_CHANNELS)}"
        if predict_l1_status() == "model"
        else None
    )
    return ctx


@router.get("/studio", response_class=HTMLResponse)
async def page_01(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "pages/01_内容工坊.html", _01_context()
    )


@router.post("/api/studio/generate", response_class=HTMLResponse)
async def api_01_generate(request: Request) -> Response:
    """接收 form，调 generate + check_candidates + predict_for_candidates，返回 /01 页面。"""
    form = await request.form()
    form_dict = {k: form.get(k, "") for k in (
        "product_category", "benefit_type", "audience", "channel",
        "objective", "stage", "scene", "tone", "expected_action",
        "plan_type", "coupon", "planned_send_date", "extra_requirements",
        "text_has_coupon",
    )}
    # planned_send_date 兜底
    if not form_dict.get("planned_send_date"):
        form_dict["planned_send_date"] = None

    try:
        task = TaskInput.from_form(form_dict)
    except ValueError as e:
        S_01["last_error"] = f"必填字段缺失：{e}"
        return RedirectResponse(url="/studio", status_code=303)

    channel_rules, brand_rules = load_rules()
    router = _build_llm_router()
    try:
        candidates = generate(task, router=router, channel_rules=channel_rules)
    except GenerationError as e:
        S_01["last_error"] = f"生成失败：{e}"
        S_01["task_input"] = task.to_dict()
        return RedirectResponse(url="/studio", status_code=303)

    S_01["last_error"] = None
    S_01["task_input"] = task.to_dict()
    S_01["candidates"] = [c.to_dict() for c in candidates]
    rule_results = check_candidates(candidates, task.channel, channel_rules, brand_rules)
    S_01["rule_results"] = [r.to_dict() for r in rule_results]

    ctr_mode = S_01["ctr_mode"]
    if ctr_mode == "l1_model" and predict_l1_status() != "model":
        ctr_mode = "demo"
    # Phase 29 · 2026-09-01 用户翻牌：候选展示固定 A→B→C（不再按 CTR 重排）
    # 反哺影响排序的拍板 #6 改为：CTR 仍展示在右侧"参考结果"，但卡片顺序保持 ABC 固定
    ctr_results = predict_for_candidates(candidates, task, mode=ctr_mode)
    S_01["candidates"] = [c.to_dict() for c in candidates]
    S_01["ctr_results"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in ctr_results]
    # 默认选中 A（Phase 29 用户拍板）
    S_01["selected_id"] = "A"

    first = candidates[0]
    sim_df = find_similar(first.title, first.body, task.channel)
    S_01["similar_summary"] = summarize_similar(sim_df)
    S_01["last_generated_signature"] = form_change_signature(task.to_dict())

    return RedirectResponse(url="/studio", status_code=303)


@router.post("/api/studio/select", response_class=HTMLResponse)
async def api_01_select(request: Request) -> Response:
    form = await request.form()
    sel = form.get("selected_id", "A")
    if sel in ("A", "B", "C"):
        S_01["selected_id"] = sel
    return RedirectResponse(url="/studio", status_code=303)


@router.post("/api/studio/ctr-mode", response_class=HTMLResponse)
async def api_01_ctr_mode(request: Request) -> Response:
    form = await request.form()
    mode = form.get("ctr_mode", "demo")
    if mode in S_01["ctr_mode_options"]:
        if mode == "l1_model" and predict_l1_status() != "model":
            mode = "demo"
        S_01["ctr_mode"] = mode
    return RedirectResponse(url="/studio", status_code=303)


@router.post("/api/studio/l1-toggle", response_class=HTMLResponse)
async def api_01_l1_toggle(request: Request) -> Response:
    form = await request.form()
    S_01["show_l1"] = form.get("show_l1") == "1"
    return RedirectResponse(url="/studio", status_code=303)


# ============================================================
# ============================================================
# 04 历史洞察
# ============================================================
def _safe_int(v, default=0):
    try:
        if v is None:
            return default
        return int(v)
    except (ValueError, TypeError):
        return default


def _plan_detail(df: pd.DataFrame, plan_id: str) -> Optional[dict]:
    """按 Plan ID 精确查询，返回 plan 元数据 + 触达/点击/CTR + 样本标题正文。

    与 rank_plans 一行字段对齐 + 加 title/body 示例，给 Tab 1 「输入 Plan ID 查详情」用。
    """
    if df is None or df.empty or "Plan ID" not in df.columns:
        return None
    sub = df[df["Plan ID"].astype(str) == plan_id]
    if sub.empty:
        return None
    reach = int(sub["触达成功"].sum())
    click = int(sub["点击人次"].sum())
    has_date = "发送日期" in sub.columns
    n_days = sub["发送日期"].dt.date.nunique() if has_date else 0
    sample_title = str(sub["标题"].iloc[0]) if "标题" in sub.columns else ""
    sample_body = str(sub["正文"].iloc[0])[:120] if "正文" in sub.columns else ""
    detail = {
        "plan_id": plan_id,
        "plan_name": str(sub["Plan名称"].iloc[0]) if "Plan名称" in sub.columns else "",
        "channel": str(sub["渠道"].iloc[0]) if "渠道" in sub.columns else "",
        "owner": str(sub["owner"].iloc[0]) if "owner" in sub.columns else "",
        "n_records": int(len(sub)),
        "n_days": int(n_days) if n_days else 0,
        "触达成功": reach,
        "点击": click,
        "加权CTR%": round(weighted_ctr(click, reach), 2),
        "标题字数均值": round(float(sub["标题"].astype(str).str.len().mean()), 1)
        if "标题" in sub.columns else 0,
        "正文字数均值": round(float(sub["正文"].astype(str).str.len().mean()), 1)
        if "正文" in sub.columns else 0,
        "样本标题": sample_title,
        "样本正文": sample_body,
    }
    if "_tokens" in sub.columns:
        tok_set = set()
        for s in sub["_tokens"]:
            tok_set |= set(s)
        detail["覆盖高效词数"] = len(tok_set)
    return detail


def _df_to_rows(df, columns: Optional[list] = None, limit: int = 5000) -> list[dict]:
    """DataFrame → list[dict]，处理 NaN。"""
    if df is None or df.empty:
        return []
    if columns is None:
        columns = list(df.columns)
    safe_cols = [c for c in columns if c in df.columns]
    if limit and len(df) > limit:
        df = df.head(limit)
    rows = []
    for _, row in df[safe_cols].iterrows():
        d = {}
        for c in safe_cols:
            v = row[c]
            try:
                if v is None:
                    d[c] = ""
                    continue
                if isinstance(v, float):
                    import math
                    if math.isnan(v):
                        d[c] = ""
                        continue
                    # 整数浮点化简（仅小数点后为 0 时）
                    if v.is_integer() and abs(v) < 1e15:
                        d[c] = int(v)
                    else:
                        d[c] = round(v, 4)
                else:
                    d[c] = v
            except Exception:
                d[c] = str(v)
        rows.append(d)
    return rows


def _insights_default_params() -> dict:
    """04 历史洞察所有 tab 的 query 参数默认值。"""
    return {
        "min_reach": "1000", "top_n": "30",
        "wf_min_plans": "3", "wf_top_n": "50", "wf_compare_sel": "",
        "ef_min_plans": "3", "ef_top_n": "20", "ef_compare_sel": "",
        "rank_plan_sel": "",
        "sim_title": "", "sim_body": "", "sim_topk": "5",
        "by_channel": "",
        "oc_min_plans": "3", "oc_min_reach": "1000",
    }


def _build_insights_ctx(active_tab: str, params: dict) -> dict:
    """拼装 /insights 页面顶层 ctx（ins 概览 + active_tab + params）。"""
    return {
        "ins": {
            "filename": S_04["filename"],
            "n_rows": S_04["n_rows"],
            "n_has_copy": S_04["n_has_copy"],
            "n_channels": S_04["n_channels"],
            "channels": S_04["channels"],
            "date_range": S_04["date_range"],
        },
        "error_msg": S_04["error_msg"],
        "active_tab": active_tab,
        "params": params,
    }


def _compute_insights_tab_context(df, active_tab: str, p: dict) -> dict:
    """Phase 51：04 历史洞察 tab 计算 helper（带 per-tab LRU 缓存）。

    page_04 + /api/insights/tab 共用。返回 dict 是 ctx 的字段增量，
    调用方 update 到自己的 ctx 即可。

    cache key = (df_ref, tab, frozenset(params.items()))，
    df 变更（/api/insights/upload）时统一 clear。
    """
    def _insights_cached(tab: str, params: dict, compute_fn):
        key = (S_04["df_ref"], tab, frozenset(params.items()))
        hit = insights_cache_get(key)
        if hit is not None:
            return hit
        val = compute_fn()
        insights_cache_put(key, val)
        return val

    ctx: dict = {}

    if active_tab == "rank":
        min_reach = _safe_int(p["min_reach"], 1000)
        top_n = _safe_int(p["top_n"], 30)

        def _compute_rank():
            out = rank_plans(df, min_reach=min_reach, top_n=top_n)
            if not out.empty:
                show = out.copy()
                show["加权CTR%"] = show["加权CTR%"].apply(lambda v: round(float(v), 2))
            else:
                show = out
            return {
                "df_rows": _df_to_rows(show, columns=list(show.columns) if not show.empty else None),
                "columns": list(show.columns) if not show.empty else [],
            }

        cached = _insights_cached("rank", {"min_reach": min_reach, "top_n": top_n}, _compute_rank)
        ctx["df_rows"] = cached["df_rows"]
        ctx["columns"] = cached["columns"]

        sel = p["rank_plan_sel"].strip()
        ctx["plan_detail"] = None
        if sel:
            ctx["plan_detail"] = _plan_detail(df, sel)

    elif active_tab == "wf":
        min_plans = _safe_int(p["wf_min_plans"], 3)
        top_n = _safe_int(p["wf_top_n"], 50)

        def _compute_wf():
            wf = word_frequency(df, min_plans=min_plans).head(top_n)
            if wf.empty:
                return {
                    "high_rows": [], "low_rows": [],
                    "high_cols": [], "low_cols": [],
                    "wf_words": [],
                }
            high = wf[wf["差值"] > 0].head(15)
            low = wf[wf["差值"] < 0].head(15)
            for sub in (high, low):
                for col in sub.columns:
                    if sub[col].dtype.kind == "f":
                        sub[col] = sub[col].round(4)
            return {
                "high_rows": _df_to_rows(high),
                "high_cols": list(high.columns),
                "low_rows": _df_to_rows(low),
                "low_cols": list(low.columns),
                "wf_words": wf[wf.columns[0]].tolist()[:50],
            }

        cached = _insights_cached(
            "wf", {"wf_min_plans": min_plans, "wf_top_n": top_n}, _compute_wf
        )
        ctx["high_rows"] = cached["high_rows"]
        ctx["high_cols"] = cached["high_cols"]
        ctx["low_rows"] = cached["low_rows"]
        ctx["low_cols"] = cached["low_cols"]
        ctx["wf_words"] = cached["wf_words"]

        ctx["compare"] = None
        sel = p["wf_compare_sel"]
        if sel:
            cmp = compare_token(df, sel)
            if cmp:
                in_block = cmp.get("含", {}) or {}
                out_block = cmp.get("不含", {}) or {}
                ctr_in = float(in_block.get("ctr", 0.0))
                ctr_out = float(out_block.get("ctr", 0.0))
                ctx["compare"] = {
                    "sel_word": sel,
                    "reach_with": int(in_block.get("reach", 0)),
                    "reach_without": int(out_block.get("reach", 0)),
                    "ctr_with": round(ctr_in, 2),
                    "ctr_without": round(ctr_out, 2),
                    "delta_pp": round(ctr_in - ctr_out, 2),
                    "n_plans_with": int(in_block.get("n_plans", 0)),
                    "n_plans_without": int(out_block.get("n_plans", 0)),
                }

    elif active_tab == "ef":
        min_plans = _safe_int(p["ef_min_plans"], 3)
        top_n = _safe_int(p["ef_top_n"], 20)

        def _compute_ef():
            ef = emoji_frequency(df, min_plans=min_plans).head(top_n)
            for col in ef.columns:
                if ef[col].dtype.kind == "f":
                    ef[col] = ef[col].round(4)
            return {
                "df_rows": _df_to_rows(ef),
                "columns": list(ef.columns),
            }

        cached = _insights_cached(
            "ef", {"ef_min_plans": min_plans, "ef_top_n": top_n}, _compute_ef
        )
        ctx["df_rows"] = cached["df_rows"]
        ctx["columns"] = cached["columns"]

        sel = p["ef_compare_sel"].strip()
        ctx["ef_compare"] = None
        if sel:
            if "_emojis" not in df.columns:
                df = add_tokens(df)
            cmp = compare_token(df, sel, col="_emojis")
            if cmp:
                in_block = cmp.get("含", {}) or {}
                out_block = cmp.get("不含", {}) or {}
                ctr_in = float(in_block.get("ctr", 0.0))
                ctr_out = float(out_block.get("ctr", 0.0))
                ctx["ef_compare"] = {
                    "sel_emoji": sel,
                    "reach_with": int(in_block.get("reach", 0)),
                    "reach_without": int(out_block.get("reach", 0)),
                    "ctr_with": round(ctr_in, 2),
                    "ctr_without": round(ctr_out, 2),
                    "delta_pp": round(ctr_in - ctr_out, 2),
                    "n_plans_with": int(in_block.get("n_plans", 0)),
                    "n_plans_without": int(out_block.get("n_plans", 0)),
                }

    elif active_tab == "tl":
        def _compute_tl():
            if "标题" not in df.columns or "Plan ID" not in df.columns:
                return {"df_rows": []}
            work = df.copy()
            work["_title_len"] = work["标题"].astype(str).str.len()
            bins = [-1, 0, 5, 10, 15, 20, 1000]
            labels = ["空", "1-5", "6-10", "11-15", "16-20", "21+"]
            work["_bucket"] = pd_cut(work["_title_len"], bins=bins, labels=labels)

            rows = []
            for bucket, sub in work.groupby("_bucket", dropna=False, observed=True):
                reach = int(sub["触达成功"].sum())
                click = int(sub["点击人次"].sum())
                if reach == 0:
                    continue
                n_plans = int(sub["Plan ID"].nunique()) if "Plan ID" in sub.columns else 0
                rows.append({
                    "字数桶": str(bucket),
                    "n_plans": n_plans,
                    "触达成功": reach,
                    "点击": click,
                    "加权CTR%": weighted_ctr(click, reach),
                })
            return {"df_rows": rows}

        cached = _insights_cached("tl", {}, _compute_tl)
        ctx["df_rows"] = cached["df_rows"]

    elif active_tab == "sim":
        q_title = p.get("sim_title", "")
        q_body = p.get("sim_body", "")
        top_k = _safe_int(p["sim_topk"], 5)

        def _compute_sim():
            if not q_title and not q_body:
                return {"df_rows": [], "columns": []}
            sim = find_similar_plans(df, q_title, q_body, top_k=top_k)
            if sim is not None and not sim.empty:
                show_cols = [c for c in ("plan_id", "plan_name", "channel", "ctr", "similarity")
                             if c in sim.columns]
                for col in sim.columns:
                    if sim[col].dtype.kind == "f":
                        sim[col] = sim[col].round(4)
                return {
                    "df_rows": _df_to_rows(sim, columns=show_cols),
                    "columns": show_cols,
                }
            return {"df_rows": [], "columns": []}

        cached = _insights_cached(
            "sim",
            {"sim_title": q_title, "sim_body": q_body, "sim_topk": top_k},
            _compute_sim,
        )
        ctx["df_rows"] = cached["df_rows"]
        ctx["columns"] = cached["columns"]

    elif active_tab == "daily":
        by_channel = bool(p.get("by_channel"))

        def _compute_daily():
            summary = daily_summary(df) or {}
            out = daily_aggregate(df, channel_col="渠道" if by_channel else None)
            if not out.empty:
                for col in out.columns:
                    if out[col].dtype.kind == "f":
                        out[col] = out[col].round(4)
                show_cols = [c for c in (
                    "date", "channel", "n_records", "触达成功", "点击", "加权CTR%", "周环比%",
                ) if c in out.columns]
                return {
                    "summary": summary,
                    "df_rows": _df_to_rows(out, columns=show_cols),
                    "columns": show_cols,
                }
            return {"summary": summary, "df_rows": [], "columns": []}

        cached = _insights_cached("daily", {"by_channel": by_channel}, _compute_daily)
        ctx["summary"] = cached["summary"]
        ctx["df_rows"] = cached["df_rows"]
        ctx["columns"] = cached["columns"]

    elif active_tab == "owner":
        min_plans = _safe_int(p["oc_min_plans"], 3)
        min_reach = _safe_int(p["oc_min_reach"], 1000)

        def _compute_owner():
            out = owner_compare(df, min_plans=min_plans, min_reach=min_reach)
            if not out.empty:
                for col in out.columns:
                    if out[col].dtype.kind == "f":
                        out[col] = out[col].round(4)
                return {
                    "df_rows": _df_to_rows(out),
                    "columns": list(out.columns),
                }
            return {"df_rows": [], "columns": []}

        cached = _insights_cached(
            "owner",
            {"oc_min_plans": min_plans, "oc_min_reach": min_reach},
            _compute_owner,
        )
        ctx["df_rows"] = cached["df_rows"]
        ctx["columns"] = cached["columns"]

    else:
        # 未知 tab：兜底空
        ctx["df_rows"] = []

    return ctx


@router.get("/insights", response_class=HTMLResponse)
async def page_04(request: Request) -> HTMLResponse:
    ctx = base_context("insights")
    df = get_df(S_04["df_ref"])

    params = _insights_default_params()
    for k in list(params.keys()):
        v = request.query_params.get(k, "")
        if v:
            params[k] = v
    active_tab = request.query_params.get("tab", "rank")

    ctx.update(_build_insights_ctx(active_tab, params))

    if df is not None and not df.empty:
        ctx.update(_compute_insights_tab_context(df, active_tab, params))

    return templates.TemplateResponse(
        request, "pages/04_历史洞察.html", ctx
    )


# Phase 51：HTMX tab 局部替换端点（/api/insights/tab?tab=X）
# 返回 #ins-tab-block 片段，避免全页 reload + 滚到顶。
# tab 链接 + 各 tab filter form 都用 hx-get 走这个端点。
@router.get("/api/insights/tab", response_class=HTMLResponse)
async def api_04_tab(request: Request) -> HTMLResponse:
    df = get_df(S_04["df_ref"])
    params = _insights_default_params()
    for k in list(params.keys()):
        v = request.query_params.get(k, "")
        if v:
            params[k] = v
    active_tab = request.query_params.get("tab", "rank")

    ctx = _build_insights_ctx(active_tab, params)
    if df is not None and not df.empty:
        ctx.update(_compute_insights_tab_context(df, active_tab, params))

    return templates.TemplateResponse(
        request, "_insights_tab_block.html", ctx
    )


def pd_cut(series, bins, labels):
    import pandas as _pd
    return _pd.cut(series, bins=bins, labels=labels)


@router.post("/api/insights/upload", response_class=HTMLResponse)
async def api_04_upload(request: Request, file: UploadFile = File(...)) -> Response:
    S_04["error_msg"] = ""
    try:
        file_bytes = await file.read()
        fname = file.filename or ""
        if fname.lower().endswith(".csv"):
            import pandas as pd
            df = pd.read_csv(io.BytesIO(file_bytes))
            meta = {"n_rows": len(df), "sheet_name": "csv", "all_sheets": ["csv"]}
        else:
            df, meta = data_loader_build(file_bytes)
    except Exception as e:  # noqa: BLE001
        S_04["error_msg"] = f"解析失败：{e}"
        return RedirectResponse(url="/insights", status_code=303)

    # 释放旧 df
    if S_04["df_ref"] is not None:
        release_df(S_04["df_ref"])

    # 新 df 上线，旧 tab 缓存全部失效
    insights_cache_clear()

    try:
        df = add_tokens(df)
    except Exception:
        pass

    S_04["df_ref"] = store_df(df)
    S_04["filename"] = file.filename or ""
    S_04["n_rows"] = meta.get("n_rows", len(df))
    S_04["n_has_copy"] = meta.get("n_has_copy")
    S_04["channels"] = meta.get("channels") or []
    S_04["n_channels"] = len(S_04["channels"])
    if meta.get("date_min"):
        S_04["date_range"] = f"{meta['date_min']} ~ {meta.get('date_max', '')}"
    else:
        S_04["date_range"] = "—"

    return RedirectResponse(url="/insights", status_code=303)




# ============================================================


# ============================================================
# /settings  字典维护（Phase 39 · 2026-09-02）
# ============================================================
# ============================================================


# ============================================================
# 启动预热（性能优化 · 2026-09-03）
# ============================================================
# 根因：Jinja2 默认 auto_reload=True，每次渲染都 stat 模板文件；
#       且 01 内容工坊首次渲染要编译 bytecode，导致 /studio 首次 GET 1.33s。
# 修复：服务启动时主动预热 6 个页面模板到 env cache，首次 GET 降至 ~50ms。
# 实测：启动多 ~100ms（一次性），后续每个页面首次访问从 1.3s → ~50ms。
_STARTUP_PAGE_TEMPLATES = (
    "home.html",
    "pages/01_内容工坊.html",
    "pages/02_内容诊断.html",
    "pages/03_内容预测.html",
    "pages/04_历史洞察.html",
    "pages/05_真实结果回流.html",
)


