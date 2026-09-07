# ideon-portal handoff (2026-09-07)

## 当前状态
- v3.3：苹果风首页 + LLM modal（fetch+JSON，不重渲）+ studio icon 改 sparkles + activity-icon 跟 metric 同款
- 4 可见工具：content-rank / reach-trend / copy-analyzer / ctr-predictor
- 2 external 跳 8530：studio / insights
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
app.py                 (15 routes + 3 LLM API)
config.py              (5 tools + library hidden)
llm_config.py          (LLM 配置 + probe_llm + LLM_PROVIDERS×3)
requirements.txt       (fastapi / uvicorn / jinja2 / openai / anthropic)
portal.service         (v2.2 PATH 修复版，**不同步**)
static/loading.gif
templates/
  index.html           (v3.3 苹果风首页)
  loading.html         (浅玻璃中转)
  partials/settings_llm_modal.html
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

## 已知坑
- Windows 上 `/api/recent` 永远 `[]`（DB_PATH 是 Linux 路径，UI fallback "暂无访问记录"）
- Windows 上点 4 个主工具都跳 `?need_start=xxx`（没配 dev_cmd，只有 library 配 8002），VM 上正常
- portal 重启才生效（pip 装完老进程不重 import）
- 表单切 provider 时 base_url 自动覆盖、model 自动填（单 model）或清空（多 model），但 api_key 不自动填（密码框永远不预填）—— 用户必须手动清掉重输

## 待办
1. `/changelog` 页面（sidebar 入口已加，404）
2. 5 个新工具
3. 工具卡片 hover micro-interaction
4. 清理从 8530 抄过来的半成品（`templates/studio_old8530.html` / `base_8530.html` / `partials/01_*` / `02_*` / `static/css/style.css` / `static/img/mcdonalds.svg`）

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
git add -A && git commit -m "v3.3 ..."
# 2) 走 api.github.com（脚本里 TOKEN/REPO 已写死，更新 REMOTE_HEAD/REMOTE_TREE 即可）
python tools/push_via_api.py
```
