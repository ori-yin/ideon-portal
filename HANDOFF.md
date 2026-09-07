# ideon-portal handoff (2026-09-07)

## 当前状态
- v3.4：内容工坊（/studio）+ 历史洞察（/insights）从 mcd-ai-content-platform/web 迁过来，sub-app include_router；LLM 走 portal 自己的 ~/.ideon-portal/llm_settings.yaml
- 6 可见工具：content-rank / reach-trend / copy-analyzer / ctr-predictor / studio / insights
- 0 external（不再跳 8530）
- 1 hidden：library
- **portal.service 不要 main/full 同步**（main 是 v2.2 PATH 修复版，full 是 VM 原版）

## 启动
```bash
cd "C:\Users\a952462\OneDrive - ATOS\桌面\ideon-portal-main"
python app.py   # → http://127.0.0.1:8001
```

## 设计参考
- 规范：`OneDrive\桌面\设计参考\designUIv3.md`（Calm Intelligence）
- 样例：`OneDrive\桌面\设计参考\best.html`
- 金拱 SVG：`c:\ideon\元素\mcdonalds.svg`（金黄 `#FFC72C`，**别改红**）

## 关键 API
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

## 文件结构
```
app.py                 (15 routes + 3 LLM API + 1 include_router)
config.py              (6 tools + library hidden)
llm_config.py          (LLM 配置 + probe_llm + LLM_PROVIDERS×2 麦当劳AI网关+MiniMax)
requirements.txt       (fastapi / uvicorn / jinja2 / openai / anthropic)
portal.service         (v2.2 PATH 修复版，**不同步**)
static/loading.gif
static/css/style.css   (v3.4 覆盖：mcd-ai 风格，给 /studio /insights 用)
static/img/mcdonalds.svg (v3.4 覆盖：mcd-ai 金拱 SVG)
static/portal.css      (portal 自己的苹果风，给 / 用)
templates/
  index.html           (v3.3 苹果风首页)
  loading.html         (浅玻璃中转)
  partials/settings_llm_modal.html
  partials/llm_pill.html
web_content/           (v3.4 新增：mcd-ai web 层迁移)
  app.py               (APIRouter + 8 endpoint: /studio + 4 studio API + /insights + 2 insights API)
  state.py             (S_01-S_05 内存 state，含 df_registry)
  templates/
    base.html          (mcd-ai 风格 base：侧栏 + topbar)
    pages/01_内容工坊.html
    pages/04_历史洞察.html
    _insights_tab_block.html
    partials/01_candidates.html + 01_right_column.html
    partials/04_*.html (7 个 tab：rank/wf/ef/tl/sim/daily/owner)
    partials/llm_pill.html
  static/css/style.css
  static/img/mcdonalds.svg
services/ai_content/   (业务层：core services adapters prompts config，含 ProviderRouter 类)
  core/llm_gateway.py  (注意：ProviderRouter 白名单只接 minimax/openai/siliconflow/qianfan，
                        web_content 不用它，自己实现 _PortalRouter 走 portal 的 base_url)
tools/push_via_api.py  (github.com 被墙时走 api.github.com 推)
```

## v3.3 (2026-09-07) 改动
| 文件 | 改了什么 |
|---|---|
| `app.py` | LLM test/save 改 JSON 返回（成功关 modal / 失败 detail）；test 失败 stderr 打印方便 debug |
| `config.py` | `studio` icon `wand-sparkles` → `sparkles` |
| `llm_config.py` | `LLM_PROVIDERS` 砍到 3 个（麦当劳AI网关 / MiniMax / 自定义走模板） |
| `requirements.txt` | 加 `openai>=1.0.0` `anthropic>=0.30.0`（之前漏装，probe_llm 直接 ImportError） |
| `templates/index.html` | 工具卡 `target="_blank"`；`activity-icon` 40×40 + 内部 20×20 跟 metric 同款 |
| `templates/partials/settings_llm_modal.html` | test/save 都走 fetch+JSON 不重渲；切 provider 自动填/清 model；保存成功关 modal，失败 form 内小红字；去掉 3 个信息块（modal subtitle / masked_key / modal-foot）+ saved banner + errors banner |

## v3.4 (2026-09-07) 改动 — 内容工坊 + 历史洞察迁移
**目标**：把 mcd-ai-content-platform/web 的内容工坊（/studio）+ 历史洞察（/insights）从 8530 端口外跳改成 portal 内嵌 sub-app。

**Sub-app 架构**：FastAPI `include_router`，web_content/app.py 用 APIRouter 隔离 8 个 endpoint。
业务层 Python 已在 portal `services/ai_content/`，web_content 只搬 web 层（路由 + HTML + 静态资源）。

| 文件 | 改了什么 |
|---|---|
| `web_content/`（新） | app.py（精简 2027→880 行，删诊断/批量/反馈/settings/llm-modal/health/warmup/main）+ state.py + templates/（base.html + 2 page + 10 partials）+ static/（CSS + SVG） |
| `app.py` | + `from web_content.app import router as content_router`；+ `app.include_router(content_router)` |
| `config.py` | studio/insights: `type=external` → `type=internal`；`path_prefix` `http://localhost:8530/x` → `/x`；删 `dev_port: 8530` |
| `templates/`（D） | 删半成品：`studio_old8530.html` / `base_8530.html` / `studio.html` / `insights.html` / `partials/01_*.html` × 2 / `partials/02_*.html` × 4 / `partials/studio_right.html` / `partials/llm_pill_8530.html` |
| `static/` | `style_8530.css` 删；`style.css` + `mcdonalds.svg` 被 web_content 真版覆盖 |
| `web_content/app.py` 路径处理 | sys.path 双挂 portal 根 + `services/ai_content`，业务模块内部 `from core/services/adapters/prompts` 相对 import 才能 work（不能改成 portal 风格，否则 namespace package `services.ai_content` 会被 Python 错误合并） |
| `web_content/app.py` LLM | 新增 `_PortalRouter` 类（绕开 `services.ai_content.core.llm_gateway.ProviderRouter` 的 provider 白名单限制 — portal 允许任意中文 provider + 自定义 base_url）；`_build_llm_router()` 恢复（之前误以为是死代码删了，导致 generate 500，已恢复） |

**踩坑**（下次接手不要重蹈）：
1. **namespace package 陷阱**：`from services.ai_content.xxx` 看似合理，但因为 portal/services/ 也有同名目录 + services/ai_content/ 也有 services 子目录，Python namespace package 自动合并 path，导致 `import services` 找到的是 ai_content/services/，`services.ai_content` 找不到 → **业务模块内部保留 mcd-ai 风格的 `from core.xxx` 相对 import**（依赖 sys.path 注入 ai_content 根）
2. **`_build_llm_router` 不是死代码**：第一版我以为只有诊断/批量用了它，就删了，结果 `/api/studio/generate` 还在用 → POST 500（NameError）。**所有 mcd-ai 页面用 `router.call(prompt)` 都依赖这个函数**，必须保留
3. **ProviderRouter 白名单**：`core/llm_gateway.ProviderRouter` 只接 `minimax/openai/siliconflow/qianfan`，portal 的 LLM 允许任意中文 provider（"麦当劳AI网关"）+ 自定义 base_url → web_content 自己实现 `_PortalRouter` 走 portal 配置的 protocol 字段
4. **portal 半成品 style.css 覆盖**：portal/static/css/style.css 是 8530 抄的半成品，被 web_content/static/css/style.css 覆盖后正好；但 portal/static/portal.css 不动（portal 首页用 portal.css，studio/insights 用 style.css，两套独立）

## 已知坑
- Windows 上 `/api/recent` 永远 `[]`（DB_PATH 是 Linux 路径，UI fallback "暂无访问记录"）
- Windows 上点 4 个主工具都跳 `?need_start=xxx`（没配 dev_cmd，只有 library 配 8002），VM 上正常
- portal 重启才生效（pip 装完老进程不重 import）
- 表单切 provider 时 base_url 自动覆盖、model 自动填（单 model）或清空（多 model），但 api_key 不自动填（密码框永远不预填）—— 用户必须手动清掉重输
- **v3.4 UI 风格分裂**：portal 首页走 `portal.css`（苹果风 designUIv3）；点 studio/insights 进 mcd-ai 风格（侧栏 240px + topbar）。两套独立 CSS 互不影响。要统一得重写 20+ partials，工作量大
- **v3.4 ai_content 业务模块内部 import 不要动**（见踩坑 #1），改业务代码时只能改实现，别改 `from core/services/adapters/prompts` 路径

## 待办
1. `/changelog` 页面（sidebar 入口已加，404）
2. 5 个新工具
3. 工具卡片 hover micro-interaction
4. ~~清理从 8530 抄过来的半成品~~ ✅ v3.4 完成
5. **新增**：UI 风格统一（把 studio/insights 也套 portal.css；或反之把 portal 首页套 mcd-ai 风格）
6. **新增**：mcd-ai 进程是否还要保留？web_content 迁完后 8530 没用了，但要确认用户没有外部脚本依赖 `http://localhost:8530/`（如有要改 `.env` 或 systemd unit）

## UX 规则（用户面向 = 内部分析师/运营）
- 别给看"设计语言 v3"这种技术元信息
- UI 不要 emoji（用 lucide SVG）
- 改配色：grep 颜色变量 → 批量替换
- 改 HTML：先 Read 整段再改；改文件名走 grep → Edit
- 改 LLM 配置：portal 走 `~/.ideon-portal/llm_settings.yaml`（**不与 mcd-ai 共享**）

## 推送（github.com 被墙时）
```bash
cd "C:\ideon\ideon-portal-main"
# 1) commit
git add -A && git commit -m "v3.4: 内容工坊 + 历史洞察从 mcd-ai 迁过来（sub-app include_router）"
# 2) 走 api.github.com（脚本里 TOKEN/REPO 已写死，更新 REMOTE_HEAD/REMOTE_TREE 即可）
python tools/push_via_api.py
```
