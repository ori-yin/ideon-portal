"""ideon 中台 / 路由页。按需启停 + 闲置超时。"""

import asyncio
import shutil
import socket
import subprocess
import sys
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import sqlite3

from config import TOOLS, IDLE_TIMEOUT_MINUTES, CHECK_INTERVAL_SECONDS, DB_PATH, PORTAL_PORT

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

HAS_SYSTEMCTL = shutil.which("systemctl") is not None
_dev_procs: dict[str, subprocess.Popen] = {}  # tool_key -> subprocess（本地开发模式）


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
    if HAS_SYSTEMCTL:
        try:
            if not service_exists(name):
                return "not_installed"
            r = subprocess.run(
                ["systemctl", "is-active", name], capture_output=True, text=True, timeout=5
            )
            state = r.stdout.strip()
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
        except (FileNotFoundError, Exception):
            pass
    # 本地开发模式：探测端口
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
        log_file = open(log_dir / f"{tool_key}.log", "ab")
        proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, **kwargs)
        _dev_procs[tool_key] = proc
        # 短延迟让进程有失败机会
        import time
        time.sleep(0.3)
        if proc.poll() is not None:
            return False, f"进程立即退出，退出码 {proc.returncode}"
        return True, "已启动，等待端口"
    except Exception as e:
        return False, f"启动失败: {e}"


def stop_dev(tool_key: str) -> tuple[bool, str]:
    proc = _dev_procs.get(tool_key)
    if not proc:
        return True, "未在追踪"
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
        _dev_procs.pop(tool_key, None)
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


def build_cards():
    return [
        {
            "key": k,
            "title": t["title"],
            "subtitle": t["subtitle"],
            "status": get_service_status(t["service"]),
            "last_access": get_last_access(k),
        }
        for k, t in TOOLS.items()
    ]


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


@app.get("/")
async def index(request: Request):
    need = request.query_params.get("need_start")
    err = request.query_params.get("err")
    need_title = (TOOLS.get(need) or {}).get("title", "") if need else ""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "cards": build_cards(),
            "idle_timeout": IDLE_TIMEOUT_MINUTES,
            "need_start": need,
            "need_start_title": need_title,
            "err": err,
        },
    )


@app.get("/api/status")
async def api_status():
    out = {}
    for k, t in TOOLS.items():
        try:
            la = get_last_access(k)
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
    return {"ok": True, "service": svc}


@app.post("/api/stop/{tool_key}")
async def api_stop(tool_key: str):
    if tool_key not in TOOLS:
        raise HTTPException(404, "unknown tool")
    svc = TOOLS[tool_key]["service"]
    ok, msg = systemctl_action(svc, "stop")
    if not ok:
        raise HTTPException(500, f"stop failed: {msg}")
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


@app.get("/api/debug/redirect/{tool_key}")
async def debug_redirect(tool_key: str):
    """调试：显示 /open/ 实际会跳到哪个 URL。"""
    if tool_key not in TOOLS:
        raise HTTPException(404, "unknown tool")
    tool = TOOLS[tool_key]
    if not HAS_SYSTEMCTL and tool.get("dev_port"):
        target = f"http://127.0.0.1:{tool['dev_port']}/"
    else:
        target = tool["path_prefix"]
    return {
        "HAS_SYSTEMCTL": HAS_SYSTEMCTL,
        "dev_port": tool.get("dev_port"),
        "path_prefix": tool["path_prefix"],
        "target": target,
    }


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
        # 轮询等待（systemd 看 is-active，开发模式看端口）
        port = TOOLS[tool_key].get("dev_port") if not HAS_SYSTEMCTL else None
        for _ in range(30):
            await asyncio.sleep(1)
            if HAS_SYSTEMCTL:
                if get_service_status(svc) == "running":
                    break
            elif port and is_port_open(port):
                break
        else:
            return RedirectResponse(
                url=f"/?need_start={tool_key}&err={urllib.parse.quote('启动超时（30秒）')}",
                status_code=303,
            )

    touch_access(tool_key)
    # 本地开发模式：跳绝对 URL（带 dev_port）；VM 模式：跳相对路径（nginx 反代）
    if not HAS_SYSTEMCTL and TOOLS[tool_key].get("dev_port"):
        target = f"http://127.0.0.1:{TOOLS[tool_key]['dev_port']}/"
    else:
        target = TOOLS[tool_key]["path_prefix"]
    return RedirectResponse(url=target, status_code=303)


# ---------- 后台: 闲置超时 ----------
async def idle_checker():
    while True:
        try:
            cutoff = datetime.now() - timedelta(minutes=IDLE_TIMEOUT_MINUTES)
            for k, t in TOOLS.items():
                last = get_last_access(k)
                if last and last < cutoff and get_service_status(t["service"]) == "running":
                    systemctl_action(t["service"], "stop")
        except Exception:
            pass
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORTAL_PORT)