# ideon-portal handoff (2026-09-07)

> 中台与子项目是**并列关系**，互不依赖：
> - 本中台只负责**路由 + 启停 + LLM 配置**，不嵌任何业务代码
> - 每个工具都是 `C:\ideon\` 下的独立项目，独立端口，独立 git 仓库
> - 中台 HANDOFF **不写**子项目内部文件；子项目 HANDOFF **不写**中台内部细节

---

## 当前状态

- **架构**：FastAPI 中台（8001），每个工具独立运行在各自端口；中台只做 ① 主页卡片展示 ② `/open/{key}` 启进程 + 跳新标签 ③ LLM 配置 modal
- **6 可见工具**（中台只列名 + 启停 + 跳转，不嵌代码）：

| 工具 | 子项目路径 | 端口 | 类型 |
|---|---|---|---|
| content-rank | `C:\ideon\mcd-content-rank\` | 8501 | Streamlit |
| copy-analyzer | `C:\ideon\mcd-copy-analyzer\` | 8502 | Streamlit |
| ctr-predictor | `C:\ideon\mcd-ctr-predictor\` | 8503 | Streamlit |
| reach-trend | `C:\ideon\mcd-reach-trend\` | 8504 | Streamlit |
| studio / insights | `C:\ideon\mcd-ai-content-platform\` | 8530 | FastAPI（独立 web 层，子项目自己维护） |
| library | `C:\ideon\mcd-report-archive\` | 8002 | FastAPI（hidden，always-on） |

- **portal.service 不要 main/full 同步**（main 是 v2.2 PATH 修复版，full 是 VM 原版）
- **LLM 配置现状**：中台自己的 `~/.ideon-portal/llm_settings.yaml`（**只 portal 用，不与子项目共享**）。其他子项目各自有独立配置。**全局生效改造见待办 #1**

---

## 启动

```bash
cd "C:\Users\a952462\OneDrive - ATOS\桌面\ideon-portal-main"
python app.py   # → http://127.0.0.1:8001
```

---

## 设计参考

- 规范：`OneDrive\桌面\设计参考\designUIv3.md`（Calm Intelligence）
- 样例：`OneDrive\桌面\设计参考\best.html`
- 金拱 SVG：`c:\ideon\元素\mcdonalds.svg`（金黄 `#FFC72C`，**别改红**）

---

## 关键 API（中台自己用）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/` | 主页 |
| GET/POST | `/open/{key}` | 启服务 + 跳转（target=_blank，工具卡都新标签） |
| GET | `/loading/{key}` | 中转页（GIF + 自动跳） |
| GET | `/api/status` | 所有工具状态 |
| GET | `/api/summary` | total / running / opens / idle |
| GET | `/api/recent?limit=10` | 最近访问（Windows 永远 `[]`） |
| GET | `/api/settings/llm-modal` | LLM 配置 modal（HTMX partial） |
| POST | `/api/settings/llm/test` | 测连接 → `{ok, detail}` JSON |
| POST | `/api/settings/llm` | 保存 → `{ok}` JSON（成功关 modal，失败小红字） |
| GET | `/static/*` | 静态资源 |

---

## 文件结构（中台自己的文件）

```
app.py                 (15 routes + 3 LLM API；不 include_router 任何子项目)
config.py              (6 工具 + library hidden)
llm_config.py          (LLM 配置 + probe_llm + LLM_PROVIDERS×2 麦当劳AI网关+MiniMax)
requirements.txt       (fastapi / uvicorn / jinja2 / openai / anthropic)
portal.service         (v2.2 PATH 修复版，**不同步**)
static/loading.gif
static/css/style.css   (中台首页用)
static/img/mcdonalds.svg
static/portal.css      (portal 自己的苹果风，给 / 用)
templates/
  index.html           (苹果风首页)
  loading.html         (浅玻璃中转)
  partials/settings_llm_modal.html
  partials/llm_pill.html
tools/push_via_api.py  (github.com 被墙时走 api.github.com 推)
```

**红线**：
- 中台不 `include_router` 任何子项目
- 不 `import` 子项目业务模块
- 不复制子项目代码到中台

---

## v3.3 (2026-09-07) 改动

| 文件 | 改了什么 |
|---|---|
| `app.py` | LLM test/save 改 JSON 返回（成功关 modal / 失败 detail）；test 失败 stderr 打印方便 debug |
| `config.py` | `studio` icon `wand-sparkles` → `sparkles` |
| `llm_config.py` | `LLM_PROVIDERS` 砍到 3 个（麦当劳AI网关 / MiniMax / 自定义走模板） |
| `requirements.txt` | 加 `openai>=1.0.0` `anthropic>=0.30.0`（之前漏装，probe_llm 直接 ImportError） |
| `templates/index.html` | 工具卡 `target="_blank"`；`activity-icon` 40×40 + 内部 20×20 跟 metric 同款 |
| `templates/partials/settings_llm_modal.html` | test/save 都走 fetch+JSON 不重渲；切 provider 自动填/清 model；保存成功关 modal，失败 form 内小红字；去掉 3 个信息块（modal subtitle / masked_key / modal-foot）+ saved banner + errors banner |

---

## v3.4 (2026-09-07) — ⚠️ **架构错误尝试，已回滚**

**错误尝试**：曾尝试把一个子项目的 2 个 web 页面通过 `include_router` 内嵌到中台，做成 sub-app。**这是错的**：

- 中台不嵌业务代码，**架构红线被破坏**
- 子项目本来就有完整 web 层，复制到中台 = 两边维护同一份代码（后续升级会分裂）
- 由此引入 4 个本不该有的踩坑（namespace 冲突 / 关键函数误判为死代码 / 子项目白名单冲突 / CSS 文件覆盖）

---

## v3.5 (2026-09-07) — 回滚 v3.4 + 清理业务层副本

v3.4 错误的回滚已落地，分两个 commit：

### 6ff0413 — 回滚 v3.4 include_router

- `app.py` 撤 `from web_content.app import router as content_router` + `app.include_router(content_router)`
- `config.py` studio/insights `type=internal` → `external`，加 `dev_port: 8530` + `path_prefix=http://localhost:8530/{studio,insights}` + `external_blank: True`
- 删除 `web_content/` 整个目录（31 个文件，全部在 git 跟踪，可 `git checkout 7d61fa4 -- web_content/` 恢复）

### 15ed7a8 — 清理 services/ai_content 业务层副本

v3.2 init 时（commit `be62978`）带入的 mcd-ai 业务层副本，v3.4 用 `web_content/app.py` 当唯一调用者，v3.5 删 `web_content/` 后无引用方。

- 删 `services/ai_content/` 整目录（5 个子目录，75 个文件，660K 业务代码 + 228K data/）
- 删前已对比 `data/` 8 个文件（含 `lgbm_model_v1.pkl`）与 `mcd-ai-content-platform/data/` **8/8 字节级一致**，零风险
- `services/` 目录空 → rmdir

**架构教训**（v3.4 / v3.2 的根因相同，合并成 4 条）：
1. **中台不嵌业务**：子项目自己跑自己的 web 服务，中台只做导航 + 启停 + 配置
2. **代码不复制**：子项目升级 web 层时，中台不需要同步（避免双份维护漂移）
3. **配置不共享**：每个子项目自己管 LLM / DB / 配置；中台的 `~/.ideon-portal/llm_settings.yaml` 跟子项目无关
4. **不要为「整合」做架构妥协**：业务连贯 ≠ 进程合并；保持并列关系

**验证**：`py_compile` + `import app` 19 routes OK（15 中台 + 3 LLM API + static mount），`/studio` `/insights` 已从 portal 路由表移除；`llm_config.get_status()` 仍 `configured=True / MiniMax / MiniMax-M3 / has_key=True`（凭证未动）。

---

## 已知坑

- Windows 上 `/api/recent` 永远 `[]`（DB_PATH 是 Linux 路径，UI fallback "暂无访问记录"）
- Windows 上点 4 个主工具都跳 `?need_start=xxx`（没配 dev_cmd，只有 library 配 8002），VM 上正常
- 中台重启才生效（pip 装完老进程不重 import）
- 表单切 provider 时 base_url 自动覆盖、model 自动填（单 model）或清空（多 model），但 api_key 不自动填（密码框永远不预填）—— 用户必须手动清掉重输
- **UI 风格分裂**（已记录，不修）：中台首页走 `portal.css`（苹果风 designUIv3）；点 studio/insights 进去子项目自己的 web 层（侧栏 240px + topbar）。两套独立 CSS 互不影响。要统一得改子项目，工作量大且不属于中台

---

## 待办

1. **LLM 配置全局生效（2026-09-07 用户拍板，未做）**
   - 现状：每个项目独立配置 LLM，portal 配的只 portal 用；子项目要分别配
     - `~/.ideon-portal/llm_settings.yaml`（portal）
     - `~/.mcd-ai/llm_settings.yaml`（mcd-ai）
     - mcd-content-rank / mcd-copy-analyzer / mcd-ctr-predictor / mcd-reach-trend / mcd-report-archive 各自还有配置（散在项目目录或各自家目录）
   - 目标：在 portal 配一次 → 全局生效（其他子项目都能读）
   - 设计方向（待定，下次 session 决定）：
     - 方案 A：portal 写 `~/.ideon-portal/llm_settings.yaml`（已有），子项目改读这个路径 → 子项目零迁移成本，但要改子项目启动逻辑
     - 方案 B：portal 写一份**共享 canonical**（如 `~/.ideon/llm_settings.yaml`），所有子项目读这个 → 改 1 处写 + 改 N 处读（每个工具 1 行 llm_config.py 默认路径）
     - 方案 C：portal 配的时候同时**写入**所有子项目的配置位置 → 子项目代码 0 改动，但每次配置要写 N 份，容易漂移
   - 推荐 **方案 B**（单一权威源，子项目只读不改，配置漂移风险最低）
   - 不冲突"中台不嵌业务"红线：LLM 连接参数是**配置**不是业务代码

2. `/changelog` 页面（sidebar 入口已加，404）
3. 5 个新工具
4. 工具卡片 hover micro-interaction
5. ~~清理从 8530 抄过来的半成品~~ ✅ v3.4 回滚完成

---

## UX 规则（用户面向 = 内部分析师/运营）

- 别给看"设计语言 v3"这种技术元信息
- UI 不要 emoji（用 lucide SVG）
- 改配色：grep 颜色变量 → 批量替换
- 改 HTML：先 Read 整段再改；改文件名走 grep → Edit
- 改 LLM 配置：中台走 `~/.ideon-portal/llm_settings.yaml`（**不与子项目共享**）
- **改子项目的代码 → 跳到子项目目录去改，别在中台改**

---

## v3.4+ 推送状态（2026-09-07）

- **本地 3 commit 未推**：v3.3 / init 攒在本地未到远端（远端还停在 `d5ff87b`）。今天顺序推上 ori-yin/ideon-portal（push_via_api.py 改成顺序推保留历史）。
- **v3.4 不推**：v3.4 是错误尝试，已回滚，不入历史；中台回归 v3.3 + init 状态
- 推完远端 HEAD = init 或 v3.3 二选一（看哪个更稳）

---

## 推送（github.com 被墙时）

```bash
cd "C:\ideon\ideon-portal-main"
# 1) commit
git add -A && git commit -m "v3.3: 工具新标签 + LLM modal 简化 + provider 砍到 3 + activity-icon 跟 metric 同款"
# 2) 走 api.github.com（脚本自动拿远端 HEAD + 顺序推未推 commit 保留历史）
python tools/push_via_api.py
```