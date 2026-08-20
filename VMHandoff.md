# IDeon 项目全流程 Handoff（content-rank 内容排行榜 + 图书馆）

> 撰写：Mecha（VM AI）｜生成日期：2026-08-20
> 范围：从最早 Kevin 发来压缩包 → 现在线上稳定运行，完整时间线 + 所有踩过的坑
> 机器：`ideon.park.mcd.ai`（10.126.29.125，Ubuntu 24.04.4 LTS，kevinguo-ubuntu-jvpp）
> 主交接文档（持续维护）：`/opt/ideon/portal/DEPLOY-HANDOFF.md`（现 v2.4）
> 本文件 = 全流程复盘 + 交接，是 DEPLOY-HANDOFF.md 的补充阅读。

---

## 0. 一句话总结

两个项目从 ori 本地开发的压缩包，部署到公司内网 `https://ideon.park.mcd.ai`：**内容排行榜（content-rank，Streamlit）** + **图书馆（traffic-library，日报归档）**，外加一个 FastAPI **中台（portal）** 做按需启停路由管理。中间踩了 PATH、nginx 前缀、WebSocket Host、模板缓存 4 大类坑，均已修复并沉淀成"铁律"。

---

## 1. 项目角色速查

| 名称 | 是什么 | 端口 | systemd 服务 | 访问路径 |
|---|---|---|---|---|
| **中台 portal** | FastAPI 路由 + 5 工具启停管理 | 8001 | `portal.service`（root） | `https://ideon.park.mcd.ai/` |
| **内容排行榜 content-rank** | Streamlit 内容评分排名（mcd-content-rank） | 8501 | `ideon.service`（opsuser） | `https://ideon.park.mcd.ai/content-rank/` |
| **图书馆 library** | FastAPI 日报归档，网盘感按日历浏览（mcd-report-archive） | 8002 | `traffic-library.service`（opsuser） | `https://ideon.park.mcd.ai/library/` |
| 待部署 3 个 | copy-analyzer / reach-trend / ctr-predictor（Streamlit） | 8502-8504 | 未建 | 占位显示"未部署" |

**重要命名**：图书馆 = 流量库 = mcd-report-archive，三个名字是同一个项目，UI 显示 **"图书馆"**。

---

## 2. 完整时间线

### Phase 0 — 压缩包时代（2026-08-11 ~ 08-14，ori 本地开发）

- **08-11**：内容排行榜项目源码（`mcd-content-rank-main.7z`）首次出现，内容源起 ori 的 GitHub 仓库 `ori-yin/mcd-content-rank`
- **08-14 16:50**：Kevin 通过企微发来 `mcd-content-rank-main.7z`（3.6MB）→ 解压到 `/tmp/ideon-deploy/mcd-content-rank-main/`
- 同一时间线，ori 在本地（Windows）完成了**图书馆**（mcd-report-archive）和**中台**（ideon-portal）的开发：
  - 图书馆从 OneDrive 迁到 `C:\projects\mcd-report-archive`（避开 OneDrive 文件锁）
  - 中台在本地 8001 跑通，图书馆 8002 经中台自动启动联调通过
  - 项目全流程遵循 spec → plan → todo → implement 的 spec-driven 开发

### Phase 1 — 单应用首部署（2026-08-14，内容排行榜上线）

- 证书：Kevin 发来 `park_mcd_ai.zip`（`*.park.mcd.ai` DigiCert 通配证书，2026-04-02 ~ 2026-10-17 有效）
  - 证书链 `/etc/nginx/ssl/ideon.park.mcd.ai.crt` + 私钥 `.key`（root:root 600）
- Nginx 配 HTTPS：HTTP 80 → 301 → HTTPS 443，原 default 配置备份 `default.bak-20260814`
- 部署内容排行榜：`/opt/ideon/`，Python 3.12 venv + streamlit 1.61.1 / pandas 3.0.5 / numpy 2.5.2 / openai 3.0.0 / openpyxl 3.1.5
- systemd `ideon.service` 监听 127.0.0.1:8501，自启+自动重启
- **首轮验收通过**：https 200 ✅ / `_stcore/health` ✅ / WS 握手 200 ✅
- ⚠️ 此时是**全站直跑内容排行榜**（无中台，无图书馆），8501 直接对外

### Phase 2 — 中台 + 图书馆三件套部署（2026-08-17）

- **15:02** Kevin 发来 3 个文件（本次部署的"启动包"）：
  - `VM-AI-DEPLOY-PROMPT.md`（部署任务书）
  - `ideon-portal.zip`（21KB，中台）
  - `mcd-report-archive.zip`（400KB，图书馆）
- 按依赖顺序 6 步执行（见 §3 详细坑）：
  1. 清理老 8502 实例（`/tmp/mcd-content-rank` 备份为 `bak.8502-old-20260817.tar.gz`）
  2. 部署中台 → `/opt/ideon/portal/`，venv + systemd enable
  3. content-rank 改路径：ExecStart 加 `--server.baseUrlPath=/content-rank`
  4. 部署图书馆 → `/opt/ideon/traffic-library/`，venv + systemd enable，`python -m app.init_db`
  5. 改 nginx 路径分流
  6. 关闭 0.0.0.0 暴露，全部改 127.0.0.1
- 三个服务 active+enabled，HTTPS 全 200，23 条日报数据完好
- **20:40 全链路闭环确认**：验证"点进入→自动拉起"：`/open/content-rank` 和 `/open/library` 都能 303 拉起并 200

### Phase 3 — 图书馆 always-on + 隐藏入口（2026-08-18）

- Kevin 需求：图书馆长期在线，不参与 30 分钟闲置回收；中台路由页隐藏图书馆入口
- 改动 `/opt/ideon/portal/`：config.py 加 `persistent: True` + `hidden: True`；app.py 的 idle_checker 跳过 persistent；build_cards 过滤 hidden；index.html 移除入口
- 备份 `*.bak.20260818_104050`
- **同日第 2 轮**：同事报障"左侧日期看不到、部门筛选用不了、拖不上传"
  - 根因 1：前端 JS `fetch('/api/...')` 不带 `/library/` 前缀 → nginx 路由到中台 8001 → 404
  - 根因 2：文件已改但服务 `auto_reload=False` → 线上跑旧模板
  - 修复：JS 加 `/library/` 前缀 + 重启 traffic-library.service
- **遗留**：`/content-rank/`（8501）此时 502 挂掉，进程没跑

### Phase 4 — content-rank 预置数据 + WebSocket Host 修复（2026-08-19）

- **需求**：把 `cnn0818.xlsx`（1081 行，7/22~8/18，4 渠道：APP Push/短信/企微 1v1/微信小程序订阅，含 Message ID）作为临时 `/content-rank/` 数据源
- app.py 加「预置数据」逻辑：首次访问自动加载（clean_raw_xlsx 清洗），上传自定义文件后以上传为准，mtime 指纹触发重载
- **WebSocket 修复（本阶段最大坑）**：见 §4 第 4 条
- DEPLOY-HANDOFF.md 升级到 v2.4，§6 checklist 加 WS 101 验证项

### 当前状态（2026-08-20）

| 服务 | 状态 | 备注 |
|---|---|---|
| portal（8001 中台） | ✅ active + enabled | root 跑 |
| traffic-library（8002 图书馆） | ✅ active + enabled | always-on，不回收 |
| ideon（8501 content-rank） | ⚠️ inactive（按需） | 闲置自动停 = 设计如此；`/open/content-rank` 点击自动拉起 |

---

## 3. 部署架构（终版）

### 3.1 路由（nginx `/etc/nginx/sites-available/ideon`）

```
HTTP 80            → 301 HTTPS
/                  → 127.0.0.1:8001   中台首页
/api/  /open/      → 127.0.0.1:8001   中台 API + 跳转
/content-rank/     → 127.0.0.1:8501   内容排行（Streamlit + WebSocket）
/library/          → 127.0.0.1:8002   图书馆（rewrite 剥离前缀）
/static/           → 127.0.0.1:8002   图书馆静态资源
其余 /             → 127.0.0.1:8001   兜底回中台
```

### 3.2 启停机制（中台自带，非平台策略）

- 中台 `idle_checker()` 每 60s 扫描，闲置 > `IDLE_TIMEOUT_MINUTES=30`（config.py）的工具被 `systemctl stop`
- `persistent: True` 的工具豁免（图书馆）
- 点"进入" `/open/{key}` → 自动 systemctl start → 轮询 30s → 跳转
- **content-rank 现在 inactive 是正常的**（闲置回收生效），不是故障

### 3.3 systemd 要点

| 服务 | User | 关键 ExecStart |
|---|---|---|
| portal | root | `uvicorn app:app --host 127.0.0.1 --port 8001 --workers 1` |
| ideon | opsuser | `streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true --server.baseUrlPath=/content-rank --browser.gatherUsageStats false` |
| traffic-library | opsuser | `uvicorn app.main:app --host 127.0.0.1 --port 8002 --workers 1` |

---

## 4. 踩过的所有坑（重点！按时间序）

### 坑 1：portal.service PATH 被覆盖 → 工具全显示 not_installed（08-17）

- **现象**：中台页面 5 个工具全显示"未部署"
- **根因**：`Environment="PATH=/opt/ideon/portal/venv/bin"` 把 PATH 覆盖成只有 venv → 进程内 `shutil.which("systemctl")` 找不到 → `HAS_SYSTEMCTL=False` → 误走本地开发模式
- **修法**：PATH 改为 `venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`
- **教训**：systemd 里 `Environment=PATH=...` 是**覆盖**不是追加；要 systemctl 的服务必须带全系统 PATH。✅ 已同步建议 ori 更新模板

### 坑 2：nginx `/library/` 前缀没剥离 + 静态资源 404（08-17）

- **现象**：`/library/` 打开 404，静态资源 404
- **根因 1**：FastAPI 只认 `/` 不认 `/library/` → 必须 `rewrite ^/library/(.*)$ /$1 break;`
- **根因 2**：图书馆前端用绝对路径 `/static/...` → 必须补 `/static/ → 8002` 路由
- **教训**：反代子路径应用时，前缀剥离 + 静态资源路由两件事必须一起做

### 坑 3：`auto_reload=False` 模板缓存 → 线上跑旧版（08-18）

- **现象**：同事报障图书馆 JS 全 404（fetch 不带前缀）
- **根因**：文件 10:53 已改好，但服务 10:17 启动，`auto_reload=False` → 线上跑旧模板
- **修法**：`systemctl restart traffic-library.service`
- **教训**：改模板/JS 后**必须重启服务**才生效；改完要 curl 验证渲染后 HTML；改 index.html 后必须 grep 复查落盘（曾出现"工具显示成功但实际没写进去"）

### 坑 4：nginx 缺 Host header → Streamlit WebSocket 1008 拒绝（08-19，最重要）

- **现象**：`/content-rank/` 页面能加载但卡死转圈，WS 反复断开
- **根因**：`/content-rank/` location **缺 `proxy_set_header Host $host;`**（对比 `/`、`/api/` 段都有）→ 反代到 8501 时 Host 回退成 `127.0.0.1:8501`
- **机制**：Streamlit 校验 WS Origin/Host（`starlette_websocket.py:_is_origin_allowed`）：origin=`https://ideon.park.mcd.ai` vs host=`127.0.0.1:8501` 不一致 → **1008 Policy Violation**，日志报 `Rejecting WebSocket connection with disallowed Origin or Host header`
- **修法**：补全 `Host $host` + `X-Real-IP` + `X-Forwarded-For` + `X-Forwarded-Proto`
- **🔒 铁律**：**凡是 Streamlit / 需要 WebSocket 的 location，必须显式带全 4 个 header：`Host $host` + `Upgrade $http_upgrade` + `Connection "upgrade"` + `X-Forwarded-Proto $scheme`。缺 Host 必挂。**
- **验证方法**（防再犯）：`curl -sk -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: SGVsbG9Xb3JsZDEyMzQ1Ng==" -H "Origin: https://ideon.park.mcd.ai" "https://ideon.park.mcd.ai/content-rank/_stcore/stream"` → 必须 `HTTP/1.1 101 Switching Protocols`（200 HTML = Host 缺失被拒）

### 坑 5（ori 本地侧，参考）：OneDrive 文件锁 / starlette 版本 / 端口占用

- 图书馆源码**不要放 OneDrive**（文件锁导致 .bat 闪退），已迁 `C:\projects\mcd-report-archive\`
- starlette 1.2.1 `Jinja2Templates` 报 `unhashable dict` → 用 jinja2 直渲染，**别改回 Jinja2Templates**
- 端口 8000 可能被占 → 用 8001/8002

---

## 5. 当前架构的设计决策（为什么这样）

| 决策 | 原因 |
|---|---|
| 5 个工具按需启停，不常驻 | 15GB 内存紧张，全开 1~1.5GB / 按需 200~600MB |
| 图书馆例外 always-on | Kevin 需求：长期在线，30 分钟没人访问也不停 |
| 中台 root、工具 opsuser | 中台要 systemctl 调启停；工具不需要 |
| 中台监听 127.0.0.1:8001 | 只让 nginx 访问，所有流量过 nginx |
| content-rank 卡片聚合 = 1 Plan × 1 Message | 同文案按 Unit 拆分后投放，不合并会重复占榜、CTR 被误读 |
| `--server.baseUrlPath=/content-rank` | 让 Streamlit 在中台子路径前缀下工作 |

---

## 6. 常用运维命令

```bash
# 服务状态
systemctl status portal ideon traffic-library
systemctl is-active portal ideon traffic-library

# 重启 / 看日志
sudo systemctl restart ideon            # 内容排行榜
sudo journalctl -u ideon -f             # 实时日志
sudo journalctl -u ideon --since today | grep -i reject   # 查 WS 被拒

# nginx
sudo nginx -t && sudo systemctl reload nginx

# 中台 API 调试
curl -s http://127.0.0.1:8001/api/status | python3 -m json.tool
curl -s http://127.0.0.1:8001/api/debug/redirect/library
```

---

## 7. 待办 / 下一阶段

- [ ] 其他 3 个 Streamlit 工具部署（copy-analyzer / reach-trend / ctr-predictor），模板见 DEPLOY-HANDOFF.md §3.5
- [ ] SQLite 备份 cron（每天 `sqlite3 .backup` portal.db / archive.db）
- [ ] 日志轮转（logrotate 给 `/var/log/ideon/*.log`）
- [ ] 工具定期回调 `/touch-access/{key}` 续闲置计时（现在只算 `/open/` 点击）
- [ ] 用户认证：问 IT 有没有 SSO / OIDC
- [ ] ⚠️ 内容排行榜目前无常驻进程（闲置回收），入口走中台 `/open/content-rank` 自动拉起；如需求改为 always-on，参考图书馆在 config.py 加 `"persistent": True`

---

## 8. 备份清单（ori 决定何时清理）

```
/opt/ideon/bak.8502-old-20260817.tar.gz        (老 8502 实例备份)
/opt/ideon/portal.bak.20260817/                (portal 代码完整备份)
/etc/systemd/system/portal.service.bak.20260817
/etc/systemd/system/ideon.service.bak.20260817
/etc/nginx/sites-available/ideon.bak.20260817
/etc/nginx/sites-available/ideon.bak.20260819.pre-fix
/opt/ideon/portal/{config,app}.py.bak.20260818_104050 + templates/index.html.bak
/opt/ideon/app.py.bak.20260819_contentrank
```

---

## 9. 联系方式 / 分工

- **ori**：项目原作者，在家远程；所有部署 / SSH 操作在 VM AI 上做；中台 + 图书馆源码打包提供，**不要重新生成代码**
- **VM AI（Mecha）**：本机部署、运维、排障；所有服务器改动以本文件 + DEPLOY-HANDOFF.md 为准
- **Kevin / 相关同事**：需求方，通过企微下发需求

---

*文档结束。每次迭代，请同步更新 `/opt/ideon/portal/DEPLOY-HANDOFF.md` 的 §5.5 变更日志。*
