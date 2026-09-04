# MCD AI / iDeon 智能中台设计规范 V2.0

> **统一 Design System / UI UX Specification**
>
> **设计方向：80% Apple Professional Software + 20% Liquid Glass**
>
> **适用范围：AI
> 工作台、工具中台、内容中台、数据分析后台、运营后台、系统管理，以及未来两个中台合并后的统一平台。**
>
> **原则：本文件是 UI/UX 的 Source of Truth。**

------------------------------------------------------------------------

# 0. 使用规则

未来新增任何页面或组件时，优先级：

1.  `designv2.md`
2.  Design Token
3.  已有统一组件
4.  新业务需求

禁止为了新功能自行创造新的颜色、圆角、按钮、阴影、Glass 风格。

给 AI 编程工具的统一指令：

> 严格遵循项目根目录 `designv2.md`。优先复用现有 Token、Layout
> 和组件。普通业务界面使用 Apple Professional 风格；Liquid Glass
> 仅用于导航、浮层、状态组件和关键 AI 聚焦区域。新增组件必须考虑
> Default、Hover、Focus、Disabled、Loading，以及必要的 Empty/Error
> 状态。

------------------------------------------------------------------------

# 1. 产品设计定位

## 一句话定义

> **一个冷静、专业、清晰、智能、可长期使用和持续扩展的企业级 AI
> 工作平台。**

它不是：

-   炫技型 AI Landing Page
-   Dribbble 概念图
-   全页面透明玻璃
-   传统密集、沉重的管理后台
-   每个工具各自拥有一套 UI

它应融合：

-   Apple 官方专业软件的克制与秩序
-   macOS/iPadOS 的信息层级
-   现代 Enterprise SaaS 的效率
-   少量 Liquid Glass 的空间感

## 设计比例

``` text
████████████████  80% Apple Professional
████                20% Liquid Glass
```

### 80% Professional

负责：信息架构、可读性、数据密度、稳定性、长期使用体验、企业专业感。

### 20% Liquid Glass

负责：顶层空间感、导航、Popover、Dropdown、Modal、Status Pill、Command
Palette、Floating Toolbar、关键 AI Focus Area。

------------------------------------------------------------------------

# 2. 核心设计原则

## P1 信息优先

``` text
用户目标
↓
主要操作
↓
结果 / 数据
↓
状态 / 反馈
↓
辅助信息
↓
装饰
```

任何视觉效果不得降低信息可读性。

## P2 克制优先

高级感来自：

-   留白
-   对齐
-   字体层级
-   合理比例
-   少量颜色
-   微弱阴影
-   一致性

不是来自：

-   大量渐变
-   霓虹
-   发光
-   满屏玻璃
-   无意义动画

### AI 装饰严禁清单

以上原则在 AI 相关 UI 中尤其重要。具体禁用：

-   Sparkles / 闪光特效作为默认 AI 标识
-   机器人 / 发光大脑 / 电路板 插画
-   紫蓝渐变 / 霓虹边框 / 赛博朋克网格背景
-   AI 区域使用全息、星空、粒子等科幻装饰
-   每个 AI 按钮都加闪烁发光

AI 的存在感应来自"能力被使用"，而非"看上去像 AI"。

## P3 一致优先

未来新增 5 个、20 个、100 个工具，都必须让用户感觉：

> 这是同一个产品。

## P4 可扩展优先

系统必须支持：

-   分类
-   搜索
-   收藏
-   最近使用
-   常用工具
-   Workspace
-   异步任务
-   权限

## P5 AI 是能力，不是装饰

AI 的价值应体现在：

``` text
输入
→ 理解
→ 生成 / 分析
→ 结果
→ 人工决策
→ 数据回流
```

------------------------------------------------------------------------

# 3. 推荐统一信息架构

``` text
首页 Home

AI 工作台 AI Workspace
├── 内容生成
├── 内容诊断
├── 文案解析
├── AI Agent
└── 批量 AI 任务

工具中心 Tool Center
├── 内容排行
├── 触达趋势
├── CTR 预测
├── 文案解析
└── 未来业务工具

数据洞察 Insights
├── 历史洞察
├── 内容表现
├── 渠道表现
├── 趋势分析
└── 报表

任务中心 Tasks
├── 运行中
├── 已完成
├── 失败
└── 历史

系统管理 Administration
├── 用户与权限
├── 模型与服务
├── 数据源
├── 配置
├── 日志
└── 系统状态
```

未来新增工具时，优先判断：

> 它是一个一级模块，还是 Tool Center 内的工具？

不要因为新增一个功能就新增一个 Sidebar 一级菜单。

------------------------------------------------------------------------

# 4. App Shell 与 Layout

## Desktop Structure

``` text
┌──────────── Sidebar ────────────┬──────── Main ────────┐
│ Brand                           │ Topbar               │
│ Search                          ├──────────────────────┤
│ Primary Navigation              │ Page Header          │
│ Secondary Navigation            │ Main Workspace       │
│                                 │                      │
│ User / Settings                 │                      │
└─────────────────────────────────┴──────────────────────┘
```

## Sidebar

默认：

``` css
width: 224px;
padding: 20px 16px;
```

Compact：

``` css
width: 72px;
```

移动端：Drawer。

Sidebar 是全局组件，禁止每个页面重新设计。

## Main Content

``` css
padding: 30px 38px;
max-width: 1780px;
margin: 0 auto;
```

## Spacing

``` text
页面大区块：24-32px
模块之间：16px
Card 内边距：20-24px
紧密元素：8-12px
```

## Grid

推荐 12 Column Grid：

``` text
12
6 + 6
8 + 4
9 + 3
4 + 4 + 4
3 + 3 + 3 + 3
```

默认 gap：16px。

------------------------------------------------------------------------

# 5. Design Token

## 颜色

中性色基调比例（Universal Design System 基线）：

``` text
70%  中性背景与表面（canvas / surface / subtle / hover）
20%  文本与层级（primary / secondary / tertiary / disabled）
 8%  功能色（primary blue + success / warning / danger / info）
 2%  品牌重音（MCD 红黄、iDeon Logo 色）
```

原则：去掉品牌色后，界面仍应保持平衡。日常配色应优先用中性 token 承载信息层级，品牌色只用于品牌识别与关键 CTA 强调。

``` css
:root {
  --bg-canvas: #F5F5F7;
  --bg-subtle: #FAFAFB;
  --surface: #FFFFFF;
  --surface-soft: #F8F9FB;

  --text-primary: #1D1D1F;
  --text-secondary: #6E6E73;
  --text-tertiary: #86868B;
  --text-disabled: #AEAEB2;

  --border-subtle: rgba(60,60,67,.08);
  --border-default: rgba(60,60,67,.12);

  --primary: #0A6EE8;
  --primary-hover: #005FCC;
  --primary-active: #0052B8;
  --primary-soft: #EAF3FF;

  --success: #22A06B;
  --success-soft: #EAF7F1;
  --warning: #E98A00;
  --warning-soft: #FFF5DF;
  --danger: #E6525C;
  --danger-soft: #FFF0F1;
  --info: #0A6EE8;
  --info-soft: #EAF3FF;
}
```

## Spacing

统一 4px Grid：

``` css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-7: 28px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
```

## Radius

``` css
--radius-xs: 8px;
--radius-sm: 10px;
--radius-md: 14px;
--radius-lg: 20px;
--radius-xl: 28px;
--radius-pill: 999px;
```

## Shadow

``` css
--shadow-sm: 0 6px 18px rgba(28,43,65,.04);
--shadow-card: 0 10px 28px rgba(28,43,65,.055);
--shadow-md: 0 14px 36px rgba(28,43,65,.08);
--shadow-floating: 0 18px 50px rgba(28,43,65,.12);
```

------------------------------------------------------------------------

# 6. Typography

``` css
font-family:
  -apple-system,
  BlinkMacSystemFont,
  "SF Pro Display",
  "PingFang SC",
  "Microsoft YaHei",
  sans-serif;
```

  Token          Size Usage
  --------- --------- -----------
  Display        36px Hero
  H1          30-32px 页面标题
  H2          22-24px 大区块
  H3          17-18px Card 标题
  Body           14px 默认正文
  Small          13px 辅助信息
  Caption        12px Metadata

字重：

``` text
Page Title: 600-650
Section: 600
Card Title: 600
Body: 400
Metric: 600-700
```

------------------------------------------------------------------------

# 7. Liquid Glass 规范

## 核心原则

Liquid Glass 不是：

``` text
透明 + blur = Glass
```

真正效果来自：

``` text
半透明材质
+ 背景环境光
+ 背景模糊
+ 高光边缘
+ 内部高光
+ 正确层级
```

## 使用位置

推荐：

-   Sidebar（轻）
-   Status Pill
-   Dropdown
-   Popover
-   Context Menu
-   Command Palette
-   Modal
-   Floating Toolbar
-   AI Hero / Focus Area

普通业务 Card 优先实体 Surface。

## Glass CSS

``` css
.glass {
  background: linear-gradient(
    135deg,
    rgba(255,255,255,.50),
    rgba(255,255,255,.18)
  );

  border: 1px solid rgba(255,255,255,.62);

  backdrop-filter: blur(28px) saturate(145%);
  -webkit-backdrop-filter: blur(28px) saturate(145%);

  box-shadow:
    0 18px 50px rgba(40,60,90,.12),
    inset 0 1px 0 rgba(255,255,255,.72);
}
```

## Blur Layer

  Layer             Blur
  ------------ ---------
  Navigation     16-20px
  Status            18px
  Popover        22-26px
  Modal          28-32px
  AI Focus       28-32px

## Environment Light

``` css
body {
  background:
    radial-gradient(
      900px 500px at 52% -150px,
      rgba(216,230,255,.72),
      transparent 70%
    ),
    radial-gradient(
      700px 500px at 95% 90%,
      rgba(235,239,255,.55),
      transparent 65%
    ),
    #F5F5F7;
}
```

禁止：

-   所有 Card 都 Glass
-   全页面 blur
-   高饱和彩色玻璃
-   强白色描边
-   夸张发光

------------------------------------------------------------------------

# 8. Sidebar 与 Navigation

## Navigation Item

结构：

``` text
Icon
Label
Badge（可选）
```

推荐：

``` text
Height: 48-52px
Radius: 14-16px
Gap: 14px
```

## Active

统一使用 Soft Primary Surface：

``` css
background: var(--primary-soft);
color: var(--primary);
```

如果某个历史系统保留深色 Sidebar + 黄色品牌
Active，可以作为**品牌主题变体**，但整个统一平台必须固定一种 Sidebar
方案。

## 搜索

Sidebar 或全局顶部可提供：

``` text
搜索工具 / 页面
⌘K / Ctrl+K
```

未来工具增多后必须提供 Global Search / Command Palette。

------------------------------------------------------------------------

# 9. Button System

## Size

``` text
Small: 32px
Medium: 40px
Large: 48px
```

## Primary

``` css
background: var(--primary);
color: #fff;
border-radius: 12px;
```

Hover：

``` css
background: var(--primary-hover);
transform: translateY(-1px);
```

## Secondary

``` css
background: rgba(255,255,255,.82);
border: 1px solid var(--border-default);
color: var(--text-primary);
```

## Ghost

用于低优先级操作。

## Danger

仅用于删除、停止、高风险操作。

**红色不是系统默认 Primary。**

## Icon Button

推荐：

``` text
40 × 40px
Radius: 12px
```

必须提供 Tooltip / aria-label。

------------------------------------------------------------------------

# 10. Form Components

完整基础组件：

-   Input
-   Textarea
-   Search
-   Select
-   Combobox
-   Checkbox
-   Radio
-   Switch
-   Date Picker
-   Date Range Picker
-   Number Input
-   Slider
-   File Upload

## Form Field

标准：

``` text
Label
Control
Helper Text（可选）
Validation Error（必要时）
```

错误信息必须靠近对应字段。

## Focus

``` css
border-color: rgba(10,110,232,.65);
box-shadow: 0 0 0 4px rgba(10,110,232,.10);
```

## Textarea

AI Prompt 场景：

-   支持 Auto Resize
-   支持 Context
-   支持字符限制
-   支持 Clear

------------------------------------------------------------------------

# 11. Select / Combobox / Command

### Select

有限选项。

### Combobox

大量选项，可搜索。

### Command Palette

跨系统执行：

``` text
搜索工具
搜索页面
执行操作
```

推荐快捷键：

``` text
⌘K / Ctrl+K
```

------------------------------------------------------------------------

# 12. Card System

## Standard Card

``` css
.card {
  background: linear-gradient(
    145deg,
    rgba(255,255,255,.92),
    rgba(255,255,255,.74)
  );
  border: 1px solid rgba(255,255,255,.9);
  border-radius: 20px;
  box-shadow: var(--shadow-card);
}
```

## Card Types

统一优先复用：

-   Metric Card
-   Content Card
-   Tool Card
-   Action Card
-   Chart Card
-   Status Card
-   Empty Card
-   AI Result Card

------------------------------------------------------------------------

# 13. Data Display

## Metric

``` text
Icon（可选） + Label
Main Value
Comparison / Description
```

规则：

-   千分位统一
-   单位统一
-   百分比精度统一
-   数字建议使用 tabular numbers

不要同一页混用：

``` text
2.3%
2.34%
2.3456%
```

## Status / Badge / Tag

必须区分：

### Status

系统运行状态。

### Badge

数量、New。

### Tag

分类。

------------------------------------------------------------------------

# 14. Table

中后台必须统一 Table。

支持：

-   Sorting
-   Filtering
-   Pagination
-   Row Selection
-   Bulk Action
-   Column Visibility
-   Empty
-   Loading
-   Error

推荐：

``` text
Default Row: 52-56px
Compact Row: 40-44px
```

复杂表格必须支持横向滚动，而不是强行压缩所有列。

------------------------------------------------------------------------

# 15. List / Activity / Timeline

结构：

``` text
Icon / Avatar
Primary Text
Secondary Text
Time / Metadata
Action（可选）
```

适用于：

-   最近活动
-   日志
-   通知
-   历史记录

------------------------------------------------------------------------

# 16. Overlay Components

## Tooltip

解释图标或短信息。

## Popover

展示额外信息。

## Dropdown

选项列表。

## Context Menu

对象操作：

``` text
编辑
复制
归档
────────
删除
```

危险操作必须视觉分组。

## Modal

短任务：

-   确认
-   小表单
-   快速设置

## Drawer

复杂：

-   详情
-   配置
-   编辑

## Fullscreen

适合：

-   AI Studio
-   大数据分析
-   多步骤工作流

------------------------------------------------------------------------

# 17. Feedback System

## Toast

适合：

-   保存成功
-   上传成功
-   任务已创建

不适合长错误说明。

## Alert

适合页面内长期存在的重要信息。

## Loading

### Skeleton

页面 / Card 加载。

### Spinner

局部动作 / Button。

### Progress

上传、导入、异步任务。

禁止全页面只有一个 Spinner。

------------------------------------------------------------------------

# 18. Empty / Error / Permission State

## Empty State

结构：

``` text
Icon / Illustration
Title
Description
Primary Action（可选）
```

禁止只写：

> 暂无数据

## Error State

必须回答：

``` text
发生什么？
可能原因？
用户能做什么？
```

## Permission

支持：

``` text
No Access
Read Only
Cannot Edit
Feature Unavailable
```

不要把无权限用户导向空白页面。

------------------------------------------------------------------------

# 19. Dashboard / Home

首页回答：

``` text
我现在可以做什么？
我最近在做什么？
今天发生了什么？
系统是否正常？
```

推荐结构：

``` text
Greeting
Primary AI Action
Today's Metrics
Recent Work
Favorite / Common Tools
Trend
System Status
Notifications
```

首页不是"所有数据的垃圾场"。

------------------------------------------------------------------------

# 20. Tool Center

未来工具多时统一支持：

``` text
Search
Categories
Favorites
Recent
Popular
All Tools
```

Tool Card：

``` text
Icon
Name
One-line Description
Status
Favorite
Open
```

工具状态：

``` text
Available
Running
Maintenance
Not Deployed
```

------------------------------------------------------------------------

# 21. AI Workspace

这是产品的重要核心。

统一流程：

``` text
Business Goal
↓
Context / Parameters
↓
AI Processing
↓
AI Result
↓
Prediction / Diagnosis
↓
Human Decision
↓
Save / Export / Publish
↓
Feedback / Data Return
```

## AI Input

建议支持：

-   Prompt
-   Context
-   Channel
-   Audience
-   Goal
-   Tone
-   Advanced Options

AI 主输入区可以使用系统中最明显的 Glass。

## AI Result

必须分层：

``` text
AI Output
Prediction
Diagnosis
Recommendation
Confidence / Score（如有）
Actions
```

不要全部混成一段文字。

## AI Streaming

必须有：

-   Generating
-   Stop
-   Retry
-   Regenerate
-   Copy
-   Save
-   Compare
-   Feedback

------------------------------------------------------------------------

# 22. Task Center

所有异步任务统一管理。

Status：

``` text
Queued
Running
Completed
Failed
Cancelled
Expired
```

每个任务至少包含：

``` text
Name
Type
Creator
Created Time
Status
Progress
Result
Failure Reason（如有）
```

------------------------------------------------------------------------

# 23. Search / Filter / View

## Search

至少规划：

-   Local Search
-   Global Search

## Filter Bar

``` text
Search
Quick Filters
Advanced Filters
Reset
Saved View（未来）
```

必须清楚展示当前筛选条件，并支持一键重置。

## Saved View

复杂数据后台未来可支持：

-   我的视图
-   团队视图
-   默认视图

------------------------------------------------------------------------

# 24. Pagination / Infinite Scroll

### Table

优先 Pagination。

### Feed / Activity

可 Infinite Scroll。

### 大数据

可使用 Virtualization。

------------------------------------------------------------------------

# 25. Chart Design

统一支持：

-   Line
-   Bar
-   Area
-   Donut
-   Funnel
-   Heatmap
-   Scatter

颜色优先：

``` text
Primary: Blue
Secondary: Teal
Third: Purple
```

网格线非常淡。

Pie Chart 谨慎使用。

图表必须支持：

-   Empty
-   Loading
-   Tooltip
-   Date Range
-   Legend

------------------------------------------------------------------------

# 26. Date / Time

统一：

``` text
2026-09-03
2026-09-03 14:30
```

Activity 可使用：

``` text
2 分钟前
1 小时前
```

报表优先绝对时间。

------------------------------------------------------------------------

# 27. File Upload / Import / Export

Upload：

``` text
Drop Zone
Upload Button
File List
Progress
Success
Error
Remove
Retry
```

Import：

``` text
Upload
→ Validation
→ Preview
→ Confirm
→ Processing
→ Result
```

必须显示：

-   文件名
-   文件大小
-   状态
-   错误原因

Export 应明确：

-   导出格式
-   数据范围
-   是否后台生成

------------------------------------------------------------------------

# 28. Notification Center

建议支持：

-   System
-   Task
-   Business
-   Mention（未来）

操作：

``` text
Read
Unread
Mark All Read
Jump to Related Object
```

------------------------------------------------------------------------

# 29. Settings / Administration

建议分类：

``` text
General
AI / Model
Data Source
Notifications
Users & Permissions
Security
System
About
```

复杂设置必须有说明和保存反馈。

------------------------------------------------------------------------

# 30. Responsive

## ≥ 1440px

完整 Desktop。

## 1024-1439px

减少 Grid 列数。

## 768-1023px

Sidebar Compact / Collapse。

## \<768px

Drawer Navigation。

复杂 AI Studio、Table、Charts 可以简化，不要强行等比例缩小。

------------------------------------------------------------------------

# 31. Accessibility

必须考虑：

-   Keyboard Navigation
-   Focus Visible
-   文字对比度
-   Icon aria-label
-   Tooltip
-   不只依赖颜色表达状态
-   Toast 不作为唯一错误信息

Focus：

``` css
box-shadow: 0 0 0 4px rgba(10,110,232,.12);
```

------------------------------------------------------------------------

# 32. Motion

推荐：

``` css
transition: 180ms 240ms cubic-bezier(.2,.8,.2,1);
```

允许：

-   Hover 微上移
-   Fade
-   Panel 轻进入

禁止：

-   大幅缩放
-   弹跳
-   无意义循环
-   Loading 时复杂动画

支持 `prefers-reduced-motion`。

------------------------------------------------------------------------

# 33. Dark Mode

如果未来加入 Dark Mode：

> 必须是完整 Theme，不允许简单颜色反转。

需要独立定义：

-   Canvas
-   Surface
-   Elevated Surface
-   Text
-   Border
-   Semantic Colors
-   Glass

Dark Mode 的 Glass 透明度和高光必须单独调整。

------------------------------------------------------------------------

# 34. Icon System

正式产品推荐：

-   Lucide 风格
-   SF Symbols 风格

统一：

``` text
Stroke
Corner
Weight
Size
```

默认：

``` text
16px / 18px / 20px / 24px
```

禁止正式产品混用 Emoji、实心 Icon、线性 Icon。

------------------------------------------------------------------------

# 35. Brand Color Strategy

未来两个中台合并采用三层：

``` text
Brand Layer
System Layer
Semantic Layer
```

### Brand

负责品牌识别。

### System

负责交互，如 Primary Blue。

### Semantic

负责状态：

-   Success
-   Warning
-   Danger
-   Info

原则：

> 品牌色回答"我是谁"；系统色回答"如何操作"。

------------------------------------------------------------------------

# 36. Component State Matrix

交互组件必须尽量覆盖：

``` text
Default
Hover
Active
Focus
Disabled
Loading
Success（必要时）
Error（必要时）
```

------------------------------------------------------------------------

# 37. 完整组件库存

## Foundation

-   Color
-   Typography
-   Spacing
-   Radius
-   Shadow
-   Motion
-   Icon

## Navigation

-   Sidebar
-   Topbar
-   Tabs
-   Breadcrumb
-   Pagination
-   Stepper

## Inputs

-   Input
-   Textarea
-   Search
-   Select
-   Combobox
-   Checkbox
-   Radio
-   Switch
-   Date Picker
-   Date Range
-   Number Input
-   Slider
-   File Upload

## Actions

-   Button
-   Icon Button
-   Split Button
-   Dropdown Button

## Data Display

-   Card
-   Statistic
-   Table
-   List
-   Timeline
-   Tag
-   Badge
-   Avatar
-   Tooltip
-   Chart

## Feedback

-   Alert
-   Toast
-   Progress
-   Spinner
-   Skeleton
-   Empty State
-   Error State
-   Permission State

## Overlay

-   Modal
-   Drawer
-   Popover
-   Dropdown
-   Context Menu
-   Command Palette

## AI Components

-   Prompt Input
-   Context Chip
-   AI Streaming
-   AI Result Card
-   Regenerate
-   Compare
-   Feedback
-   Confidence
-   Recommendation

------------------------------------------------------------------------

# 38. Page Template

新页面优先：

``` text
Page Header
├── Breadcrumb（可选）
├── Title
├── Description（可选）
└── Primary Action

Main Workspace
├── Primary Content
└── Secondary Panel

Supporting Content
├── Data
├── Activity
└── Help / System Information
```

不要每个页面重新发明 Layout。

------------------------------------------------------------------------

# 39. New Feature Checklist

## Information Architecture

-   [ ] 属于哪个一级模块？
-   [ ] 是否已有相似功能？
-   [ ] 是否应作为 Tool？
-   [ ] 是否需要首页入口？

## UX

-   [ ] 用户目标是什么？
-   [ ] Primary Action 是什么？
-   [ ] 最短完成路径是什么？
-   [ ] 是否支持批量操作？

## UI

-   [ ] 使用统一 Token
-   [ ] 复用已有组件
-   [ ] Glass 是否真的必要？
-   [ ] 颜色是否符合语义？
-   [ ] Radius 是否统一？

## State

-   [ ] Loading
-   [ ] Empty
-   [ ] Error
-   [ ] Permission
-   [ ] Disabled

## Quality

-   [ ] Responsive
-   [ ] Keyboard
-   [ ] Focus
-   [ ] Long Text
-   [ ] Large Data

------------------------------------------------------------------------

# 40. 严禁事项

``` text
❌ 全页面 Glass
❌ 每张 Card 都彩色渐变
❌ 每个模块不同 Button
❌ 随意新增颜色
❌ 随意新增 Radius
❌ 每页重新设计 Sidebar
❌ Emoji 作为正式 Icon
❌ 红色作为默认 Primary
❌ 厚重黑色阴影
❌ 无意义动画
❌ 只有“暂无数据”的空状态
❌ 只有“失败”的错误提示
❌ 没有 Loading
❌ AI 输出没有下一步操作
```

------------------------------------------------------------------------

# 41. 最终验收标准

每个页面完成后检查：

## Professional

> 是否像成熟企业软件，而不是 Demo？

## Apple

> 是否简洁、清晰、有秩序？

## Glass

> 是否只在真正需要空间层级的位置使用？

## Consistency

> 是否像同一个产品？

## Long-term

> 连续使用一天是否舒适？

## Executive

CIO 或管理层打开时，是否能感受到：

> **统一、成熟、专业、可扩展，并且 AI 已真正融入工作流。**

## 三档质量判断

每个页面、每个功能上线前，除了上面 6 维自检，再问自己一次：

弱的结果：

> "AI 生成了一个漂亮的界面。"

合格的结果：

> "这是一个设计良好的产品。"

优秀的结果：

> "这个产品拥有一个连贯且经过深思熟虑、持续打磨的设计系统。"

目标：每一次交付都向"优秀"靠近一格。

------------------------------------------------------------------------

# 42. 最终设计语言

## Design Name

> **Calm Intelligence**

中文：

> **冷静的智能感**

关键词：

``` text
Professional
Calm
Precise
Intelligent
Spatial
Minimal
Premium
Scalable
```

最终目标不是：

> "这个 UI 特效真酷。"

而是：

> **"这是一个成熟的平台，而且未来还能持续扩展。"**

------------------------------------------------------------------------

# Appendix A：推荐项目结构

``` text
src/
├── app/
├── pages/
│   ├── home/
│   ├── ai-workspace/
│   ├── tool-center/
│   ├── insights/
│   ├── tasks/
│   └── administration/
│
├── components/
│   ├── layout/
│   ├── ui/
│   ├── charts/
│   ├── ai/
│   └── business/
│
├── design/
│   ├── tokens.css
│   ├── globals.css
│   ├── liquid-glass.css
│   └── designv2.md
│
├── hooks/
├── services/
└── utils/
```

------------------------------------------------------------------------

# Appendix B：AI Coding Prompt

``` text
本项目采用 designv2.md 作为 UI/UX 单一设计规范。

开发任何新页面前：
1. 先判断功能属于哪个信息架构模块；
2. 检查是否已有可复用 Layout 和 Component；
3. 使用统一 Design Token；
4. 普通业务内容遵循 Apple Professional；
5. Liquid Glass 仅用于导航、浮层、状态组件和关键 AI 聚焦区域；
6. 禁止自行创造新的视觉语言；
7. 所有重要组件必须处理 Loading、Empty、Error、Disabled 等状态；
8. 完成后检查 Responsive、Accessibility 和一致性。
```

------------------------------------------------------------------------

**End of MCD AI / iDeon Design System V2.0**
