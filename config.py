"""工具注册表。改这里就能加/删工具，不用碰其他代码。"""

import os

# 工具 key → SVG icon key 映射（v3.1：emoji/unicode → lucide SVG）
# 后端 /api/tools/search 和 Jinja filter 都读这个；前端 JS 用 ICON_KEY 同源
ICON_MAP = {
    "content-rank": "grid-3x3",
    "reach-trend": "trending-up",
    "copy-analyzer": "pencil",
    "ctr-predictor": "activity",
    "studio": "sparkles",
    "insights": "bar-chart-3",
}

TOOLS = {
    "content-rank": {
        "title": "内容排行",
        "subtitle": "内容排行榜 · 多维度评分",
        "service": "ideon.service",
        "path_prefix": "/content-rank/",
    },
    "reach-trend": {
        "title": "触达趋势",
        "subtitle": "CNN 多渠道触达分析",
        "service": "reach-trend.service",
        "path_prefix": "/reach-trend/",
    },
    "copy-analyzer": {
        "title": "文案解析",
        "subtitle": "企微 1v1 文案 AI 诊断",
        "service": "copy-analyzer.service",
        "path_prefix": "/copy-analyzer/",
    },
    "ctr-predictor": {
        "title": "CTR 预测",
        "subtitle": "推送内容点击率预测",
        "service": "ctr-predictor.service",
        "path_prefix": "/ctr-predictor/",
    },
    "library": {
        "title": "图书馆",
        "subtitle": "日报归档平台",
        "service": "traffic-library.service",
        "path_prefix": "/library/",
        # always-on：不参与闲置回收（idle_checker 跳过）
        "persistent": True,
        # 页面不展示（路由页仅保留内容相关工具）
        "hidden": True,
        # 本地开发模式（无 systemctl 时生效）
        "dev_cmd": ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002"],
        "dev_cwd": r"C:\Users\a952462\OneDrive - ATOS\桌面\mcd-report-archive",
        "dev_port": 8002,
    },
    # v3.4：从 mcd-ai-content-platform/web 迁过来，sub-app include_router
    # type=internal：新标签页打开 path_prefix，走 portal 自身路由
    "studio": {
        "title": "内容工坊",
        "subtitle": "LLM 生成 + CTR 预测 + 规则校验",
        "type": "internal",
        "service": "",
        "path_prefix": "/studio",
    },
    "insights": {
        "title": "历史洞察",
        "subtitle": "Plan 排行 · 高低表现词 · 每日趋势",
        "type": "internal",
        "service": "",
        "path_prefix": "/insights",
    },
}

IDLE_TIMEOUT_MINUTES = int(os.environ.get("IDLE_TIMEOUT_MINUTES", "30"))
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "60"))
DB_PATH = os.environ.get("PORTAL_DB_PATH", "/opt/ideon/portal/portal.db")
PORTAL_PORT = int(os.environ.get("PORTAL_PORT", "8001"))
# v3.1：状态探活缓存 TTL（前端 setInterval 5000ms 对齐，改这里同步改前端）
STATUS_CACHE_TTL = float(os.environ.get("STATUS_CACHE_TTL", "5"))