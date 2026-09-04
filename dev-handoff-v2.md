# ideon.park.mcd.ai 交接文档 (v2.1)

> 撰写：ori｜最近更新：2026-08-17 (v2.2，VM 部署完成 + 2 个实战 bug 修复)
> 接收方：VM AI 部署 / 未来 session 维护
> 目标：把 **中台 + 5 个工具**全部部署到 `ideon.park.mcd.ai`
> 核心架构：**中台做按需启停管理，工具闲置 30 分钟自动停止**

---

## 0. 总览

### 0.1 部署目标

```
https://ideon.park.mcd.ai/
├── /               → 8001 FastAPI 中台（5 张卡片 + 启停控制）
├── /content-rank/  → 8501 Streamlit（mcd-content-rank）✅ 已部署 + 路径改造
├── /copy-analyzer/ → 8502 Streamlit（mcd-copy-analyzer）⏳
├── /reach-trend/   → 8503 Streamlit（mcd-reach-trend）⏳
├── /ctr-predictor/ → 8504 Streamlit（mcd-ctr-predictor）⏳
└── /library/       → 8002 FastAPI（mcd-report-archive）✅ 已部署
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
| 已部署 | `portal.service` (8001, root) + `ideon.service` (8501, opsuser) + `traffic-library.service` (8002, opsuser) |
| 已清理 | 2026-08-17 杀掉老 8502 进程 + 备份 `/tmp/mcd-content-rank/`（140MB）后删除 |

### 0.3 关键架构决策（避免后续返工）

| 决策 | 原因 |
|---|---|
| **5 个工具按需启停**，不常驻 | 15GB 内存紧张，全开 1~1.5GB / 按需 200~600MB |
| **中台运行身份 = root**，工具 = opsuser | 中台要 systemctl 调启停；工具不需要 |
| **闲置 30 分钟自动 stop** | 工具不再被访问就杀进程；靠 `access_log` 表的 `last_access_at` |
| **中台监听 127.0.0.1:8001**，不直暴露 | 只让 nginx 访问；所有流量必须过 nginx |
| **图书馆 = 流量库 = mcd-report-archive** | 三个名字指同一项目，UI 显示**"图书馆"**（不是"流量库"） |
| **进入按钮开新标签** (`target="_blank"`) | 用户可同时打开多个工具，中台不丢 |
| **侧栏工具菜单也跳 `/open/``** | 不滚动定位，统一行为 |

### 0.4 当前进度

| 任务 | 状态 |
|---|---|
| 中台代码开发 | ✅ 本地跑通（http://127.0.0.1:8001） |
| 图书馆本地联调 | ✅ 本地 8002 已通过中台自动启动 |
| content-rank 路径改造 | ✅ ExecStart 加 `--server.baseUrlPath=/content-rank` |
| 部署中台 + 改 nginx + 部署图书馆 | ✅ 2026-08-17 VM AI 完成，9 项验收全过（详见 §10） |
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

## 5. Bug 修复记录（v2.1 + v2.2 实战）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | `/api/status` 返 500 | walrus `:=` 在 true 分支绑 `la`，但条件 `if la` 先求值 → NameError | 改成显式 `la = get_last_access(k)` 再三元判断 |
| 2 | `/open/library` 跳到 portal 自己 404 | 跳转用相对路径 `/library/`，本地没 nginx 兜底 | 本地模式跳绝对 URL `http://127.0.0.1:{dev_port}/`；VM 模式仍用相对路径（nginx 反代） |
| 3 | 进入工具时 banner 误导 | "正在自动启动，请稍候重试" 写错，实际 not_installed 时根本不调 start | 改成"服务尚未部署，请联系管理员部署后重试" |
| 4 | portal 退出后 dev 子进程变孤儿 | lifespan teardown 只 cancel 异步 task，没清 `_dev_procs` | finally 块遍历 `_dev_procs` 调 `stop_dev` |
| 5 | 用户构造 `?need_start=xxx` 让标题显示 "· ideon 中台" | `need_start_title` 为 None 时 Jinja 渲染残缺 | Python 端 `TOOLS.get(need, {}).get("title", "")` + Jinja 加 `and need_start_title` 防御 |
| 6 | **VM 部署时全部工具误报 not_installed** | `portal.service` 模板 `Environment="PATH=/opt/ideon/portal/venv/bin"` 把 PATH 覆盖成只有 venv → `shutil.which("systemctl")` 找不到 `/usr/bin/systemctl` → `HAS_SYSTEMCTL=False` → 全部工具走本地 dev 模式 | portal.service 改 PATH 为 `venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`。**⚠️ 任何新建 VM/重装都会复现，必须先修模板再部署** |
| 7 | **VM 上访问 `/library/` 静态资源 404** | 图书馆前端用绝对路径引用 `/static/`，nginx `/library/` 反代不剥离前缀会找不到 | nginx location 加 `proxy_set_header Host $host;` 并保留 `/static/` 直通路由 |

---

## 6. 验收 checklist（部署完勾）

- [ ] `ss -l -t -n | grep -E '8001|8501|8002'` 都监听 127.0.0.1
- [ ] `systemctl is-active portal ideon traffic-library` 全 active
- [ ] `systemctl is-enabled portal ideon traffic-library` 全 enabled
- [ ] `curl https://ideon.park.mcd.ai/` 200，中台 5 张卡片
- [ ] content-rank "进入"按钮 → 跳转 /content-rank/
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

## 9. UI 迭代日志（v3.1+，2026-09-04）

### v3.1 — SVG icon 全套 + ⌘K Command Palette（commit 194e790）

设计层大改。designUIv3.md §34 禁用 emoji/unicode + §11 要求全局 ⌘K。中台 icon 全套换 lucide SVG（14 个）+ 加 Command Palette。

核心改动：
- **ICON_SVG 前后端去重**：14 个 lucide SVG 字符串放后端 `app.py` 常量，`<body data-icons='...'>` 注入；前端 `ICONS = JSON.parse(document.body.dataset.icons)`，删 ICONS/ICON_KEY 硬编码
- **`config.ICON_MAP` 单一来源**：tool_key → icon_key 映射，DRY
- **`_tool_target()` 统一 helper**：4 处 target 拼接收敛
- **5s 状态缓存**：`get_service_status` 包缓存层（`STATUS_CACHE_TTL`），共享 `api_status / api_summary / build_cards / idle_checker`
- **status-pill 三套 → 单 `.status` + `.is-flat`**：tool card / palette 共用 `STATUS` 表 + `statusHtml()` helper
- **⌘K Command Palette**：Liquid Glass 模态 + debounce 120ms + ↑↓ Enter Esc
- **8 个 UI bug**：palette 默认显示 / 黑点 / 猫耳 / bell 红点 / metric icon 过大 / tool card 重排 / 卡宽 / hover 描边

### v3.1.1 — UI 微调（commit 5202484）

3 处调整：
1. **Metric icon 内 SVG 缩到 20×20**（容器 40×40 不变，留 ~10px padding 防"填太满"）
2. **Sidebar 折叠分组**：首页 / ▼ 工具入口 / 设置（disabled）/ 更新日志
3. **Tool card 去副标题 + 尺寸对齐 best.html `.quick`**：138×104，icon 24px

### v3.1.2 — 响应式 + Apple Design 动效（commit 0e6f3635981e）

3 次迭代提交（c6919183 / 91431feb / c87251f / 0e6f3635）：

**1. 响应式 5 断点（c6919183 + 91431feb）**

| 断点 | 关键变化 |
|---|---|
| `≤1440` | 主区 padding 28/32，dashboard-grid 1.32/.82/1fr |
| `≤1280` | 主区 26/28，metric-grid gap 12 |
| `≤1024` | 主区 24/24，metric→3 列，dashboard→2 列（feedback 跨2），tool-card 128→104 |
| `≤800` | 侧栏→72px（图标 only），metric→2 列，dashboard→1 列 |
| `≤480` | tool-card→2 列（手机） |

流体排版：`clamp(22px, 2.4vw, 32px)`（greeting h1）+ `clamp(24px, 2.8vw, 32px)`（metric-value）。

**2. Apple Design 动效（c6919183）**

| 规范 | 实现 |
|---|---|
| §1 Response（按下反馈） | `:active{transform:scale(.97)}` + 100ms |
| §4 Springs（弹性曲线） | `cubic-bezier(.2,.8,.2,1)` 统一过渡 |
| §7 Spatial（错落入场） | `@keyframes fade-up` 8px→0，.55s，metric 0/50/100/150ms → tool-card 180/230/280/330ms |
| §14 Reduced motion | 默认尊重 `prefers-reduced-motion` |

**3. 抄 best.html 交互 + tool-card 调方块（91431feb / c87251f / 0e6f3635）**

| 修复 | 改动 |
|---|---|
| sidebar hover 看不到白 | sidebar 背景 `.94/.82` → `.58/.42`，hover 改 `#fff` + 阴影（明显加深） |
| tool-card hover 弹不起 | 入场动画 `fade-up` 的 `animation-fill-mode:both` + `transform:translateY(0)` 永远覆盖 hover 的 `translateY(-3px)`（CSS 规范：animation 永远比 transition 优先）；改成 `fade-in` 只动 opacity，transform 留给 hover |
| tool-card 改方块 | 108×108 → 128×128（≤1024 断点 120×120），gap 14，radius 18 |
| 删冗余副标题 | 去掉「点击「进入」启动并跳转」 |

---

## 10. VM 部署实战（2026-08-17，Mecha）

### 10.1 部署结果

✅ 9 项验收全过。已部署服务：

| systemd 名 | 端口 | 状态 | 用户 | 用途 |
|---|---|---|---|---|
| `portal.service` | 8001 | active+enabled | root | 中台路由页 |
| `ideon.service` | 8501 | active+enabled | opsuser | content-rank（已加 `/content-rank` baseUrlPath） |
| `traffic-library.service` | 8002 | active+enabled | opsuser | 图书馆（23 条日报数据完好） |

### 10.2 实战教训（重点，避免其他 VM 复现）

**A. portal.service PATH 模板必须修正**（对应 bug #6）

原模板：
```ini
Environment="PATH=/opt/ideon/portal/venv/bin"
```

只留 venv → `shutil.which("systemctl")` 找不到 `/usr/bin/systemctl` → `HAS_SYSTEMCTL` 判 False → 全部工具走本地 dev 模式误报 not_installed。

修正后：
```ini
Environment="PATH=/opt/ideon/portal/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
```

⚠️ ori 本地 `ideon-portal/` 项目里的 `portal.service` 模板同步改完才能打新部署包。

**B. nginx `/library/` 反代需要前缀剥离**（对应 bug #7）

图书馆前端用绝对路径引用 `/static/...`，反代若没保留前缀会 404。Mecha 已加：
- `proxy_set_header Host $host;`
- `location /static/` 直通

### 10.3 .bak 文件清单（ori 决定何时清理）

| 路径 | 说明 |
|---|---|
| `/opt/ideon/bak.8502-old-20260817.tar.gz` | 老 8502 备份，140MB |
| `/opt/ideon/portal.bak.20260817/` | 完整 portal 代码 |
| `/etc/systemd/system/portal.service.bak.20260817` | portal.service 备份 |
| `/etc/systemd/system/ideon.service.bak.20260817` | ideon.service 备份 |
| `/etc/nginx/sites-available/ideon.bak.20260817` | nginx 配置备份 |

### 10.4 日志路径

- `/var/log/ideon/portal.log` + `portal.err`
- `/var/log/ideon/traffic-library.log` + `traffic-library.err`

### 10.5 Mecha 浏览器实测（2026-08-17，ori 转述）

✅ 4 项全过，**包括中台控制能力验证**（stop → inactive → start → active），按需启停省内存机制完全生效。

| 访问地址 | 内容 | 状态 |
|---|---|---|
| `https://ideon.park.mcd.ai/` | 中台路由页（ideon 内容智能中台，5 卡片 + 启停控制） | ✅ 200 |
| `https://ideon.park.mcd.ai/content-rank/` | 内容排行榜（底层 ideon.service @8501） | ✅ 200 |
| `https://ideon.park.mcd.ai/library/` | 图书馆（日报归档，traffic-library @8002） | ✅ 200 |
| 中台 `POST /api/stop` 图书馆 → `inactive` → `POST /api/start` → `active` | 验证中台通过 systemctl 真实控制 opsuser 服务 | ✅ |

完整布局：

```
ideon.park.mcd.ai
├── /                → 中台路由 ✅（5 卡片，启停控制）
├── /content-rank/   → 内容排行榜 ✅（运行中）
├── /library/        → 图书馆 ✅（运行中）
├── /copy-analyzer/  → 文案解析（占位，未部署）
├── /reach-trend/    → 触达趋势（占位，未部署）
└── /ctr-predictor/  → CTR 预测（占位，未部署）
```

⚠️ **闲置 30 分钟自动停机制**：中台设了闲置 30 分钟自动停。页面挂机超过 30 分钟工具会被自动停——这是 ori 的设计省内存，**不是故障**。

---

## 11. 明日计划（2026-08-18+）

### 11.1 文件位置（重要）

handoff 已从 `C:\Users\a952462\dev-handoff-v2.md` 移到项目目录：

```
C:\Users\a952462\ideon-portal\
├── dev-handoff-v2.md            ← 当前主版本（v2.2）
├── DEPLOY-HANDOFF.v2.1.bak.md   ← 早期 v2.1 归档（不再维护）
├── README.md
├── portal.service                ← PATH 已修（v2.2 实战教训）
├── app.py / config.py
├── templates/ / logs/
└── ...
```

**后续 handoff 迭代都在 `ideon-portal/dev-handoff-v2.md` 一份上做，别再放根目录。**

### 11.2 ori 明天继续

- [ ] 浏览器实测确认无视觉/交互异常（Mecha 提示它没法用浏览器）
- [ ] §10.3 .bak 文件清理决策
- [ ] 中台视觉验收（金拱 SVG / #FFBA0D / Heroicons / 侧栏 #2A2A2A）
- [ ] 决定先推哪个新工具的部署（copy-analyzer / reach-trend / ctr-predictor）

### 11.3 新工具部署时的两个避坑要点（来自 §10.2 实战教训）

- ⚠️ systemd 模板**必须保留完整系统 PATH**（bug #6 教训），不能只留 venv，否则 `shutil.which("systemctl")` 找不到，全部误报 not_installed
- ⚠️ nginx `/{tool}/` 反代按 bug #7 模板：加前缀剥离 + `/static/` 直通路由，否则静态资源 404

### 11.4 长期待办（详见 §8）

- [ ] SQLite 备份 cron（每天 sqlite3 .backup）
- [ ] 日志轮转（logrotate 给 `/var/log/ideon/*.log`）
- [ ] 工具定期回调 `/touch-access/{key}` 续闲置计时（现在只算 `/open/` 点击）
- [ ] 中台加更新日志面板
- [ ] 用户认证：问 IT 有没有 SSO / OIDC

---

## 9. 联系方式

- ori 在家远程，所有部署 / SSH 操作都在 VM AI 上做
- 中台代码由 ori 打包提供，VM AI 部署
- 图书馆源码来自 ori 本地 OneDrive，**不要重新生成**
- 任何阻塞问题先记下，别瞎猜

---

文档结束。