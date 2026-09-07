# -*- coding: utf-8 -*-
r"""
services/analytics/ — 历史洞察分析（PRD §4.4 04 历史洞察页）

4 个分析（mcd-copy-analyzer 没实现，从零实现）：
- high_effort_plans:  高效 plan 排行（按 plan 加权 CTR 排前 N）
- similarity:         相似 plan 检索（TF-IDF + 余弦相似度）
- daily_trend:        每日趋势（按日聚合 + 周环比）
- owner_compare:      Owner 对比（人均 Plan + 加权 CTR + 字数 + 高效词命中率）

口径（CLAUDE.md §9）：
- CTR 一律 plan 加权：sum(点击) / sum(触达成功) * 100
- 默认 min_plans=3（plan<5 加预警）
- 样本量透明：每词对比显示 n_plans + n_records + 触达数

红线：
- 纯函数（不依赖 st.session_state）
- 必备列：触达成功 / 点击人次 / 发送日期 / owner
- Plan ID 列缺失时降级为记录级聚合（不抛错，给空结果 + warning）
"""