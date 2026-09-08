"""ideon 中台 / 路由页。按需启停 + 闲置超时。"""

import asyncio
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sqlite3

from config import TOOLS, ICON_MAP, IDLE_TIMEOUT_MINUTES, CHECK_INTERVAL_SECONDS, DB_PATH, PORTAL_PORT, STATUS_CACHE_TTL
from llm_config import load_config, save_config, get_status, probe_llm, LLM_PROVIDERS

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# v3.0: 8530 在独立端口 8530 上跑自己的 app，portal 不挂载它。portal 只生成跳转链接。
# 8530 进程：cd C:\ideon\mcd-ai-content-platform\web && uvicorn app:app --port 8530
# portal 这边：首页工具卡用绝对 URL http://localhost:8530/... target=_blank 新开标签
# 这里不做任何导入，避免 portal/8530 之间 sys.path 互相污染

# v3.1：SVG icon 字符串（Jinja filter 渲染工具卡图标用）
# 路径来自 lucide 库 + mcd_ai_content_platform_ui_v3.html，保持 viewBox="0 0 24 24"
ICON_SVG = {
    "home": '<svg viewBox="0 0 24 24" class="icon"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h5v-6h4v6h5V9.5"/></svg>',
    "pencil": '<svg viewBox="0 0 24 24" class="icon"><path d="m4 20 4.5-1 10-10a2.8 2.8 0 0 0-4-4l-10 10Z"/><path d="m13 6 5 5"/></svg>',
    "shield-check": '<svg viewBox="0 0 24 24" class="icon"><path d="M12 3 4 6v5c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V6Z"/><path d="m9 12 2 2 4-4"/></svg>',
    "list-checks": '<svg viewBox="0 0 24 24" class="icon"><path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3" cy="6" r="1"/><circle cx="3" cy="12" r="1"/><circle cx="3" cy="18" r="1"/></svg>',
    "bar-chart-3": '<svg viewBox="0 0 24 24" class="icon"><path d="M4 20V10M9 20V4M14 20v-7M19 20V7"/></svg>',
    "refresh-ccw": '<svg viewBox="0 0 24 24" class="icon"><path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v6h-6"/></svg>',
    "settings": '<svg viewBox="0 0 24 24" class="icon"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>',
    "trending-up": '<svg viewBox="0 0 24 24" class="icon"><path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M17 7h5v5"/></svg>',
    "grid-3x3": '<svg viewBox="0 0 24 24" class="icon"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>',
    "activity": '<svg viewBox="0 0 24 24" class="icon"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
    "bell": '<svg viewBox="0 0 24 24" class="icon"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>',
    "lightbulb": '<svg viewBox="0 0 24 24" class="icon"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>',
    "chevron-down": '<svg viewBox="0 0 24 24" class="icon"><path d="m6 9 6 6 6-6"/></svg>',
    "search": '<svg viewBox="0 0 24 24" class="icon"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
    "wand-sparkles": '<svg viewBox="0 0 24 24" class="icon"><path d="m15 4 3 3"/><path d="M9 13 4 18"/><path d="m15 4-3 3 6 6 3-3z"/><path d="m19 9 1 1"/><path d="m3 19 2 2"/><path d="m13 4-1 1"/><path d="m21 16-1 1"/><path d="m5 6 1 1"/></svg>',
    "sparkles": '<svg viewBox="0 0 24 24" class="icon"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/></svg>',
}


def _icon_svg(icon_key: str) -> str:
    """Jinja filter: SVG icon key → SVG 字符串。模板 `{{ 'pencil' | icon_svg | safe }}`。

    build_cards() 已把 tool_key → icon_key resolve 成 `icon` 字段，
    模板直接读 `t.icon` 即可，不需要再传 tool_key。
    """
    return ICON_SVG.get(icon_key or "", ICON_SVG["grid-3x3"])


templates.env.filters["icon_svg"] = _icon_svg


def _tool_target(tool_key: str, *, via_loading: bool = False) -> str:
    """跳转 URL：v3.5 后 web_content sub-app 已删，所有外部工具走中转页触发启停 + 探活，
    最后给浏览器跳绝对 URL（dev 模式 dev_port / VM 模式 service_port）。
    via_loading=True 时仅返回中转页 /open/{key}（不直接跳终点）。
    """
    tool = TOOLS[tool_key]
    # internal 类型：portal 自身页面，直接走 path_prefix
    if tool.get("type") == "internal":
        return tool["path_prefix"]
    if via_loading:
        return f"/open/{tool_key}"
    # 绝对 URL：dev 模式走 dev_port，VM 模式走 service_port（端口从 config.TOOLS 读）
    port = tool.get("dev_port") if not HAS_SYSTEMCTL else tool.get("service_port")
    if port:
        return f"http://127.0.0.1:{port}{tool['path_prefix']}"
    return tool["path_prefix"]


# 状态缓存：api_status / api_summary / api_tools/search / build_cards / idle_checker 共享
# 防 N+1 探活；TTL 在 config.py（前端 setInterval 同步）
_STATUS_CACHE: dict[str, tuple[float, str]] = {}

HAS_SYSTEMCTL = shutil.which("systemctl") is not None
# dev_procs: tool_key -> (Popen, log_file)；stop 时一起关，防 FD 泄漏
_dev_procs: dict[str, tuple[subprocess.Popen, "object"]] = {}


def _visible_tools() -> dict:
    """过滤 hidden 工具（library 永远不进 UI / API 响应）。"""
    return {k: t for k, t in TOOLS.items() if not t.get("hidden")}


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """探测端口是否在监听。"""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:
        return False


# ---------- SQLite: 访问日志 ----------
def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS access_log (
                tool_key TEXT PRIMARY KEY,
                last_access_at TEXT NOT NULL,
                total_opens INTEGER DEFAULT 0
            )
        """)
        conn.commit()


def get_last_access(tool_key: str):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT last_access_at FROM access_log WHERE tool_key = ?",
                (tool_key,),
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None
    except Exception:
        return None


def touch_access(tool_key: str):
    try:
        now = datetime.now().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO access_log (tool_key, last_access_at, total_opens)
                VALUES (?, ?, 1)
                ON CONFLICT(tool_key) DO UPDATE SET
                    last_access_at = excluded.last_access_at,
                    total_opens = total_opens + 1
                """,
                (tool_key, now),
            )
            conn.commit()
    except Exception:
        pass


# ---------- systemd 接口 / 本地开发模式 ----------
def _tool_for_service(name: str) -> tuple[str, dict] | None:
    for k, t in TOOLS.items():
        if t["service"] == name:
            return (k, t)
    return None


def service_exists(name: str) -> bool:
    if HAS_SYSTEMCTL:
        try:
            r = subprocess.run(
                ["systemctl", "cat", name], capture_output=True, text=True, timeout=5
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
    # 本地开发模式：有 dev_cmd 就算"已部署"
    pair = _tool_for_service(name)
    return bool(pair and "dev_cmd" in pair[1])


def get_service_status(name: str) -> str:
    """带缓存：api_status / api_summary / api_tools/search / build_cards / idle_checker 共享。

    缓存命中直接返回；miss 时跑探活（最多 5 tool 同时 miss，5s 内仅 1 次 N+1）。
    不用锁：subprocess.run 单 tool 5s timeout，FastAPI 单 worker 下不会卡死 event loop
    （open_tool/loading_tool 显式用 asyncio.to_thread 包装）。
    """
    hit = _STATUS_CACHE.get(name)
    if hit and time.time() - hit[0] < STATUS_CACHE_TTL:
        return hit[1]
    result = _probe_service_status(name)
    _STATUS_CACHE[name] = (time.time(), result)
    return result


def _probe_service_status(name: str) -> str:
    if HAS_SYSTEMCTL:
        try:
            if not service_exists(name):
                return "not_installed"
            r = subprocess.run(
                ["systemctl", "is-active", name], capture_output=True, text=True, timeout=5
            )
            state = r.stdout.strip()
            if not state:
                return "unknown"
            if state == "active":
                return "running"
            if state == "failed":
                return "failed"
            if state in ("inactive", "unknown"):
                en = subprocess.run(
                    ["systemctl", "is-enabled", name], capture_output=True, text=True, timeout=5
                ).stdout.strip()
                return "stopped" if en == "enabled" else "failed"
            return "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "unknown"
        except Exception:
            return "unknown"
    # 本地开发模式：探测端口（永远不会进 systemd 异常分支）
    pair = _tool_for_service(name)
    if pair and "dev_port" in pair[1]:
        return "running" if is_port_open(pair[1]["dev_port"]) else "stopped"
    return "not_installed"


def start_dev(tool_key: str) -> tuple[bool, str]:
    """本地开发模式启动子进程（同步，不等端口）。"""
    tool = TOOLS[tool_key]
    port = tool.get("dev_port")
    if port and is_port_open(port):
        return True, "已在运行"
    cmd = tool.get("dev_cmd")
    cwd = tool.get("dev_cwd")
    if not cmd:
        return False, "未配置本地启动命令"
    # python / {python} 占位符 → 当前解释器（保证用 portal venv 的 uvicorn）
    cmd = [sys.executable if c in ("python", "{python}", "python3") else c for c in cmd]
    try:
        kwargs: dict = {"cwd": cwd}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        # 用 context manager 关 FD；存到 _dev_procs 给 stop_dev 用
        log_file = open(log_dir / f"{tool_key}.log", "ab")
        try:
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, **kwargs)
            _dev_procs[tool_key] = (proc, log_file)
        except Exception:
            log_file.close()
            raise
        time.sleep(0.3)  # 短延迟让进程有失败机会
        if proc.poll() is not None:
            stop_dev(tool_key)  # 收尾关 log_file
            return False, f"进程立即退出，退出码 {proc.returncode}"
        return True, "已启动，等待端口"
    except Exception as e:
        return False, f"启动失败: {e}"


def stop_dev(tool_key: str) -> tuple[bool, str]:
    entry = _dev_procs.pop(tool_key, None)
    if not entry:
        return True, "未在追踪"
    proc, log_file = entry
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    except Exception as e:
        return False, str(e)
    finally:
        try:
            log_file.close()
        except Exception:
            pass
    return True, "已停止"


def systemctl_action(name: str, action: str):
    if not HAS_SYSTEMCTL:
        # 本地开发模式
        pair = _tool_for_service(name)
        if not pair:
            return False, "未知工具"
        tool_key, tool = pair
        if "dev_cmd" not in tool:
            return False, "未配置本地启动命令（仅 VM 部署）"
        if action == "start":
            return start_dev(tool_key)
        if action == "stop":
            return stop_dev(tool_key)
        if action == "restart":
            stop_dev(tool_key)
            return start_dev(tool_key)
        return False, f"未知动作: {action}"
    try:
        r = subprocess.run(
            ["systemctl", action, name], capture_output=True, text=True, timeout=30
        )
        return (r.returncode == 0, (r.stderr or r.stdout or "unknown").strip())
    except subprocess.TimeoutExpired:
        return (False, "timeout")
    except FileNotFoundError:
        return (False, "systemctl not available (非 Linux 环境)")
    except Exception as e:
        return (False, str(e))


# ---------- 应用 ----------
def get_total_opens() -> int:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT COALESCE(SUM(total_opens), 0) FROM access_log").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def relative_time(dt) -> str:
    """把 datetime 转成「N 分钟前 / N 小时前 / N 天前 / 刚刚」。"""
    delta = datetime.now() - dt
    if delta.days > 0:
        return f"{delta.days} 天前"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours} 小时前"
    minutes = delta.seconds // 60
    if minutes > 0:
        return f"{minutes} 分钟前"
    return "刚刚"


def build_cards():
    """返回 (cards, hidden_count)。hidden_count 让模板不需要 +1 magic number。

    v2.2：internal 类型 status 强制 running，external_blank=false；模板据此决定 target=_blank
    """
    visible = _visible_tools()
    cards = [
        {
            "key": k,
            "title": t["title"],
            "subtitle": t["subtitle"],
            "status": "running" if t.get("type") == "internal" else get_service_status(t["service"]),
            "last_access": get_last_access(k),
            "icon": ICON_MAP.get(k, "grid-3x3"),
            "external_blank": bool(t.get("external_blank")) or t.get("type") == "internal",
            "target_url": _tool_target(k, via_loading=t.get("type") != "internal"),
        }
        for k, t in visible.items()
    ]
    hidden_count = len(TOOLS) - len(visible)
    return cards, hidden_count


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(idle_checker())
    try:
        yield
    finally:
        task.cancel()
        # 退出时清理本地开发模式子进程
        for tool_key in list(_dev_procs.keys()):
            stop_dev(tool_key)


app = FastAPI(title="ideon 中台", lifespan=lifespan)

# v2.2: 把 templates / ICON_SVG 挂在 app.state，tool_routes 用
app.state.templates = templates
app.state.ICON_SVG = ICON_SVG

# 静态资源（loading.gif 等）
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# v3.0: 8530 跑在独立端口，portal 不挂载。跳转链接由 config.py + _tool_target 走绝对 URL。


@app.get("/")
async def index(request: Request):
    need = request.query_params.get("need_start")
    err = request.query_params.get("err")
    need_title = (TOOLS.get(need) or {}).get("title", "") if need else ""
    cards, hidden_count = build_cards()
    status = get_status()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "cards": cards,
            "hidden_count": hidden_count,
            "ICON_SVG": ICON_SVG,
            "idle_timeout": IDLE_TIMEOUT_MINUTES,
            "need_start": need,
            "need_start_title": need_title,
            "err": err,
            "llm_configured": status["configured"],
            "llm_model": status["model"],
        },
    )


@app.get("/api/status")
async def api_status():
    out = {}
    for k, t in _visible_tools().items():
        try:
            la = get_last_access(k)
            # v2.2 internal 类型永远 running，省掉 systemd 探活
            if t.get("type") == "internal":
                out[k] = {"status": "running", "last_access": la.isoformat() if la else None}
                continue
            out[k] = {
                "status": get_service_status(t["service"]),
                "last_access": la.isoformat() if la else None,
            }
        except Exception as e:
            out[k] = {"status": "error", "last_access": None, "error": str(e)}
    return out


@app.post("/api/start/{tool_key}")
async def api_start(tool_key: str):
    if tool_key not in TOOLS:
        raise HTTPException(404, "unknown tool")
    svc = TOOLS[tool_key]["service"]
    if not service_exists(svc):
        raise HTTPException(404, f"{svc} 未部署")
    ok, msg = systemctl_action(svc, "start")
    if not ok:
        raise HTTPException(500, f"start failed: {msg}")
    _STATUS_CACHE.pop(svc, None)  # action 后失效缓存，避免 5s 内显示 stale 状态
    return {"ok": True, "service": svc}


@app.post("/api/stop/{tool_key}")
async def api_stop(tool_key: str):
    if tool_key not in TOOLS:
        raise HTTPException(404, "unknown tool")
    svc = TOOLS[tool_key]["service"]
    ok, msg = systemctl_action(svc, "stop")
    if not ok:
        raise HTTPException(500, f"stop failed: {msg}")
    _STATUS_CACHE.pop(svc, None)
    return {"ok": True, "service": svc}


@app.post("/api/restart/{tool_key}")
async def api_restart(tool_key: str):
    if tool_key not in TOOLS:
        raise HTTPException(404, "unknown tool")
    svc = TOOLS[tool_key]["service"]
    if not service_exists(svc):
        raise HTTPException(404, f"{svc} 未部署")
    ok, msg = systemctl_action(svc, "restart")
    if not ok:
        raise HTTPException(500, f"restart failed: {msg}")
    _STATUS_CACHE.pop(svc, None)
    return {"ok": True, "service": svc}


@app.get("/api/summary")
async def api_summary():
    """汇总数据：在线工具数、总访问次数、闲置超时"""
    running_count = sum(
        1 for t in TOOLS.values() if get_service_status(t["service"]) == "running"
    )
    return {
        "total_tools": len(TOOLS),
        "running_count": running_count,
        "total_opens": get_total_opens(),
        "idle_timeout_minutes": IDLE_TIMEOUT_MINUTES,
        "checked_at": datetime.now().isoformat(),
    }


@app.get("/api/recent")
async def api_recent(limit: int = 10):
    """最近访问事件：基于 access_log.last_access_at 倒序，过滤 hidden 工具。"""
    items = []
    for k, t in _visible_tools().items():
        la = get_last_access(k)
        if la:
            items.append({
                "tool_key": k,
                "title": t["title"],
                "icon": ICON_MAP.get(k, "grid-3x3"),
                "last_access_at": la.isoformat(),
                "relative": relative_time(la),
            })
    items.sort(key=lambda x: x["last_access_at"], reverse=True)
    return items[:limit]


@app.get("/api/tools/search")
async def api_tools_search(q: str = "", limit: int = 10):
    """工具搜索/列表（v3.1 ⌘K Command Palette 用）。

    模糊匹配 key/title/subtitle；跳过 hidden 工具。
    q 超长截断到 50，limit clamp 到 1-20。
    """
    try:
        limit = max(1, min(int(limit or 10), 20))
    except (TypeError, ValueError):
        limit = 10
    q_raw = (q or "")[:50]
    q_low = q_raw.lower()
    items = []
    for k, t in TOOLS.items():
        if t.get("hidden"):           # library 不进搜索
            continue
        title = t["title"]
        subtitle = t.get("subtitle", "")
        score = 0
        if q_low:
            if q_low in title.lower():
                score = max(score, 100 - len(title))
            if q_low in subtitle.lower():
                score = max(score, 50)
            if q_low in k.lower():
                score = max(score, 25)
        if q_low and score == 0:
            continue
        # v2.2 internal 类型 palette 也走新标签页（target + external_blank）
        is_internal = t.get("type") == "internal"
        items.append({
            "key": k,
            "title": title,
            "subtitle": subtitle,
            "status": "running" if is_internal else get_service_status(t["service"]),
            "service": t["service"],
            "path_prefix": t["path_prefix"],
            "target": _tool_target(k, via_loading=not is_internal),
            "icon": ICON_MAP.get(k, "grid-3x3"),
            "external_blank": is_internal,
            "_score": score,
        })
    items.sort(key=lambda x: (-x.pop("_score"), x["title"]))
    return {"items": items[:limit], "total": len(items), "q": q_raw}


@app.get("/api/debug/redirect/{tool_key}")
async def debug_redirect(tool_key: str):
    """调试：显示 /open/ 实际会跳到哪个 URL。"""
    if tool_key not in TOOLS:
        raise HTTPException(404, "unknown tool")
    tool = TOOLS[tool_key]
    target = _tool_target(tool_key)
    return {
        "HAS_SYSTEMCTL": HAS_SYSTEMCTL,
        "dev_port": tool.get("dev_port"),
        "path_prefix": tool["path_prefix"],
        "target": target,
    }


@app.get("/loading/{tool_key}")
async def loading_tool(tool_key: str, request: Request):
    """进入工具的中转页：触发启动 + 显示居中 GIF，就绪后前端跳转。"""
    if tool_key not in TOOLS:
        raise HTTPException(404, "unknown tool")
    svc = TOOLS[tool_key]["service"]
    status = get_service_status(svc)

    if status == "not_installed":
        return RedirectResponse(url=f"/?need_start={tool_key}", status_code=303)

    if status != "running":
        ok, msg = systemctl_action(svc, "start")
        if not ok:
            return RedirectResponse(
                url=f"/?need_start={tool_key}&err={urllib.parse.quote(f'启动失败: {msg}')}",
                status_code=303,
            )
        # 轮询等待 systemd 就绪（至多 30s）；探测走 thread 防 event loop 阻塞
        port = TOOLS[tool_key].get("dev_port") if not HAS_SYSTEMCTL else None
        for _ in range(30):
            await asyncio.sleep(1)
            if HAS_SYSTEMCTL:
                if await asyncio.to_thread(get_service_status, svc) == "running":
                    break
            elif port and await asyncio.to_thread(is_port_open, port):
                break
        # 不阻塞渲染：无论是否就绪，先给用户看 GIF，前端继续探测

    touch_access(tool_key)
    target = _tool_target(tool_key)
    return templates.TemplateResponse(
        "loading.html",
        {"request": request, "target": target},
    )


@app.get("/open/{tool_key}")
async def open_tool(tool_key: str):
    """进入工具：未运行则自动启动，再跳转。"""
    if tool_key not in TOOLS:
        raise HTTPException(404, "unknown tool")
    svc = TOOLS[tool_key]["service"]
    status = get_service_status(svc)

    if status == "not_installed":
        return RedirectResponse(url=f"/?need_start={tool_key}", status_code=303)

    if status != "running":
        ok, msg = systemctl_action(svc, "start")
        if not ok:
            return RedirectResponse(
                url=f"/?need_start={tool_key}&err={urllib.parse.quote(f'启动失败: {msg}')}",
                status_code=303,
            )
        # 轮询等待（systemd 看 is-active，开发模式看端口）；探测走 thread 防 event loop 阻塞
        port = TOOLS[tool_key].get("dev_port") if not HAS_SYSTEMCTL else None
        for _ in range(30):
            await asyncio.sleep(1)
            if HAS_SYSTEMCTL:
                if await asyncio.to_thread(get_service_status, svc) == "running":
                    break
            elif port and await asyncio.to_thread(is_port_open, port):
                break
        else:
            return RedirectResponse(
                url=f"/?need_start={tool_key}&err={urllib.parse.quote('启动超时（30秒）')}",
                status_code=303,
            )

    touch_access(tool_key)
    # 本地开发模式：跳绝对 URL（带 dev_port）；VM 模式：跳相对路径（nginx 反代）
    target = _tool_target(tool_key)
    return RedirectResponse(url=target, status_code=303)


# ---------- 后台: 闲置超时 ----------
async def idle_checker():
    while True:
        try:
            cutoff = datetime.now() - timedelta(minutes=IDLE_TIMEOUT_MINUTES)
            for k, t in TOOLS.items():
                # always-on / internal 类型不参与闲置回收（internal 是 portal 自身页面）
                if t.get("persistent") or t.get("type") == "internal":
                    continue
                last = get_last_access(k)
                if last and last < cutoff and get_service_status(t["service"]) == "running":
                    systemctl_action(t["service"], "stop")
        except Exception:
            pass
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


# ============== LLM 设置路由（点右上角 pill → 弹 modal） ==============

@app.get("/api/settings/llm-modal")
async def api_settings_llm_modal(request: Request):
    """点 LLM pill → 弹配置 modal（HTMX 塞 #settings-modal-slot）。"""
    cfg = load_config()
    return templates.TemplateResponse(
        request=request,
        name="partials/settings_llm_modal.html",
        context={
            "request": request,
            "form": {
                "provider": cfg.get("provider", ""),
                "base_url": cfg.get("base_url", ""),
                "model": cfg.get("model", ""),
                "api_key": "",  # 密码框不预填
            },
            "providers": LLM_PROVIDERS,
        },
    )


@app.post("/api/settings/llm")
async def api_settings_llm_save(request: Request):
    """保存 LLM 配置到 ~/.ideon-portal/llm_settings.yaml。返回 JSON {ok, detail}。

    成功 → {ok: True}，前端直接关 modal
    失败 → {ok: False, detail: "..."}，前端显示在 form 里的红色小字
    """
    form = await request.form()
    provider = (form.get("provider") or "").strip()
    base_url = (form.get("base_url") or "").strip()
    model = (form.get("model") or "").strip()
    api_key = (form.get("api_key") or "").strip()

    cfg_old = load_config()
    errors = []
    if not provider:
        errors.append("Provider 不能为空")
    if not model:
        errors.append("Model 不能为空")
    if not api_key and not cfg_old.get("api_key"):
        errors.append("API Key 不能为空（首次配置必须填）")

    if errors:
        return JSONResponse({"ok": False, "detail": " · ".join(errors)})

    save_config({"provider": provider, "base_url": base_url,
                 "model": model, "api_key": api_key or cfg_old.get("api_key", "")})
    return JSONResponse({"ok": True, "detail": ""})


@app.post("/api/settings/llm/test")
async def api_settings_llm_test(request: Request):
    """测试当前表单 4 字段能否连上，返回 JSON {ok, detail}。

    返回 JSON 而不是重渲 modal：避免 modal DOM 被销毁重建（动画重跑 + api_key 丢失）。
    前端 JS 拿到结果后只改测试按钮的样式，文案 / 输入框保持原状。
    """
    form = await request.form()
    provider = (form.get("provider") or "").strip()
    base_url = (form.get("base_url") or "").strip()
    model = (form.get("model") or "").strip()
    api_key = (form.get("api_key") or "").strip()

    cfg_old = load_config()
    effective_key = api_key or cfg_old.get("api_key", "")
    effective_model = model or cfg_old.get("model", "")
    effective_url = base_url or cfg_old.get("base_url", "")

    if not provider:
        return JSONResponse({"ok": False, "detail": "Provider 不能为空"})
    if not effective_model:
        return JSONResponse({"ok": False, "detail": "Model 不能为空"})
    if not effective_key:
        return JSONResponse({"ok": False, "detail": "API Key 不能为空（首次配置必须填）"})

    test_ok, detail = probe_llm(provider, effective_url, effective_key, effective_model)
    if not test_ok:
        import sys
        print(f"[llm-test] FAIL provider={provider!r} model={effective_model!r} base_url={effective_url!r}\n{detail}", file=sys.stderr)
    return JSONResponse({"ok": test_ok, "detail": detail or ""})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORTAL_PORT)