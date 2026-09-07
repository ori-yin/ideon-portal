# -*- coding: utf-8 -*-
r"""
adapters/ctr_predictor_adapter — CTR 预测旧项目适配层

Phase 1a 导出（4 个纯函数模块）：
- baseline_lookup:  get_baseline / get_baseline_ctr / get_time_multiplier
- char_utils:       count_chars / get_char_range / suggest_char_range
- column_mapping:   auto_detect / auto_detect_all + 8 组 KNOWN_*_ALIASES
- prompt_builder:   build_context_for_llm / enrich_rows_for_llm

Phase 1b 新增（CLAUDE.md §6.2 CTR_MODE）：
- CTRPredictionAdapter: 统一入口，四态分明
    - existing_predictor: 调真实 LLM（需注入 ProviderRouter）
    - baseline_only:       仅历史基准
    - demo:                演示数据稳定占位
    - l1_model:            L1 LightGBM 模型（Phase 20 · 业务主动切主流程）
    - unavailable:         无有效结果

Phase 19 新增（L1 LightGBM 静默双轨）：
- l1_predictor: predict_l1 / predict_l1_batch / predict_l1_status / L1_SUPPORTED_CHANNELS
    - 四态：model / baseline_only（模型缺失）/ unavailable（渠道不在训练范围）
    - 默认 silent；UI 必须显式开启 sidebar checkbox 才走预测
    - 模型缺失或特征构造失败均静默降级，不影响主流程

Phase 20 新增（CTR 主流程 mode="l1_model"）：
- CTRPredictionAdapter.mode 加 "l1_model"
- 路径调 predict_l1()：model→model_prediction，baseline_only→baseline_only，
  unavailable→unavailable（双轨口径统一，UI 无需特殊处理）
- UI 切到 L1：pages/01_content_studio.py sidebar 加 mode selectbox，用户主动切
- 业务拍板"切 L1 时点"（§6.3 #1）= 用户在 UI 主动操作

红线（CLAUDE.md §4.1）：
- 页面层不得 import 此 adapter 的内部模块，统一通过本 __init__.py
- 本 adapter 不得 import openai / anthropic SDK（由 core/llm_gateway 承担）
- mode = "existing_predictor" 必须显式注入 router，否则降级为 unavailable
"""

from .baseline_lookup import get_baseline, get_baseline_ctr, get_time_multiplier
from .char_utils import count_chars, get_char_range, suggest_char_range
from .column_mapping import (
    KNOWN_TITLE_ALIASES,
    KNOWN_BODY_ALIASES,
    KNOWN_CHANNEL_ALIASES,
    KNOWN_COUPON_ALIASES,
    KNOWN_WORKDAY_ALIASES,
    KNOWN_TIME_ALIASES,
    KNOWN_PLAN_ALIASES,
    KNOWN_OWNER_ALIASES,
    auto_detect,
    auto_detect_all,
)
from .prompt_builder import build_context_for_llm, enrich_rows_for_llm
from .feedback_lookup import is_feedback_ready, lookup_feedback_ctr
from .l1_predictor import (
    predict_l1,
    predict_l1_batch,
    predict_l1_status,
    L1_SUPPORTED_CHANNELS,
)

from typing import Optional  # noqa: E402

# ── Phase 1b: CTRPredictionAdapter ─────────────────────────────────────
# lazy import core/ 避免顶层循环依赖（core/ 也 import adapters 的常量？不，但保持清洁）
from core import PredictionResult, ProviderRouter  # noqa: E402


VALID_MODES = ("existing_predictor", "baseline_only", "demo", "l1_model", "unavailable")


class CTRPredictionAdapter:
    """CTR 预测统一入口，四态分明。

    用法：
        adapter = CTRPredictionAdapter(
            mode="existing_predictor",
            router=ProviderRouter(provider="siliconflow", api_key="xxx", model="yyy"),
            baseline=baseline_dict,  # 可选，默认从 JSON 读
        )
        results: list[PredictionResult] = adapter.predict_batch(rows)

    mode 决定行为：
    - existing_predictor: enrich + 拼 prompt + router.call + 合并四态
                          （无 router 时降级为 unavailable）
    - baseline_only:      enrich → 每行仅返回 baseline（无 LLM）
    - demo:               enrich → 每行返回 demo 占位（标"演示数据"）
    - unavailable:        每行 unavailable（带 error 原因）
    """

    def __init__(
        self,
        mode: str = "baseline_only",
        router: ProviderRouter = None,
        baseline: Optional[dict] = None,
    ):
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")
        self.mode = mode
        self.router = router
        self.baseline = baseline  # None 时内部用 get_baseline() 兜底

    # ── 主入口 ─────────────────────────────────────────────────────────
    def predict_batch(self, rows: list, **kwargs) -> list:
        """批量预测，返回 list[PredictionResult]，长度 == len(rows)。

        kwargs:
            model: 覆盖 router 默认 model（仅 existing_predictor 模式生效）
        """
        if not rows:
            return []

        # 1) 先 enrich，拿到 baseline + tm（任何模式都要算，便于 UI 对比展示）
        enriched = enrich_rows_for_llm(rows, baseline=self.baseline)

        # 2) 按 mode 分流
        if self.mode == "unavailable":
            return [PredictionResult.unavailable(error=f"CTR_MODE=unavailable") for _ in rows]

        if self.mode == "baseline_only":
            return [self._baseline_only_pred(r) for r in enriched]

        if self.mode == "demo":
            return [self._demo_pred(r) for r in enriched]

        if self.mode == "l1_model":
            return [self._l1_model_pred(r) for r in enriched]

        # mode == "existing_predictor"
        return self._llm_predict_batch(enriched, **kwargs)

    def predict_one(self, row: dict, **kwargs) -> PredictionResult:
        """单条便捷方法。"""
        return self.predict_batch([row], **kwargs)[0]

    # ── existing_predictor 路径 ────────────────────────────────────────
    def _llm_predict_batch(self, enriched: list, model: Optional[str] = None) -> list:
        if self.router is None:
            return [
                PredictionResult.unavailable(error="existing_predictor 模式需注入 ProviderRouter")
                for _ in enriched
            ]

        context = build_context_for_llm(baseline=self.baseline)
        batch_text = "\n".join(
            f"【{i+1}】标题：{r.get('标题','')}｜正文：{r.get('内容','')}｜渠道：{r.get('渠道','') or '未填'}"
            f"｜用券：{r.get('是否用券','') or '未填'}｜工作日：{r.get('工作日类型','') or '未填'}"
            f"｜发送时间：{r.get('发送时间','') or '未填'}｜计划类型：{r.get('计划类型','') or '未填'}"
            f"｜预算Owner：{r.get('预算Owner','') or '未填'}｜基准CTR：{r.get('_bl_str','')}｜时段系数：{r.get('_tm', 1.0):.2f}"
            for i, r in enumerate(enriched)
        )
        prompt = (
            "你是一个麦当劳中国Push文案CTR优化专家。\n\n"
            f"{context}\n\n"
            f"以下是要预测的文案（共{len(enriched)}条）：\n{batch_text}\n\n"
            "请预测每条文案的CTR，并给出具体改进建议。\n"
            "【重要】标题字数仅供参考，不是主要因素，权重低于渠道、时段和内容质量。\n"
            "输出格式：严格JSON数组，每条包含：\n"
            "- \"pred_ctr\": 预测CTR小数（如0.025=2.5%，需综合基准CTR、时段系数、内容质量判断）\n"
            "- \"confidence\": 置信度0-1（信息越充分越接近1）\n"
            "- \"suggestion\": 改进建议（30字内，具体到文案本身）\n\n"
            "直接返回JSON数组，不要其他文字："
        )

        raw = self.router.call(prompt, model=model)
        parsed = ProviderRouter.parse_json_response(raw, expected_count=len(enriched))

        # 合并 LLM 结果 + baseline/tm（_error 行降级为 unavailable）
        results = []
        for i, r in enumerate(enriched):
            bl = _safe_ctr(r.get("_bl_str"))
            tm = r.get("_tm", 1.0)
            row_parsed = parsed[i]
            if isinstance(row_parsed, dict) and "_error" in str(row_parsed.get("suggestion", "")):
                # 解析阶段已把 _error 放进 suggestion（不抛异常路径）
                results.append(PredictionResult.unavailable(
                    error=str(row_parsed["suggestion"]),
                    suggestion=str(row_parsed["suggestion"]),
                ))
            else:
                results.append(PredictionResult.model_prediction(
                    pred_ctr=row_parsed.get("pred_ctr"),
                    confidence=row_parsed.get("confidence"),
                    suggestion=str(row_parsed.get("suggestion", "")),
                    baseline_ctr=bl,
                    time_multiplier=tm,
                    source="ctr_predictor_adapter/llm",
                ))
        return results

    # ── baseline_only / demo / l1_model 工厂 ───────────────────────────
    def _baseline_only_pred(self, r: dict) -> PredictionResult:
        bl = _safe_ctr(r.get("_bl_str"))
        return PredictionResult.baseline_only(
            baseline_ctr=bl,
            suggestion="无 LLM，仅历史基准（请开启 existing_predictor 模式）"
                       if bl is None else f"基准CTR {bl*100:.2f}%，建议开启 existing_predictor 跑 LLM 精修",
            time_multiplier=r.get("_tm", 1.0),
        )

    def _demo_pred(self, r: dict) -> PredictionResult:
        bl = _safe_ctr(r.get("_bl_str"))
        # demo 占位：基准 × 时段系数 ± 5%（这里用 baseline * tm 作为"稳定占位"）
        tm = r.get("_tm", 1.0)
        sig = r.get("_signature")

        # Phase-B：feedback.db 就绪时（≥50 plans），按 signature 优先查真实 CTR
        if sig and is_feedback_ready():
            fb_ctr = lookup_feedback_ctr(sig)
            if fb_ctr is not None:
                return PredictionResult.demo(
                    pred_ctr=fb_ctr,
                    confidence=0.7,  # 历史聚合比 baseline × tm 高
                    suggestion=f"历史聚合CTR {fb_ctr*100:.2f}% (signature={sig[:8]}…)",
                    baseline_ctr=bl,
                    time_multiplier=tm,
                )

        # 兜底：原 baseline × tm 路径（DB 不就绪 / 无 signature / signature miss）
        demo_ctr = (bl * tm) if bl else 0.02  # 兜底 2%
        bl_str = f"{bl*100:.2f}%" if bl is not None else "无基准"
        return PredictionResult.demo(
            pred_ctr=round(demo_ctr, 5),
            confidence=0.5,
            suggestion=f"演示数据：基准CTR {bl_str} × 时段系数 {tm:.2f}",
            baseline_ctr=bl,
            time_multiplier=tm,
        )

    # ── l1_model 路径（Phase 20 · Phase 31A 混合校准）─────────────────────
    # L1 LightGBM 区分能力差（R²=0.08）但绝对量级还行；
    # baseline_lookup 6 维回退查表有数据基础；混合让两边互补（不重训）
    L1_BLEND_ALPHA = 0.5  # L1 / (baseline×tm) 各占一半

    def _l1_model_pred(self, r: dict) -> PredictionResult:
        """Phase 20 · l1_model mode 主路径 + Phase 31A 混合校准。

        enrich row 的中英文 key → predict_l1 接收的 kwargs 映射：
            标题 → title / 内容 → body / 渠道 → channel /
            计划类型 → plan_type / 是否用券 → coupon /
            工作日类型 → workday / _bl_str → baseline 透传

        Phase 31A：L1 推理后叠加 baseline_lookup × tm 做混合校准
        - baseline=None（兜底到 0）：final = ctr × tm（L1 相对量级 + 时段系数）
        - baseline 有值：final = α·ctr + (1-α)·(baseline × tm)（50/50 平权）
        """
        bl = _safe_ctr(r.get("_bl_str"))
        tm = r.get("_tm", 1.0)
        ctr, l1_status = _predict_l1_impl(
            title=r.get("标题", "") or r.get("title", "") or "",
            body=r.get("内容", "") or r.get("body", "") or "",
            channel=r.get("渠道", "") or r.get("channel", "") or "",
            plan_type=r.get("计划类型") or r.get("plan_type"),
            coupon=r.get("是否用券") or r.get("coupon"),
            workday=r.get("工作日类型") or r.get("workday"),
        )
        if l1_status == "model" and ctr is not None:
            if bl is not None:
                blx = bl * tm
                final_ctr = round(self.L1_BLEND_ALPHA * ctr + (1 - self.L1_BLEND_ALPHA) * blx, 5)
                suggestion = (
                    f"L1 混合校准：L1={ctr*100:.2f}% · 基准×tm={blx*100:.2f}% · "
                    f"50/50 加权 → {final_ctr*100:.2f}%"
                )
            else:
                final_ctr = round(ctr * tm, 5)
                suggestion = f"L1 预测（无基准可校准）× tm={tm:.2f} → {final_ctr*100:.2f}%"
            return PredictionResult.model_prediction(
                pred_ctr=final_ctr,
                confidence=0.6,  # LightGBM 无原生置信度，给个中等值便于 UI 显示
                suggestion=suggestion,
                baseline_ctr=bl,
                time_multiplier=tm,
                source="ctr_predictor_adapter/l1_blended",
            )
        if l1_status == "baseline_only":
            return PredictionResult.baseline_only(
                baseline_ctr=bl,
                suggestion="L1 模型暂不可用（pkl/meta 缺失），已回退到历史基准",
                time_multiplier=tm,
                source="ctr_predictor_adapter/l1_fallback",
            )
        # unavailable：渠道不在训练范围 / 特征构造失败
        return PredictionResult.unavailable(
            error=f"L1 不可用：渠道 {r.get('渠道','?')} 不在训练范围（仅 APP Push / 企微1v1 / 短信）"
                  if r.get("渠道") and r.get("渠道") not in L1_SUPPORTED_CHANNELS
                  else "L1 不可用：特征构造失败",
            suggestion="请切回 demo 或 baseline_only 模式",
        )


def _safe_ctr(bl_str) -> Optional[float]:
    """从 '_bl_str' 字段（如 "3.572%" 或 "未知"）解析出 float，失败返回 None。"""
    if not bl_str or bl_str == "未知":
        return None
    try:
        return float(str(bl_str).rstrip("%")) / 100.0
    except (ValueError, AttributeError):
        return None


# ── l1_model 工厂（Phase 20） ──────────────────────────────────────
# CTRPredictionAdapter._l1_model_pred 定义在 class 内（闭包访问 self.predict_l1）。
# 此处保留纯函数包装 predict_l1，方便测试与外部调用。
from .l1_predictor import predict_l1 as _predict_l1_impl  # noqa: E402


__all__ = [
    # 纯函数（Phase 1a）
    "get_baseline",
    "get_baseline_ctr",
    "get_time_multiplier",
    "count_chars",
    "get_char_range",
    "suggest_char_range",
    "KNOWN_TITLE_ALIASES",
    "KNOWN_BODY_ALIASES",
    "KNOWN_CHANNEL_ALIASES",
    "KNOWN_COUPON_ALIASES",
    "KNOWN_WORKDAY_ALIASES",
    "KNOWN_TIME_ALIASES",
    "KNOWN_PLAN_ALIASES",
    "KNOWN_OWNER_ALIASES",
    "auto_detect",
    "auto_detect_all",
    "build_context_for_llm",
    "enrich_rows_for_llm",
    # 统一入口（Phase 1b）
    "CTRPredictionAdapter",
    "VALID_MODES",
    # Phase 19 L1 静默双轨
    "predict_l1",
    "predict_l1_batch",
    "predict_l1_status",
    "L1_SUPPORTED_CHANNELS",
]