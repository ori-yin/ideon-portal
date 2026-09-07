# -*- coding: utf-8 -*-
r"""
core/schemas.py — 业务 dataclass 契约层

覆盖范围（Phase 16.5 完整）：
- PredictionResult: CTR 预测四态分明（CLAUDE.md §4.2 强制）
- TaskInput / Candidate / CopyAnalysis：均已实现

四态定义：
- model_prediction: 真实 LLM 预测（基于 baseline + 推理）
- baseline_only:    仅历史基准，无 LLM
- demo:              演示数据稳定占位（UI 必标"演示数据"）
- unavailable:       无有效结果（error 必填）

UI 红线：
- 不得把 demo / baseline_only 标成"预测准确率 XX%"
- 不得让 unavailable 的 pred_ctr 进入计算
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal, Any


# ── 四态类型别名 ───────────────────────────────────────────────────────
ResultType = Literal["model_prediction", "baseline_only", "demo", "unavailable"]
VALID_RESULT_TYPES: tuple = ("model_prediction", "baseline_only", "demo", "unavailable")


@dataclass
class PredictionResult:
    """CTR 预测结果统一结构。

    字段语义：
    - result_type: 四态枚举，必填
    - pred_ctr:    预测 CTR（小数，0.025 = 2.5%）；baseline_only / unavailable 可为 None
    - confidence:  置信度 0-1；baseline_only / unavailable 可为 None
    - suggestion:  改进建议（30 字内，文案本身）；unavailable 必填原因
    - source:      数据来源（e.g. "ctr_predictor_adapter/baseline_lookup"）
    - error:       错误描述（仅 unavailable / 异常路径用）
    - baseline_ctr: 历史基准 CTR（任何态都可能存在，便于 UI 对比展示）
    - time_multiplier: 时段系数（任何态都可能存在）
    """
    result_type: str
    pred_ctr: Optional[float] = None
    confidence: Optional[float] = None
    suggestion: str = ""
    source: str = ""
    error: Optional[str] = None
    baseline_ctr: Optional[float] = None
    time_multiplier: Optional[float] = None

    def __post_init__(self):
        # 四态校验（防止 UI 层误传 demo / unavailable 又标"预测准确率 77%"）
        if self.result_type not in VALID_RESULT_TYPES:
            raise ValueError(
                f"result_type must be one of {VALID_RESULT_TYPES}, got {self.result_type!r}"
            )
        # unavailable 必须有 error
        if self.result_type == "unavailable" and not self.error:
            self.error = "无有效结果"
        # pred_ctr 范围校验
        if self.pred_ctr is not None and not (0 <= self.pred_ctr <= 1):
            raise ValueError(f"pred_ctr must be in [0, 1], got {self.pred_ctr}")
        # confidence 范围校验
        if self.confidence is not None and not (0 <= self.confidence <= 1):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

    # ── 工厂方法（便于测试和 UI 构造） ─────────────────────────────────
    @classmethod
    def baseline_only(
        cls, baseline_ctr: Optional[float], suggestion: str = "无 LLM，仅历史基准",
        time_multiplier: Optional[float] = None, source: str = "ctr_predictor_adapter/baseline_lookup",
    ) -> "PredictionResult":
        return cls(
            result_type="baseline_only",
            pred_ctr=baseline_ctr,
            confidence=None,
            suggestion=suggestion,
            source=source,
            baseline_ctr=baseline_ctr,
            time_multiplier=time_multiplier,
        )

    @classmethod
    def model_prediction(
        cls, pred_ctr: float, confidence: float, suggestion: str,
        baseline_ctr: Optional[float] = None, time_multiplier: Optional[float] = None,
        source: str = "ctr_predictor_adapter/llm",
    ) -> "PredictionResult":
        return cls(
            result_type="model_prediction",
            pred_ctr=pred_ctr,
            confidence=confidence,
            suggestion=suggestion,
            source=source,
            baseline_ctr=baseline_ctr,
            time_multiplier=time_multiplier,
        )

    @classmethod
    def demo(
        cls, pred_ctr: float, confidence: float = 0.5, suggestion: str = "演示数据",
        baseline_ctr: Optional[float] = None, time_multiplier: Optional[float] = None,
        source: str = "ctr_predictor_adapter/demo",
    ) -> "PredictionResult":
        return cls(
            result_type="demo",
            pred_ctr=pred_ctr,
            confidence=confidence,
            suggestion=suggestion,
            source=source,
            baseline_ctr=baseline_ctr,
            time_multiplier=time_multiplier,
        )

    @classmethod
    def unavailable(cls, error: str, suggestion: str = "无有效结果") -> "PredictionResult":
        return cls(
            result_type="unavailable",
            pred_ctr=None,
            confidence=None,
            suggestion=suggestion,
            source="ctr_predictor_adapter/none",
            error=error,
        )

    # ── 序列化 ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def has_ctr(self) -> bool:
        """是否可用于聚合计算（unavailable 不可用）。"""
        return self.result_type in ("model_prediction", "baseline_only", "demo") \
            and self.pred_ctr is not None

    @property
    def is_demo(self) -> bool:
        return self.result_type == "demo"

    @property
    def label(self) -> str:
        """UI 展示标签。"""
        return {
            "model_prediction": "LLM 预测",
            "baseline_only":    "历史基准",
            "demo":             "演示数据",
            "unavailable":      "无结果",
        }.get(self.result_type, self.result_type)


# ── 任务输入（PRD §6.2 左栏 11 字段）─────────────────────────────────
TARGET_AUDIENCE = ("常规大盘", "新品兴趣人群", "近期活跃用户", "沉默召回人群", "高价值会员")
OBJECTIVES      = ("通用", "建立认知", "提升点击", "促进领券", "促进下单", "用户召回", "新品种草")  # Phase 28：可选字段加"通用"首位，prompt 拼装时跳过
CHANNELS        = ("APP Push", "企微1v1", "短信", "微信小程序订阅消息")  # Phase 12 #8/#9 用户拍板：删"站内信" + 加"微信小程序订阅消息" + "企微 1v1" → "企微1v1"（跟数据源连写）
STAGES          = ("通用", "活动预热", "活动上线", "活动爆发", "活动收尾")  # Phase 28：stage 改可选
SCENES          = ("通用", "早餐", "午餐", "下午茶", "晚餐", "夜宵", "周末聚会", "其他")  # Phase 28
TONES           = ("直接利益型", "场景种草型", "品牌互动型", "行动号召型")  # tone 仍必填，不加"通用"
ACTIONS         = ("通用", "点击", "领券", "下单", "回流", "到店", "查看详情")  # Phase 28
PLAN_TYPES      = ("通用", "AARRPlan", "常规Plan", "未知")  # Phase 28
COUPON_FLAGS    = ("通用", "是", "否", "未知")  # Phase 28


@dataclass
class TaskInput:
    """左栏"定义经营任务"输入（PRD §6.2）。

    必填 4 项：audience / channel / stage / tone
              ↑ scene 从必填改为选填（Phase 12 #10 用户拍板 2026-08-27：
                场景由文案内容推断；form SCENES 字段保留但允许空）
    可选启用 2 项（Phase A.1 · 2026-08-28）：product_category / benefit_type
              ↑ 这两个从原 product_benefit 拆出来，前端 selectbox + 自定义输入
                不参与 CTR baseline（用户拍板：直接 baseline 数据稀疏）
                仅影响：①AI 文案生成 prompt 注入 ②产品词典 jieba 词条扩展
    可选灰态 1 项（A.2 待开发）：objective
              ↑ 前端 disabled，后端空字符串兜底，
                generation_service 在缺失时走 Demo 默认占位，
                不报错、不阻塞。等 UI 重构 + L2 之后再启动 A.2（PRD §26 #2）。
    可选 5 项：expected_action / plan_type / coupon / planned_send_date / scene
    用券双字段（Phase 12 #11 用户拍板）：
      - coupon          "实际是否用券"（form 字段，plan 维度）
      - text_has_coupon "标题正文是否带券"（文案推断，文案粒度）
    附加：extra_requirements

    字段名沿用 PRD §9.1 输入 schema（snake_case），便于未来落库 JSON。
    """
    audience: str
    channel: str
    stage: str
    tone: str
    expected_action: str = ""
    plan_type: str = "未知"
    coupon: str = "未知"           # "实际是否用券"（form 字段，plan 维度）
    planned_send_date: Optional[str] = None   # 工作日类型标签："工作日"|"非工作日"（Phase 11 · 2026-08-27 用户简化拍板）。
                                              # 历史：v3.1 之前是 ISO 日期字符串；Handoff §6.2 #12 用户口径
                                              #   不要日期选择器，改为 selectbox 2 值。
                                              # 透传：ctr_prediction_service._build_row 写到 row["工作日类型"]，
                                              #   参与 baseline_lookup 工作日维度查找（Phase 14 修复后）。
                                              # 字段名保留：避免破坏 records.db 老 schema 兼容。
    scene: str = ""                # Phase 12 #10 用户拍板：scene 从必填改为选填
    extra_requirements: str = ""
    # Phase A.1（2026-08-28）：产品权益 2 字段（启用，原 product_benefit 拆分）
    # 数据源：core/product_benefit.load_product_benefit()（10 产品 + 8 权益 + 自定义）
    product_category: str = ""
    benefit_type: str = ""
    # Demo 阶段灰态字段必须在尾部（dataclass 要求：no-default 字段在前）
    objective: str = ""           # A.2 待开发：前端 disabled，后端空串兜底
    text_has_coupon: str = ""     # Phase 12 #11 用户拍板："标题正文是否带券"（文案推断）

    REQUIRED_FIELDS: tuple = (
        "audience", "channel", "tone",  # Phase 28：stage 改可选，仅 3 项必填（人群/渠道/语气）
    )

    def __post_init__(self):
        # 必填校验（页面层也校验，这里兜底）
        for f in self.REQUIRED_FIELDS:
            v = getattr(self, f)
            if not v or (isinstance(v, str) and not v.strip()):
                raise ValueError(f"TaskInput 必填字段 {f} 为空")
        # 枚举校验（不强制——给默认值兜底，但给 warning 即可，不抛错便于 demo 跑通）
        # PRD §26 待业务确认项，宽松处理：不在枚举内的值原样保留，UI 层可能显示为"自定义"

    @property
    def is_complete(self) -> bool:
        return all(bool(getattr(self, f)) for f in self.REQUIRED_FIELDS)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_form(cls, form_data: dict) -> "TaskInput":
        """从 st.session_state / form dict 构造（缺失字段填空串不抛错）。"""
        return cls(
            audience=form_data.get("audience") or "",
            channel=form_data.get("channel") or "",
            stage=form_data.get("stage") or "",
            tone=form_data.get("tone") or "",
            expected_action=form_data.get("expected_action") or "",
            plan_type=form_data.get("plan_type") or "未知",
            coupon=form_data.get("coupon") or "未知",
            planned_send_date=form_data.get("planned_send_date") or None,
            scene=form_data.get("scene") or "",
            extra_requirements=(form_data.get("extra_requirements") or "").strip(),
            product_category=(form_data.get("product_category") or "").strip(),
            benefit_type=(form_data.get("benefit_type") or "").strip(),
            objective=form_data.get("objective") or "",
            text_has_coupon=form_data.get("text_has_coupon") or "",
        )


# ── 候选（PRD §7 / §9.2 输出 schema）───────────────────────────────────
CANDIDATE_STRATEGIES = ("A_核心利益直给", "B_消费场景切入", "C_行动号召强化")


@dataclass
class Candidate:
    """中栏候选（PRD §7.2 / §9.2）。

    字段语义：
    - id: "A" / "B" / "C"
    - strategy: A_核心利益直给 / B_消费场景切入 / C_行动号召强化
    - title / body: AI 原文（业务方看后自行决定是否采纳；不暴露人工编辑）
    - reason: 生成理由（PRD §9.2）
    - risk_flags: 风险标记列表（PRD §9.2）
    - used_input_fields: 使用了哪些 TaskInput 字段
    - provider / model / prompt_version: 生成溯源（PRD §10.3 Prompt 版本管理）

    Phase 13 · 2026-08-27 用户拍板：
      - 工具定位 = CTR 评估辅助决策，**不是选文案工作流**（业务方通常自己导入生产系统）
      - 删除 title_edited / body_edited（人工编辑）；UI 不再暴露"编辑候选 / 恢复 AI 原文 / 保存当前选择"
      - 业务方看 3 条候选 + CTR 估计 → 自己决定采纳哪条 → 不入库（records.db 留作 train_dimension_weights.py 训练用，UI 不调用）
    """
    id: str
    strategy: str
    title: str
    body: str
    reason: str = ""
    risk_flags: list = field(default_factory=list)
    used_input_fields: list = field(default_factory=list)
    provider: str = "demo"
    model: str = ""
    prompt_version: str = "v1.0"

    def __post_init__(self):
        if self.id not in ("A", "B", "C"):
            raise ValueError(f"Candidate.id must be A/B/C, got {self.id!r}")
        # body 必须非空；title 允许为空（短信 / 企微 1v1 无独立标题，PRD §8.2）
        if not self.body.strip():
            raise ValueError("Candidate.body 不能为空")

    def to_dict(self) -> dict:
        return asdict(self)


# ── 规则检查结果（PRD §8.4 绿/黄/红 + §11 规则引擎）────────────────────
SEVERITY_PASS = "pass"
SEVERITY_WARN = "warn"
SEVERITY_FAIL = "fail"
VALID_SEVERITIES = (SEVERITY_PASS, SEVERITY_WARN, SEVERITY_FAIL)


@dataclass
class RuleItem:
    """单条规则结果。"""
    category: str           # 字数 / 必带词 / 禁词 / 风险词 / 标点 / ...
    severity: str           # pass / warn / fail
    message: str            # 给用户看的中文短句
    suggestion: str = ""    # 改进建议


@dataclass
class RuleResult:
    """一组规则检查的聚合结果（一条 Candidate 对应一个）。"""
    items: list = field(default_factory=list)

    @property
    def status(self) -> str:
        """聚合状态：任意 fail → fail；任意 warn → warn；全 pass → pass。"""
        severities = [it.severity for it in self.items]
        if SEVERITY_FAIL in severities:
            return SEVERITY_FAIL
        if SEVERITY_WARN in severities:
            return SEVERITY_WARN
        return SEVERITY_PASS

    @property
    def has_blocking(self) -> bool:
        """PRD §8.5：存在阻断项（fail）不得推荐正式使用。"""
        return any(it.severity == SEVERITY_FAIL for it in self.items)

    @property
    def passes(self) -> list:
        return [it for it in self.items if it.severity == SEVERITY_PASS]

    @property
    def warns(self) -> list:
        return [it for it in self.items if it.severity == SEVERITY_WARN]

    @property
    def fails(self) -> list:
        return [it for it in self.items if it.severity == SEVERITY_FAIL]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "items": [asdict(it) for it in self.items],
            "passes": [asdict(it) for it in self.passes],
            "warns": [asdict(it) for it in self.warns],
            "fails": [asdict(it) for it in self.fails],
            "has_blocking": self.has_blocking,
        }


# ── 生成记录（repositories/sqlite_repository 入库结构）────────────────
@dataclass
class GenerationRecord:
    """完整保存一次"任务输入 → 生成 → 选择"全过程。"""
    task: TaskInput
    candidates: list            # list[Candidate]
    selected_id: str            # "A" / "B" / "C"
    rule_results: list = field(default_factory=list)   # list[RuleResult] 与 candidates 对齐
    ctr_results: list = field(default_factory=list)    # list[PredictionResult]
    similar_summary: dict = field(default_factory=dict)  # {"count": N, "avg_ctr": ..., "top_terms": [...]}
    created_at: str = ""        # ISO 时间戳
    signature: str = ""         # 任务指纹（PRD §回流闭环）：人群-阶段-场景-渠道-字数-必带词

    def to_row(self) -> dict:
        """转 SQLite 入库 dict。"""
        import json
        return {
            "task_json":           json.dumps(self.task.to_dict(), ensure_ascii=False),
            "candidates_json":     json.dumps([c.to_dict() for c in self.candidates], ensure_ascii=False),
            "rule_results_json":   json.dumps([r.to_dict() for r in self.rule_results], ensure_ascii=False),
            "ctr_results_json":    json.dumps(
                [c.to_dict() if hasattr(c, "to_dict") else c for c in self.ctr_results],
                ensure_ascii=False,
            ),
            "similar_summary_json": json.dumps(self.similar_summary, ensure_ascii=False),
            "selected_id":         self.selected_id,
            "created_at":          self.created_at,
            "signature":           self.signature,
        }


def task_signature(task: TaskInput, candidates: Optional[list] = None,
                   selected_id: str = "") -> str:
    """任务指纹：用于回流数据 join 锚点（docs/feedback-ctr.md §2.1）。

    字段：channel / coupon / plan_type / audience / stage / scene +
          选中候选的 title_len 桶 + body_len 桶。
    用 SHA1 截前 12 位（不变即可逆少，但回流 join 够用）。
    """
    import hashlib

    # 字数桶
    title_len_bucket = "na"
    body_len_bucket = "na"
    if candidates and selected_id:
        sel = next((c for c in candidates if getattr(c, "id", None) == selected_id), None)
        if sel is not None:
            tl = len(getattr(sel, "title", "") or "")
            bl = len(getattr(sel, "body", "") or "")
            title_len_bucket = f"{(tl // 5) * 5}"  # 0/5/10/15/20...
            body_len_bucket = f"{(bl // 10) * 10}"

    raw = (
        f"{task.channel}|{task.coupon}|{task.plan_type}|{task.audience}|"
        f"{task.stage}|{task.scene}|{title_len_bucket}|{body_len_bucket}"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]