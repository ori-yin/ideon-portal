# ideon-portal 会话交接 (2026-09-04)

> 本次会话：**v3 UI 中性主版本大改**（main + full 同步）
> 下次 session 接续：从这里读起就能接手

---

## 0. 当前状态

| 维度 | 状态 |
|---|---|
| 设计语言 | **Calm Intelligence v3 中性主版本**（浅玻璃 + Primary Blue） |
| Logo | **麦当劳金拱 SVG inline**（`c:\ideon\元素\mcdonalds.svg`，fill `#FFC72C`） |
| 工具入口 | 白底 panel + best.html `.quick` 风格（浅灰卡片居中） |
| 路由页 | 4 个可见工具（content-rank / reach-trend / copy-analyzer / ctr-predictor） |
| Library | hidden=True 路由页不显示，API 仍可见 |
| main / full | **完全一致**，已双向同步 |

---

## 1. 设计规范来源（必读）

- **设计规范**：`OneDrive\桌面\设计参考\designUIv3.md`（"Calm Intelligence"，80% Apple + 20% Liquid Glass）
- **视觉样例**：`OneDrive\桌面\设计参考\best.html`（内容中台 dashboard，sidebar/nav/metric/quick/status-row/feedback 都从这抄）
- **金拱 SVG**：`c:\ideon\元素\mcdonalds.svg`（358B，单 path，viewBox `-40.605 -59.125 351.91 354.75`）

**用户面向**：内部分析师 / 运营。不需要看"设计语言 v3"这种技术信息（曾因此被骂，已删）。

---

## 2. 本次改动清单（main + full 都改了）

### 2.1 备份（回滚用）
```
main/templates/_bak/
├── index.html.v2-brand-20260904        (390KB, 旧 v2 品牌主题变体)
├── full-index-v2-brand-20260904.html
└── loading.html.v2-brand-20260904

full/_bak-app.py.v2-20260904            (15131B, 旧 app.py)
full/templates/_bak/
├── index.html.v2-brand-20260904
└── loading.html.v2-brand-20260904
```

### 2.2 文件改动
| 文件 | 改动 |
|---|---|
| `templates/index.html` | 390KB → **26KB**，重写为 v3 中性主版本 |
| `templates/loading.html` | 333KB → **3.6KB**，重写为 v3 浅玻璃风格 |
| `static/loading.gif` | 从 templates/ 移到 static/（新增 StaticFiles 挂载） |
| `app.py` | + `/api/recent` 路由 + `relative_time()` + `StaticFiles` mount |
| `portal.service` | **不动**（main 保留 v2.2 PATH 修复版，full 保留 VM 原版） |
| `config.py` | 上一轮已同步（reach-trend 移位 + library persistent+hidden） |

### 2.3 v3 设计要点（已落地的）
- **Sidebar**：224px / glass blur(30px) / 浅白背景 / 7 项 nav + 更新日志入口
- **Topbar**：「下午好，Admin 👋」+ 「LLM 已连接」pill + ♧ 通知（红点）+ A 头像（**没有**刷新按钮 ↻）
- **Metric**：4 列（不要 5 个 metric，第 5 个是设计语言信息不该给用户看）
- **工具入口**：白底 panel 包裹，内嵌 quick-grid（4 列自适应），工具卡浅灰背景居中
- **工具卡**：23px 蓝色图标 + 14px 标题 + 11px 描述 + status pill + 「进入」+「↻ 重启」按钮
- **Dashboard 3-col**：1.4fr .85fr 1fr（最近活动 / 系统状态 / 使用提示）
- **系统状态**：6 行 status-row（不要"设计语言: Calm Intelligence v3"）

### 2.4 工具图标 → 工具 key 映射
```html
content-rank  → ▣
reach-trend   → ↗
copy-analyzer → ✎
ctr-predictor → ⌁
library       → ▦
```

---

## 3. 启动方式

### Windows 本地
```bash
cd "C:\Users\a952462\OneDrive - ATOS\桌面\ideon-portal-main"
python app.py                          # → http://127.0.0.1:8001
```
依赖：`fastapi==0.115.0` / `uvicorn[standard]==0.32.0` / `jinja2==3.1.4`

### VM 部署
```bash
rsync -av full/ root@ideon.park.mcd.ai:/opt/ideon/portal/
ssh ideon.park.mcd.ai "systemctl restart portal.service"
# → https://ideon.park.mcd.ai
```
详见 `DEPLOY-HANDOFF.md`（v2.6，VM 部署流程）

---

## 4. 回滚方法（任意时候一行命令）

```bash
# main 回滚
cp main/templates/_bak/index.html.v2-brand-20260904 main/templates/index.html
cp main/templates/_bak/loading.html.v2-brand-20260904 main/templates/loading.html

# full 回滚（连 app.py 一起）
cp full/_bak-app.py.v2-20260904 full/app.py
cp full/templates/_bak/index.html.v2-brand-20260904 full/templates/index.html
cp full/templates/_bak/loading.html.v2-brand-20260904 full/templates/loading.html
```

---

## 5. 已知限制（不要踩坑）

1. **`/api/recent` 在 Windows 上永远返回 `[]`**：`DB_PATH` 默认 `/opt/ideon/portal/portal.db`（VM Linux 路径），Windows 上写不进 access_log。UI 正常 fallback "暂无访问记录"。VM 上线后正常。

2. **4 个工具在 Windows 点击都跳 `/?need_start=xxx`**：因为 Windows 没配 `dev_cmd`（只有 library 配了 8002）。VM 上线后正常。

3. **portal.service 不要同步**：main 是 v2.2 PATH 修复版（长 PATH + 注释），full 是 VM 原版（短 PATH），两边各自保留版本。同步 portal.service 会覆盖 VM 修复或本地修复。

4. **Logo SVG 是金黄色 `#FFC72C`**，不要自作主张改红色（用户明确说过麦当劳金拱是金黄色，改红被骂过）。

5. **不要给用户看"设计语言: Calm Intelligence v3"这种技术元信息**（曾因此被骂）。用户面向的是运营/分析师，不是开发。

---

## 6. 待办（用户提到但本次没做）

1. **/changelog 页**：sidebar 已加 `◐ → /changelog` 入口，但页面还没实现（404）
2. **本周要上 5 个新工具**：config.py 改 TOOLS，模板自动渲染
3. **左侧栏更多 nav 项**：AI 工作台 / 数据洞察 / 系统管理 的子项目占位都标了 disabled（即将上线）
4. **更多工具卡片 hover 效果**：当前是 `translateY(-2px) + 白底 + 轻阴影`，后续可加更精细的 micro-interaction

---

## 7. 文件结构

```
main/
├── app.py                    (16362B, 15 routes, 含 /api/recent + /static)
├── config.py                 (1810B, 5 tools + library persistent+hidden)
├── portal.service            (860B, v2.2 PATH 修复版)
├── README.md
├── requirements.txt          (fastapi/uvicorn/jinja2)
├── DEPLOY-HANDOFF.md         (VM 部署文档)
├── HANDOFF.md                (本文件，会话交接)
├── static/
│   └── loading.gif           (从 templates 移过来)
└── templates/
    ├── index.html            (26KB, v3 中性主版本)
    ├── loading.html          (3.6KB, v3 浅玻璃)
    └── _bak/                 (旧 v2 备份)
```

---

## 8. 关键 API（给下次 session 参考）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/` | 路由页 HTML（带 cards / idle_timeout / need_start） |
| GET | `/loading/{tool_key}` | 中转页（GIF + 自动跳转） |
| GET | `/open/{tool_key}` | 启动 + 跳转（无运行则启动，30s 超时） |
| POST | `/api/start/{tool_key}` | 手动启动 |
| POST | `/api/stop/{tool_key}` | 手动停止 |
| POST | `/api/restart/{tool_key}` | 重启 |
| GET | `/api/status` | 所有工具实时状态 |
| GET | `/api/summary` | total_tools / running_count / total_opens / idle_timeout_minutes |
| GET | `/api/recent?limit=10` | 最近访问事件（基于 access_log） |
| GET | `/api/debug/redirect/{tool_key}` | 显示跳转目标 URL（调试） |
| GET | `/static/*` | 静态资源（loading.gif 等） |
| GET | `/changelog` | ⚠️ 还没实现 |

---

**End of HANDOFF (2026-09-04)**

---

## 9. v3.1.1 · 2026-09-04：内容工坊 / 历史洞察 走 8530 独立进程跳转

**背景**：之前尝试在 portal 内"模拟" 8530 studio（抄模板、抄 CSS、自写 tool_routes.py），结果：
- 中文 task_input mojibake（`ͨ��` 代替 `通用`）
- 候选顺序被 portal 自加的 `rank_candidates_by_ctr` 重排成 C/B/A，破坏 8530 固定 ABC 顺序
- HX-Redirect / form action / 静态路径在 portal 路由下行为不一致（点不动、跳错地址）
- LLM pill 调不到 modal

**用户反馈**：要"完整 copy"，不是 portal 重写。

**方案**：放弃 portal 内部实现，让 8530 在自己端口（8530）独立跑，portal 只生成跳转链接：

| 项 | 改动 |
|---|---|
| `app.py` | 删 `_tool_target` 对 external 类型的 `dev_port` 推断，新增 `path_prefix` 是 `http://...` 时直接返回；`build_cards` 的 `external_blank` 改读 `t.get("external_blank")` |
| `config.py` | `studio` / `insights` 改 `type="external"` + `dev_port=8530` + `path_prefix="http://localhost:8530/studio"` + `external_blank=True` |
| `tool_routes.py` | **删除**（portal 不再自己实现这两个工具） |
| 模板 | `templates/studio.html` / `insights.html` 留作旧版本参考，但不再被路由使用（portal 首页不再链接到 `/studio` / `/insights`） |

**跳转流程**：portal 首页工具卡 → `target=_blank` 新标签 → `http://localhost:8530/studio` → 8530 进程原生渲染（用 8530 自己的 base.html + partials + style.css + JS，零 portal 介入）。

**部署注意**：8530 进程必须保持运行（`cd C:\ideon\mcd-ai-content-platform\web && uvicorn app:app --port 8530`）。portal 这边完全独立。

**留下的半成品**（可清理）：
- `templates/studio_old8530.html`、`templates/base_8530.html`、`templates/partials/01_*` / `02_*` 几个 copy 过的 8530 模板（不再用）
- `static/css/style.css` + `static/img/mcdonalds.svg`（8530 的 CSS + icon，portal 没引用但留着不删）
- `_bak-app.py.v3-20260904` / `_bak-config.py.v3-20260904`（v3 中间过程的备份）

**教训（下次别再犯）**：
1. 用户说"完整 copy"=把目标进程嵌进来（独立端口 / 子应用 / 重定向），不是 portal 自己重写一遍
2. 自加的 `rank_candidates_by_ctr` / `_read_form_utf8` 都是擅自加的功能，破坏原行为
3. `_tool_target` 对 `external_blank` 的逻辑写反过：原来 `True → target=_blank` 只看 `type=="internal"`，没考虑 external 也要新标签

**End of v3.1.1 HANDOFF (2026-09-04)**

---

## 10. v3.2 · 2026-09-07：门户整合 + LLM 配置移植

### 10.1 背景
- 用户在 `ideon-portal-clone` 迭代了苹果风首页（37.3KB，5 处 backdrop-filter，cubic-bezier 动画）——但 clone 的 `config.py` TOOLS 没同步，LLM pill 还是静态文本
- portal 有两个并行副本（clone 远端版 / main 本地版），用户后台还跑着 clone 进程，认知混乱
- LLM 配置（provider/base_url/model/api_key）在 mcd-ai-content-platform 8530 已经配好，但 portal 没有 modal/路由 —— 点 pill 无反应

### 10.2 整合（clone → main，main 是工作目录）
| 文件 | 改动 |
|---|---|
| `templates/index.html` | cp clone 苹果风首页（37395B）覆盖 main 老 v3 版本 |
| `templates/_bak-index.html.pre-clone-20260907` | 备份 main 改之前的版本（防回退） |
| `templates/_bak-app.py.v3-20260904` | 已存在的 v3 备份保留 |
| **结论** | main 包含全部功能且超过 clone，**建议删 clone** |

### 10.3 LLM 配置移植（抄 8530 实现，走 portal 独立 yaml）
完整链路（HTMX partial 理念）：

```
pill click (hx-get) → /api/settings/llm-modal → 渲染 partials/settings_llm_modal.html → 塞 #settings-modal-slot
```

| 文件 | 改动 |
|---|---|
| `templates/index.html` line 471 | 加 `<script src="https://unpkg.com/htmx.org@1.9.10">` |
| `templates/index.html` line 517-522 | 硬编码 `<div class="llm">LLM 已连接</div>` 换 inline pill（保留 .llm 苹果风紧凑样式 + hx-get 触发 modal） |
| `templates/index.html` body 末尾 | 加 `<div id="settings-modal-slot">` 容器（HTMX target） |
| `templates/partials/settings_llm_modal.html` 顶部 | 加 `<style>` 块（modal 自包含样式，不依赖 portal.css） |
| `app.py` line 15 | `from fastapi.responses import HTMLResponse, RedirectResponse` |
| `app.py` line 21 | `from llm_config import load_config, is_configured, save_config, get_status, probe_llm, LLM_PROVIDERS, mask_api_key, reload_cache` |
| `app.py` index 路由 context | 加 `llm_configured` + `llm_model` 字段 |
| `app.py` 末尾 | 加 3 个路由：`GET /api/settings/llm-modal`、`POST /api/settings/llm`、`POST /api/settings/llm/test`（用现成 `llm_config.py`） |

**配置存储**：写到 `~/.ideon-portal/llm_settings.yaml`（不复用 `~/.mcd-ai/llm_settings.yaml`，按用户口径"key 别迁移"）。

### 10.4 关键 API（新增）
| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/settings/llm-modal` | 点 pill → 返回 LLM 配置 modal HTML |
| POST | `/api/settings/llm` | 保存 4 字段到 `~/.ideon-portal/llm_settings.yaml` |
| POST | `/api/settings/llm/test` | 测试当前表单 4 字段能否连上 LLM provider |

### 10.5 踩坑（下次别犯）
1. **方案 A 一上来就大改**：写路由 + 改 modal + 改 pill → 其实缺 1 行 HTMX script
2. **pill 用了 partials/llm_pill.html**（`class="model-select"` 大下拉框样式）→ 不适合苹果风 topbar，要用 inline `.llm`
3. **modal partial 依赖 portal.css 的 .modal-mask 等样式** → 但苹果风 `index.html` 没引 portal.css → modal 堆在底部不弹窗 → 解决：partial 自带 `<style>` 块
4. **SOP**：下次 copy 前先 grep 完整链路（head script + partial + style + 路由 + 配置）—— 不要上来就大改

### 10.6 Git 状态
- portal-main：今天 9:30 新 init（master 分支，无 remote，无 commit，无 .gitignore）
- portal-clone：远端 ori-yin/ideon-portal @ 8a5ca89（v3.1 旧版）

**End of v3.2 HANDOFF (2026-09-07)**
