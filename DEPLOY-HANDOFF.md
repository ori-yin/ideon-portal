# ideon.park.mcd.ai 交接文档 (v2.6)

> 撰写：ori | 最近更新：2026-08-20 (v2.6，content-rank 预置数据更新 cnn0819)
> 接收方：VM AI 部署 / 未来 session 维护
> 目标：把 **中台 + 5 个工具**全部部署到 `ideon.park.mcd.ai`
> 核心架构：**中台做按需启停管理，工具闲置 30 分钟自动停止**（图书馆例外，见 v2.2）

---

## 0. 总览

### 0.1 部署目标

```
https://ideon.park.mcd.ai/
├── /               → 8001 FastAPI 中台（5 张卡片 + 启停控制）
├── /content-rank/  → 8501 Streamlit（mcd-content-rank）✅ 已部署待改路径
├── /copy-analyzer/ → 8502 Streamlit（mcd-copy-analyzer）⏳
├── /reach-trend/   → 8503 Streamlit（mcd-reach-trend）⏳
├── /ctr-predictor/ → 8504 Streamlit（mcd-ctr-predictor）⏳
└── /library/       → 8002 FastAPI（mcd-report-archive）⏳ 待部署
```

### 0.2 VM 现状

Ubuntu 24.04.4 LTS，4 vCPU / 15GB 内存 / 28GB 可用磁盘（已用 1.6GB）。

| 项 | 状态 |
|---|---|
| 内网 IP | 10.126.29.125 |
| 主机名 | kevinguo-ubuntu-jvpp |
| 域名 / DNS | ideon.park.mcd.ai ✅ 已解析 |
| SSL 证书 | DigiCert 通配证书已装在 `/etc/nginx/ssl/`，**由 IT 续期，本团队不操心** |
| 系统用户 | **`opsuser`**（不是 `ideon`！） |
| Nginx | 已部署，80 → 443 反代 |
| 已部署 | `ideon.service` (mcd-content-rank, 8501) |
| 待清理 | `/tmp/mcd-content-rank/`（老 8502 实例，0.0.0.0 暴露，需 kill + 备份 + rm） |

### 0.3 关键架构决策（避免后续返工）

| 决策 | 原因 |
|---|---|
| **5 个工具按需启停**，不常驻 | 15GB 内存紧张，全开 1~1.5GB / 按需 200~600MB |
| **图书馆例外（v2.2 起）**：always-on，不参与闲置回收 | Kevin 需求：图书馆长期在线，30 分钟没人访问也不停（`config.py` 里 `"persistent": True`） |
| **中台运行身份 = root**，工具 = opsuser | 中台要 systemctl 调启停；工具不需要 |
| **闲置 30 分钟自动 stop** | 工具不再被访问就杀进程；靠 `access_log` 表的 `last_access_at`（`"persistent": True` 的工具豁免） |
| **中台监听 127.0.0.1:8001**，不直暴露 | 只让 nginx 访问；所有流量必须过 nginx |
| **图书馆 = 流量库 = mcd-report-archive** | 三个名字指同一项目，UI 显示**"图书馆"**（不是"流量库"） |
| **进入按钮开新标签** (`target="_blank"`) | 用户可同时打开多个工具，中台不丢 |
| **侧栏工具菜单也跳 `/open/``** | 不滚动定位，统一行为 |

### 0.4 当前进度

| 任务 | 状态 |
|---|---|
| 中台代码开发 | ✅ 本地跑通（http://127.0.0.1:8001） |
| 图书馆本地联调 | ✅ 本地 8002 已通过中台自动启动 |
| 图书馆 always-on + 隐藏入口 | ✅ v2.2 已上线（2026-08-18） |
| content-rank 路径改造 | ⏳ VM 上 systemd 改 ExecStart |
| 部署中台 + 改 nginx + 部署图书馆 | ✅ 已部署 |
| 部署其他 3 个 Streamlit | ⏳ 后续单独上 |

---

## 1. 中台设计

### 1.1 5 个工具注册表（`config.py`）

```python
TOOLS = {
    "content-rank":  {"service": "ideon.service",          "path_prefix": "/content-rank/"},
    "copy-analyzer": {"service": "copy-analyzer.service",  "path_prefix": "/copy-analyzer/"},
    "reach-trend":   {"service": "reach-trend.service",    "path_prefix": "/reach-trend/"},
    "ctr-predictor": {"service": "ctr-predictor.service",  "path_prefix": "/ctr-predictor/"},
    "library":       {"service": "traffic-library.service","path_prefix": "/library/",
                      "dev_cmd": [...], "dev_cwd": "...", "dev_port": 8002},
}
```

加/删工具改这里，重启 portal：`sudo systemctl restart portal`

### 1.2 两套启停逻辑（自动检测平台）

```python
HAS_SYSTEMCTL = shutil.which("systemctl") is not None

# VM (Linux):  systemctl start ideon.service
# 本地 (Win):  Popen([sys.executable, "-m", "uvicorn", ...], cwd=dev_cwd)
```

**本地开发模式字段**（仅 library 配置，其他工具可后续补）：
- `dev_cmd`: 启动命令列表，`python` 会被替换成当前 venv 的 `sys.executable`
- `dev_cwd`: 子进程工作目录
- `dev_port`: 用于端口探测判断是否启动成功

VM 上 `HAS_SYSTEMCTL=True`，dev_* 字段永远走不到，**无需删除**。

### 1.3 API 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/` | 中台首页 |
| GET | `/api/status` | 5 个工具实时状态 JSON |
| GET | `/api/summary` | KPI 汇总 |
| POST | `/api/start/{key}` / `/api/stop` / `/api/restart` | 启停重启 |
| GET | `/open/{key}` | 自动启动 → 跳转（详见 1.4） |
| GET | `/api/debug/redirect/{key}` | 调试用，看 `/open/` 实际跳哪个 URL |

### 1.4 `/open/` 自动启动逻辑（重点）

```
用户点击"进入"或侧栏菜单
    ↓
GET /open/library → 中台
    ↓
查 status（systemd is-active 或端口探测）
    ↓
├─ not_installed → 重定向到 /?need_start=library（黄色 banner："服务尚未部署"）
├─ failed → 重定向到 /?need_start=library&err=...（红色 banner）
├─ stopped → systemctl start / Popen uvicorn → 轮询 30s
│   ├─ 成功 → 重定向到目标 URL
│   └─ 超时 → 重定向到 /?need_start=library&err=启动超时（30秒）
└─ running → 直接 touch_access + 重定向

target URL 选择：
  本地模式（有 dev_port）：http://127.0.0.1:{dev_port}/（绝对 URL，绕过 portal 自己的 8001）
  VM 模式：{path_prefix}（相对路径，给 nginx 反代）
```

### 1.5 视觉规范

- **侧栏** 240px，`#2A2A2A` 背景
- **顶部栏** 72px，白底
- **选中态**：金黄 `#FFBA0D` 背景 + 黑字 `#222222`
- **左上角 logo**：麦当劳官方金拱 SVG（填色 `#fc0`）内联，不引外链
- **图标**：Heroicons SVG sprite 内联，零外部依赖
- **状态色**：running `#16A34A` / stopped `#9CA3AF` / failed `#DCF262` / not_installed `#EA580C`
- **禁用 emoji**（品牌调性）

---

## 2. 5 个工具详情

### 2.1 mcd-content-rank（✅ 已部署 / 待改造）

- 端口 8501（保持），服务名 `ideon.service`
- 改造：`--server.baseUrlPath=/content-rank`
- systemd 改 ExecStart，daemon-reload + restart

### 2.2 mcd-copy-analyzer / reach-trend / ctr-predictor（⏳ 待部署）

每个工具 0.5 天工作量。模板见 §3.5。

### 2.3 图书馆 = mcd-report-archive（⏳ 待部署到 VM / ✅ 本地已联调）

| 项 | 值 |
|---|---|
| 端口 | 8002 |
| 服务名 | `traffic-library.service` |
| 入口模块 | `app.main:app` |
| 启动命令 | `uvicorn app.main:app --host 127.0.0.1 --port 8002 --workers 1` |
| 数据 | `data/archive.db` (SQLite) + `data/reports/` (HTML) |
| 部门 | `3PO / CNN / OC / 社媒 / / 其他` |
| 运行身份 | opsuser（不需要 root） |
| 中台调用 | `/library/` path_prefix → nginx 反代 8002 |

**源码来自 ori 本地 OneDrive**，**不要重新生成**。

---

## 3. 部署步骤（精简版）

完整步骤在 `Desktop/VM-AI-DEPLOY-PROMPT.md`（已经发给 VM AI 的）。

按依赖顺序：

1. **清理老 8502**：kill 老进程 + 备份 `/tmp/mcd-content-rank/` + rm
2. **部署中台**：解压到 `/opt/ideon/portal/` → venv → systemd enable
3. **改 content-rank 路径**：ExecStart 加 `--server.baseUrlPath=/content-rank`
4. **部署图书馆**：解压到 `/opt/ideon/traffic-library/` → venv → systemd enable
5. **改 nginx**：加 `/library/` location 反代 + reload
6. **关掉老的对内网开放的入口**：所有 0.0.0.0 监听改为 127.0.0.1

---

## 4. 本地开发模式（重要！）

ori 在 Windows 上也要跑通中台，方便调试工具 UX。代码自动检测平台：

- **VM**（Linux，有 systemctl）→ 走 systemd 路径
- **本地**（Windows，没 systemctl）→ 走 `subprocess.Popen + 端口探测` 路径

**本地启动中台**：
```bash
cd C:\Users\a952462\ideon-portal
venv\Scripts\activate
uvicorn app:app --reload
```

**本地访问**：http://127.0.0.1:8001

**测试流程**（已验证）：
1. 装齐图书馆依赖到 portal venv（mcd-report-archive 要的版本比 portal 高）：
   ```
   pip install fastapi==0.136.3 uvicorn==0.49.0 jinja2==3.1.6 python-multipart==0.0.30
   ```
2. 中台首页 5 张卡片，content-rank 显示"未部署"（Windows 没装 ideon.service），其余 4 张也"未部署"
3. 点"图书馆"侧栏或卡片"进入" → 新标签打开 → 中台调 `Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8002"], cwd=OneDrive/mcd-report-archive)`
4. 等 8002 端口监听 → 跳转 http://127.0.0.1:8002/（注意：是绝对 URL，因为本地没 nginx 兜底）

**调试技巧**：
- `http://127.0.0.1:8001/api/debug/redirect/library` → 看 `/open/` 实际跳哪个 URL
- `http://127.0.0.1:8001/api/status` → 看所有工具状态
- 子进程日志：`ideon-portal/logs/library.log`
- 中台日志：uvicorn 终端直接看

---

## 5. Bug 修复记录（v2.1）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | `/api/status` 返 500 | walrus `:=` 在 true 分支绑 `la`，但条件 `if la` 先求值 → NameError | 改成显式 `la = get_last_access(k)` 再三元判断 |
| 2 | `/open/library` 跳到 portal 自己 404 | 跳转用相对路径 `/library/`，本地没 nginx 兜底 | 本地模式跳绝对 URL `http://127.0.0.1:{dev_port}/`；VM 模式仍用相对路径（nginx 反代） |
| 3 | 进入工具时 banner 误导 | "正在自动启动，请稍候重试" 写错，实际 not_installed 时根本不调 start | 改成"服务尚未部署，请联系管理员部署后重试" |
| 4 | portal 退出后 dev 子进程变孤儿 | lifespan teardown 只 cancel 异步 task，没清 `_dev_procs` | finally 块遍历 `_dev_procs` 调 `stop_dev` |
| 5 | 用户构造 `?need_start=xxx` 让标题显示 "· ideon 中台" | `need_start_title` 为 None 时 Jinja 渲染残缺 | Python 端 `TOOLS.get(need, {}).get("title", "")` + Jinja 加 `and need_start_title` 防御 |

---

## 5.5 变更日志（Change Log）

> 每次迭代/改动，在这里追加一条。格式：日期 + 改动内容 + 原因 + 涉及文件。

### v2.6 — 2026-08-20（content-rank 预置数据更新 cnn0818 → cnn0819，Mecha 执行）

**需求**：P0017393 发来最新 `cnn0819.xlsx`，替换预置数据源，让内容排行榜覆盖到 8/19。

**改动**：
| 文件 | 改动 |
|---|---|
| `/opt/ideon/content-rank-data/cnn0819.xlsx` | 新增（1099 行，7/23~8/19，28 天，4 渠道 APP Push/短信/企微1v1/微信小程序订阅，含 Message ID，0 空值） |
| `/opt/ideon/app.py` | `_DEFAULT_DATA_FILE` → `cnn0819.xlsx`；`last_file_id` → `preset:cnn0819.xlsx` |
| 备份 | `/opt/ideon/app.py.bak.20260820_cnn0819` |

**验证**（全部通过）：
- `app.py` 语法 OK；清洗管道 shape (1099, 18)，message_id 0 空值
- 服务启动 active，`/content-rank/` 200
- **WS 握手 HTTP/1.1 → 101 Switching Protocols**（铁律 §v2.4 复查通过）

**说明**：cnn0818.xlsx 保留不删（作历史）；app.py 注释文字仍写 cnn0818，无功能影响。

---

### v2.4 — 2026-08-19（content-rank WebSocket Host 修复，Mecha 排查）

**需求**：`/content-rank/`（8501，Streamlit）页面打开卡住 / WebSocket 反复断开。用户发现 nginx 转发后 Streamlit 收到的 Host 变成了 `127.0.0.1:8501`，问根因及如何避免再犯。

**排查结论**：
- ✅ **服务本身正常**：`ideon.service` active running，8501 监听 127.0.0.1，`/content-rank/_stcore/health` 200
- ❌ **根因**：`/etc/nginx/sites-available/ideon` 的 `/content-rank/` location **缺少 `proxy_set_header Host $host;`**（对比 `/`、`/api/` 段都有）。反代到 8501 时 Host 回退成 `127.0.0.1:8501`
- Streamlit 会校验 WebSocket 的 Origin/Host（`starlette_websocket.py:_is_origin_allowed`）：`origin=https://ideon.park.mcd.ai` vs `host=127.0.0.1:8501` 不一致 → **1008 Policy Violation 拒绝**，日志报 `Rejecting WebSocket connection with disallowed Origin or Host header`
- 影响：页面 HTML 能加载（HTTP 200），但 WebSocket 连不上 → 页面交互卡死/一直转圈

**修复**：
| 文件 | 改动 |
|---|---|
| `/etc/nginx/sites-available/ideon` | `/content-rank/` location 补 `proxy_set_header Host $host;` + `X-Real-IP` + `X-Forwarded-For` + `X-Forwarded-Proto`（与顶层一致） |
| 备份 | `/etc/nginx/sites-available/ideon.bak.20260819.pre-fix` |

**验证**（全部通过）：
- `nginx -t` + `systemctl reload nginx`
- 模拟 WS 握手：`curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" ... -H "Origin: https://ideon.park.mcd.ai" https://ideon.park.mcd.ai/content-rank/_stcore/stream` → **HTTP 101 切换成功**（修复前是 200 HTML 页面，说明 WS 被拒走不了 Upgrade）
- 线上页面交互正常

**🔒 铁律（防止再犯）**：**凡是 Streamlit / 需要 WebSocket 的 location，必须显式带全 4 个 header：`Host $host` + `Upgrade $http_upgrade` + `Connection "upgrade"` + `X-Forwarded-Proto $scheme`。** 缺 `Host` 时 nginx 会回退成 `127.0.0.1:<port>`，Streamlit 的 WS Origin/Host 校验必挂。以后新增任何工具 location，先对照本段抄一遍，再按 §6 checklist 的 WS 项验证。

### v2.3 — 2026-08-18（图书馆路径前缀修复，Mecha 排查）

**需求**：同事访问图书馆报障——左侧日期看不到、部门筛选用不了、文件拖不上传。

**排查结论**：
- ✅ **不是数据库没数据**：archive.db 有 23 条日报（8/1~8/16，3PO/CNN/OC/社媒）
- ✅ **后端 8002 正常**：所有 API 直连 127.0.0.1:8002 返回正常
- ❌ **根因1（路径前缀）**：前端 JS 用 `fetch('/api/...')`（不带 `/library/` 前缀），nginx 把 `/api/` 路由到中台 8001 → 全 404
- ❌ **根因2（模板缓存）**：文件在 10:53 已改成带 `/library/` 前缀的正确版本，但服务进程 10:17 启动，`auto_reload=False` 导致线上仍跑旧模板（`/static/...` 旧 JS 旧 fetch），改动未生效

**修复**：
| 文件 | 改动 |
|---|---|
| `app/static/app.js` | 所有 `fetch('/api/...')` → `fetch('/library/api/...')`；`/report/` → `/library/report/` |
| `app/templates/index.html` | 所有 `/static/...` → `/library/static/...` |
| 服务 | `systemctl restart traffic-library.service` 让新模板生效 |

> ⚠️ 注：文件改动是或（ori/其他 session）在 10:53 完成的，Mecha 排查确认并触发重启生效。

**验证**（全部 200）：
- 首页、静态资源（style.css/app.js/mcdonalds.svg）
- API：departments / latest / calendar / reports / upload / report 预览
- 中台路由页无图书馆入口 ✅

**教训**：`auto_reload=False` 下，改模板/JS 后**必须重启服务**才生效，否则线上跑旧版。改完要 curl 验证渲染后 HTML。

### v2.2 — 2026-08-18（Mecha 执行，Kevin 需求）

**需求**：图书馆（`/library/`）长期在线，不参与 30 分钟闲置回收；中台路由页隐藏图书馆入口（路由页只保留内容相关工具）。只有一个域名 `ideon.park.mcd.ai`，不新增域名，图书馆仍走 `/library/` 路径。

**改动**：
| 文件 | 改动 | 原因 |
|---|---|---|
| `config.py` | `library` 注册表加 `"persistent": True` + `"hidden": True` | persistent → always-on 不回收；hidden → 页面不展示 |
| `app.py` | `idle_checker()` 循环里 `if t.get("persistent"): continue` 跳过常驻工具 | 30 分钟闲置不再对 library 执行 `systemctl stop` |
| `app.py` | `build_cards()` 过滤 `hidden` 工具 | 工具卡片区不显示图书馆 |
| `templates/index.html` | 侧边栏 nav 硬编码列表移除 `('library', '图书馆', 'i-book')`；卡片图标分支移除 `elif card.key == 'library'` | 页面彻底不显示图书馆入口 |

**验证**（全部通过）：
- `curl http://127.0.0.1:8001/` 首页无「图书馆 / library / 日报归档」字样
- 工具卡片 data-key 只剩 4 个：content-rank / copy-analyzer / reach-trend / ctr-predictor
- `https://ideon.park.mcd.ai/library/` → HTTP 200（nginx 反代 8002 正常）
- `/api/status` 里 library 仍在注册表（running）
- idle_checker 已跳过 persistent 工具（代码确认）

**行为变化**：
- 图书馆**永远在线**，闲置 30 分钟不会被停，也无需从路由页点「进入」触发启动
- 图书馆只能通过 `https://ideon.park.mcd.ai/library/` 直连（页面无入口）
- KPI 显示「工具总数 5」含 library（仍注册），在线数含常驻的 library
- 之前 `index.html` 有一处 `('library', ...)` 编辑工具显示成功但实际未落盘，复查后重新编辑生效——**以后改模板后必须 `grep` 复查落盘**

**备份**：改动前备份 `config.py / app.py / templates/index.html` → `*.bak.20260818_104050`，可回滚。

**遗留问题（已解决 → v2.4）**：`/content-rank/`（8501，`ideon.service`）当时 502 挂掉，进程没在跑 —— 该问题 2026-08-19 由服务拉起 + v2.4 的 WebSocket Host 修复一并解决，详见 v2.4。

---

## 6. 验收 checklist（部署完勾）

- [ ] `ss -l -t -n | grep -E '8001|8501|8002'` 都监听 127.0.0.1
- [ ] `systemctl is-active portal ideon traffic-library` 全 active
- [ ] `systemctl is-enabled portal ideon traffic-library` 全 enabled
- [ ] `curl https://ideon.park.mcd.ai/` 200，中台 5 张卡片
- [ ] content-rank "进入"按钮 → 跳转 /content-rank/
- [ ] **Streamlit WS 握手必须 101**（防 Host 缺失再犯）：`curl -sk -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: SGVsbG9Xb3JsZDEyMzQ1Ng==" -H "Origin: https://ideon.park.mcd.ai" "https://ideon.park.mcd.ai/content-rank/_stcore/stream" | head` → 必须是 `HTTP/1.1 101 Switching Protocols`（若返回 200 HTML = Host header 缺失被拒）
- [ ] `sudo journalctl -u ideon --since today` 无 `Rejecting WebSocket connection` 日志
- [ ] 图书馆 "进入"按钮 → 跳转 /library/ 显示日报归档首页
- [ ] 中台点"启动/停止/重启"按钮都能正常响应
- [ ] 中台视觉：金拱 SVG + 侧栏 #2A2A2A + 选中态 #FFBA0D + Heroicons
- [ ] 闲置 30 分钟后手动设 `IDLE_TIMEOUT_MINUTES=1` 验证自动停止

---

## 7. 收尾要求

VM AI 部署完成给我一份报告：
1. 已部署服务清单（systemd 名 + 端口）
2. 验收 checklist 哪几项过 / 哪几项失败
3. 任何意外 / 报错 / 临时方案
4. `/var/log/ideon/` 下所有日志路径

---

## 8. 待办（下一阶段）

### 短期（部署完一周内）
- [ ] 其他 3 个 Streamlit 工具部署（copy-analyzer / reach-trend / ctr-predictor）
- [ ] SQLite 备份 cron（每天 sqlite3 .backup portal.db / archive.db）
- [ ] 日志轮转（logrotate 给 `/var/log/ideon/*.log`）

### 中期
- [ ] 工具定期回调 `/touch-access/{key}` 续闲置计时（现在只算 `/open/` 点击）
- [ ] 中台加更新日志面板（暂无数据，等有 changelog）
- [ ] 用户认证：问 IT 有没有 SSO / OIDC

### 已完成
- [x] 中台代码开发 + 本地联调
- [x] 图书馆代码部署包准备
- [x] VM AI 部署 prompt 写完

---

## 9. 联系方式

- ori 在家远程，所有部署 / SSH 操作都在 VM AI 上做
- 中台代码由 ori 打包提供，VM AI 部署
- 图书馆源码来自 ori 本地 OneDrive，**不要重新生成**
- 任何阻塞问题先记下，别瞎猜

---


---

## 10. 项目完整历程（从最早压缩包到上线运行）

> 本节由 Mecha 于 2026-08-20 补齐，完整覆盖从 Kevin 最早发来压缩包到当前上线稳定运行的全流程 + 所有坑。供任何接手者快速了解"这个项目怎么来的"。

### 10.1 时间线总览

| 时间 | 事件 | 产出 |
|---|---|---|
| ~2026-08-11 | ori 本地开发 content-rank / 图书馆 / 中台（spec→plan→todo→implement） | 源码包 |
| 08-14 16:50 | Kevin 发来 `mcd-content-rank-main.7z`（3.6MB）+ `park_mcd_ai.zip`（证书） | /tmp/ideon-deploy/ |
| 08-14 | 配置 HTTPS + 部署内容排行榜（单应用，8501 直跑） | ideon.park.mcd.ai 上线 |
| 08-17 15:02 | Kevin 发来 3 文件：VM-AI-DEPLOY-PROMPT.md + ideon-portal.zip + mcd-report-archive.zip | 三件套部署 |
| 08-17 | 部署中台(8001) + 改 content-rank 路径 + 部署图书馆(8002) + 清理老8502 | 多工具体系成型 |
| 08-18 | 图书馆 always-on + 中台隐藏入口（v2.2） | persistent/hidden |
| 08-18 | 图书馆路径前缀修复（v2.3） | /library/ 前缀 + 重启 |
| 08-19 | content-rank 预置数据 + WebSocket Host 修复（v2.4） | cnn0818.xlsx + WS 101 |
| 08-20 | 本 Handoff 补齐全流程（v2.5） | 完整交接 |

### 10.2 每个阶段做了什么 + 踩了什么坑

**Phase 0 压缩包时代（ori 本地）**
- content-rank = Streamlit（评分算法：触达/CTR/GC 权重 25/55/20% + 置信度惩戒；Q3 阈值分段评分）
- 图书馆 = FastAPI + SQLite + 纯 HTML/CSS/JS，麦当劳品牌风；曾因 OneDrive 文件锁导致 .bat 闪退，已迁 `C:\projects\mcd-report-archive\`
- starlette 1.2.1 `Jinja2Templates` 报 `unhashable dict` → 用 jinja2 直渲染，**别改回**

**Phase 1 单应用首部署（08-14）**
- 证书：`*.park.mcd.ai` DigiCert 通配（2026-04-02 ~ 2026-10-17，IT 续期）
- `/opt/ideon/` + Python 3.12 venv + `ideon.service`（8501，自启+自动重启）
- ✅ 验收通过；老 `/tmp/mcd-content-rank` 8502 实例留待清理

**Phase 2 三件套部署（08-17）**
- 按 VM-AI-DEPLOY-PROMPT 6 步：清老8502 → 中台 → content-rank 路径 → 图书馆 → nginx → 关0.0.0.0
- 🕳️ **坑1：portal PATH 被覆盖** → `Environment=PATH=仅venv` 导致 `shutil.which("systemctl")` 找不到 → `HAS_SYSTEMCTL=False` → 全工具误走本地模式 → 全显示 not_installed
  - 修：PATH 改 `venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`
  - 教训：systemd `Environment=PATH=` 是覆盖不是追加，要 systemctl 必须带全系统 PATH
- 🕳️ **坑2：nginx /library/ 404** → FastAPI 不认 `/library/` 前缀，必须 `rewrite ^/library/(.*)$ /$1 break;`；前端绝对路径 `/static/...` 需单独 `/static/ → 8002` 路由
- ✅ 20:40 全链路闭环验证：`/open/content-rank`、`/open/library` 均 303 拉起 200

**Phase 3 图书馆 always-on + 隐藏入口（08-18）**
- Kevin 需求：图书馆长期在线，不参与 30 分钟闲置回收；中台路由页隐藏图书馆入口
- 改动：config.py `persistent:True`+`hidden:True`；app.py idle_checker 跳过 persistent、build_cards 过滤 hidden；index.html 移除入口
- 🕳️ **坑3：模板缓存** → 同事报障"看不到日期/筛选用不了/拖不上传"。根因：① 前端 JS `fetch('/api/...')` 不带 `/library/` 前缀被 nginx 路由到 8001 全 404；② `auto_reload=False` 服务跑旧模板
  - 修：JS/HTML 加 `/library/` 前缀 + `systemctl restart traffic-library.service`
  - 教训：改模板/JS 后**必须重启服务**；改 index.html 必须 grep 复查落盘（曾"显示成功但没写进去"）

**Phase 4 content-rank 预置数据 + WS 修复（08-19）**
- 预置数据：`/opt/ideon/content-rank-data/cnn0818.xlsx`（1081 行，7/22~8/18，4渠道含 Message ID）；app.py 首次访问自动加载（mtime 指纹重载），上传后以用户文件为准
- 🕳️ **坑4（最重要）：nginx 缺 Host → Streamlit WS 1008** → `/content-rank/` location 缺 `proxy_set_header Host $host;` → 反代 Host 回退 `127.0.0.1:8501` → Streamlit `_is_origin_allowed` 校验 origin vs host 不一致 → **1008 Policy Violation**，页面卡死转圈
  - 修：补全 `Host $host` + `X-Real-IP` + `X-Forwarded-For` + `X-Forwarded-Proto`
  - 🔒 **铁律：凡 Streamlit/WebSocket location 必须带全 `Host $host` + `Upgrade $http_upgrade` + `Connection "upgrade"` + `X-Forwarded-Proto $scheme`，缺 Host 必挂**
  - 验证：WS 握手 curl 必须 **101 Switching Protocols**（200 HTML = 被拒）
- 顺手解决 v2.2 遗留的 content-rank 502

### 10.3 当前状态（2026-08-20）

| 服务 | 状态 | 说明 |
|---|---|---|
| portal (8001) | ✅ active+enabled | root |
| traffic-library (8002) | ✅ active+enabled | always-on |
| ideon (8501) | ⚠️ inactive（enabled） | **闲置回收 = 正常设计**；`/open/content-rank` 点击自动拉起 |

### 10.4 运维速查

```bash
systemctl status portal ideon traffic-library
sudo journalctl -u ideon -f
sudo journalctl -u ideon --since today | grep -i reject   # 查 WS 被拒
sudo nginx -t && sudo systemctl reload nginx
curl -s http://127.0.0.1:8001/api/status | python3 -m json.tool
```

### 10.5 待办

- [ ] 3 个 Streamlit 工具部署（copy-analyzer / reach-trend / ctr-predictor）
- [ ] SQLite 备份 cron + 日志轮转
- [ ] 工具回调 `/touch-access/{key}` 续闲置计时
- [ ] SSO/OIDC 用户认证调研
- [ ] 若 content-rank 需 always-on：config.py 加 `"persistent": True`（参考图书馆）

---

文档结束。文档结束。

---

## 9. 变更日志

### v3.0 — 2026-08-25 content-rank 升级到 SQLite 留档版（svc 版）＋阈值调整

**背景**：Kevin 发来新版压缩包 `mcd-content-rank-svc-main`（HANDOFF.md，HEAD 未推），数据存 SQLite 留档，打开即读，不再每次上传。

**主要变更**
- 代码：`app.py / config.py / scoring.py / data_cleaning.py / llm_service.py / styles.py / ingest_cli.py` + 新增 `data_source/`（sqlite_store.py / uploaded_source.py）+ `.streamlit/config.toml` 全部替换为 svc 版
- 数据层：`data/content_rank.db`（SQLite，fact_push 表），打开页面直接读库
- 覆盖语义：按上传文件 `min~max(发送日期)` DELETE+INSERT，区间外历史不动；四道保险（预览/自动备份/行数骤降警告/硬拦截 30%）
- 阈值调整（config.py，2026-08-18 本地校准）：
  - CTR/CVR 阈值 P75 → **P90**（APP Push CTR 0.23→0.30，企微 1.12→1.75，小程序 4.09→4.90，短信 0.44→0.43；CVR APP 21.35→20.72 等）
  - **新增 REACH_THRESHOLDS**（per-channel 固定 Q3）：APP Push 800万 / 企微 100万 / 小程序 100万 / 短信 20万；REACH_EXP=0.5；REACH_UNKNOWN=10万
- 导入口令：`INGEST_PASSCODE=ori1026`（systemd ideon.service 环境变量，仅 Kevin/ori 可导入）

**部署动作**
- 备份：`/opt/ideon/bak.svc-upgrade-20260825_101914/`（旧版代码全量）+ sqlite_store.py 修复备份
- 端口沿用 8501 / 127.0.0.1；`.streamlit/config.toml` 启用 `baseUrlPath="content-rank"`（与 nginx 一致）
- 依赖：补装 `anthropic>=0.40,<1`（新版 llm_service 引入）
- systemd ideon.service：ExecStart 去掉 `--server.baseUrlPath` 参数（改由 config.toml 管理），加 `INGEST_PASSCODE` env
- 闲置回收：**保留**（content-rank 非 persistent，30 分钟自动停 + `/open/content-rank` 自动拉起）；SQLite 数据落盘不受回收影响

**数据**
- 导入 `CNN历史备份0823.xlsx`（48,628 行，2024-10-15 ~ 2026-08-23）→ `data/content_rank.db`
- 首次导入备份：`data/backups/content_rank_20260825_102330.db`

**修复的 bug（需同步 ori 上游）**
- `data_source/sqlite_store.py:preview()` 空库首次导入 TypeError：`SELECT SUM(...)` 对空表返回 NULL，`existing > 0` 崩溃。修复：`existing = existing or 0; total = total or 0`（备份 `.bak.20260825_empty-fix`）
- ⚠️ 旧版预置数据模式（cnn082x.xlsx 自动加载 + session_state）已废弃，content-rank-data/ 目录保留做归档但不参与加载

**验证结果（2026-08-25）**
- 本地 health `/content-rank/_stcore/health` ✅ 200
- HTTPS `/content-rank/` ✅ 200；HTTPS health ✅ 200
- WebSocket 握手（HTTP/1.1）✅ **101**（注意：curl 默认 HTTP/2 测 WS 会得到 200 静态页，必须 `--http1.1` 才触发升级）
- 32 个回归测试（test_store/scoring/date_parsing）✅ 全过
- `import app, config, scoring, data_cleaning, llm_service, data_source.*` ✅ OK

**运维提示**
- 导入数据：`cd /opt/ideon && /opt/ideon/venv/bin/python ingest_cli.py <xlsx> --yes`（页面需口令 `ori1026`）
- 查库：`ingest_cli.py --status`
- 回滚：删 `data/content_rank.db` → 把 `data/backups/` 最近一份复制回来；代码回滚用 `bak.svc-upgrade-20260825_101914/`

### v3.1 — 2026-08-25（同日）AI 配置可自定义 + 库状态行隐藏

**需求（Kevin）**：内网不同人可能用不同 API，AI 配置的 Provider / 模型要能手动输入，不能只能选预设。

**改动**
- `app.py` AI 配置段重构：
  - Provider 下拉 = 6 预设 + `自定义…`；**默认选中「自定义…」**
  - 自定义分支：可输入 Provider 名称 / Base URL / 模型 / API Key（走 OpenAI 协议 + 自定义 base_url）
  - 预设分支：Base URL 自动带出预设值（可手动改）、模型下拉可选
  - widget key 去冲突：自定义 `ai_base_url_custom`/`ai_model_custom`，预设 `ai_base_url_preset`/`ai_model_preset`
- `llm_service.py`：`call_llm` / `call_llm_text` / `analyze_content` / `analyze_summary` 全部增加 `base_url: str = None` 参数；传入时优先，否则用预设；自定义 provider 必须传 base_url
- `app.py` 调用点传入 `base_url=ai_base_url`
- **页面顶部数据库状态行隐藏**：原来 `_render_ingest_panel()` 顶部 `st.caption("数据库：... 行 ｜ ...")` 删除，移到「导入数据」展开区内（口令通过后、上传控件前）显示，空库 warning 保留

**验证**（streamlit.testing.v1.AppTest 真实执行脚本）
- 默认 provider = 自定义…，自定义分支渲染正常，0 异常
- 切预设（MiniMax）→ Base URL 自动带出 + 模型下拉正常，0 异常
- HTTPS 200 / WS 101 / 服务 active

**备份**：`app.py.bak.20260825_custom-provider` / `llm_service.py.bak.20260825_custom-provider`
