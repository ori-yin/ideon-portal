"""工具注册表。改这里就能加/删工具，不用碰其他代码。"""

import os

TOOLS = {
    "content-rank": {
        "title": "内容排行",
        "subtitle": "内容排行榜 · 多维度评分",
        "service": "ideon.service",
        "path_prefix": "/content-rank/",
    },
    "copy-analyzer": {
        "title": "文案解析",
        "subtitle": "企微 1v1 文案 AI 诊断",
        "service": "copy-analyzer.service",
        "path_prefix": "/copy-analyzer/",
    },
    "reach-trend": {
        "title": "触达趋势",
        "subtitle": "CNN 多渠道触达分析",
        "service": "reach-trend.service",
        "path_prefix": "/reach-trend/",
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
        # 本地开发模式（无 systemctl 时生效）
        "dev_cmd": ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002"],
        "dev_cwd": r"C:\Users\a952462\OneDrive - ATOS\桌面\mcd-report-archive",
        "dev_port": 8002,
    },
}

IDLE_TIMEOUT_MINUTES = int(os.environ.get("IDLE_TIMEOUT_MINUTES", "30"))
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "60"))
DB_PATH = os.environ.get("PORTAL_DB_PATH", "/opt/ideon/portal/portal.db")
PORTAL_PORT = int(os.environ.get("PORTAL_PORT", "8001"))