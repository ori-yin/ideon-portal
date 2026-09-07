# -*- coding: utf-8 -*-
r"""
services/ — 业务层（CLAUDE.md §3）

- data_loader:       抽自 mcd-copy-analyzer/data.py 的纯函数
- text_analyzer:     抽自 mcd-copy-analyzer/analyzer.py 的纯函数（替 @st.cache_data）
- rule_engine:       规则检查（PRD §11）
- generation_service: 经营任务 -> 3 条候选（PRD §10）
- copy_analysis_service: 文案诊断 / 词频分析（PRD §8）
- ctr_prediction_service: CTR Adapter 包装（Phase 1b CTRPredictionAdapter 的薄壳）
- similarity_service: TF-IDF 找相似历史 Plan
- record_service:    SQLite 保存

红线：
- 业务层不得依赖 st.session_state（应通过参数传递）
- 不得 import openai/anthropic（统一走 core/llm_gateway）
"""