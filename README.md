# LingDraw PPT Studio

LingDraw PPT Studio 是一个用于课堂演示和原型验证的端到端 PPT/PDF 分析 Demo。它支持上传 `.pptx` 或 `.pdf`，逐页抽取文本，识别页面图表意图，生成数据图表配置，并输出文生图插图策略。

当前主流程是：

1. 上传 PPT/PDF。
2. 本地解析每页标题、正文和页面预览图。
3. 对当前页运行图表意图分析。
4. 生成 ECharts 数据图表。
5. 在实验面板中生成 ECharts / Chart.js / Mermaid 三种可渲染表示。
6. 生成插图关键词和 prompt。

## 项目结构

- `backend/`：FastAPI 后端，提供上传解析、意图分析、图表生成、插图策略、登录鉴权等接口。
- `frontend/`：Vue 3 + Vite 前端，提供文档预览、逐页导航、三步工作流、图表预览和实验面板。
- `test/`：稳定性测试资产，包含意图分析和图表构建回归用例。

## 环境准备

### 后端依赖

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 前端依赖

```powershell
cd frontend
npm install
```

## 配置 `.env`

仓库根目录下使用 `.env` 配置后端行为。常用配置如下：

```env
MOCK_MODE=true
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com
WAN_T2I_MODEL=wan2.6-t2i
IMAGE_EVAL_PASS_SCORE=72
IMAGE_GEN_MAX_ATTEMPTS=3
IMAGE_JUDGE_LOW_THRESHOLD=70
IMAGE_JUDGE_CONFIDENCE_GATE=0.6
APP_HOST=127.0.0.1
APP_PORT=8000
```

万相文生图（阿里云百炼）：

- `DASHSCOPE_API_KEY`：百炼 API Key，用于 `POST /api/flux/generate-image`（接口路径保留，后端已切换万相）。
- `DASHSCOPE_BASE_URL`：默认北京 `https://dashscope.aliyuncs.com`；新加坡用 `https://dashscope-intl.aliyuncs.com`（Key 与地域须一致）。
- `WAN_T2I_MODEL`：默认模型，前端也可在界面选择 `wan2.6-t2i`、`wan2.5-t2i-preview` 等。

模式说明：

- `mode=mock`：只使用本地规则，不调用 DeepSeek。
- `mode=deepseek`：强制尝试 DeepSeek；如果没有 Key、SDK 不可用或模型调用失败，会回退到本地规则，并返回 `fallbackReason`。
- `mode=auto`：当 `MOCK_MODE=false` 且配置了 `DEEPSEEK_API_KEY` 时优先尝试 DeepSeek；否则走本地规则。
- `MOCK_MODE=true`：让 `auto` 强制使用本地规则/mock 链路，不调用 DeepSeek。
注意：填入 `DEEPSEEK_API_KEY` 不代表所有阶段都会使用 AI。上传文本解析阶段仍是本地解析。

## 启动服务

### 启动后端

在仓库根目录执行：

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --port 8000
```

后端默认地址：

```text
http://127.0.0.1:8000
```

### 启动前端

新开一个终端：

```powershell
cd frontend
npm run dev
```

前端默认地址：

```text
http://localhost:5173
```

前端页面里有后端地址输入框，默认使用 `http://127.0.0.1:8000`。

## 默认测试账号

后端启动时会确保以下账号存在：

- 管理员账号
  - 用户名：`admin`
  - 密码：`admin123`
- 普通测试账号
  - 用户名：`tester`
  - 密码：`tester123`

可以在 `.env` 中修改：

- `ADMIN_USERNAME` / `ADMIN_PASSWORD`
- `TEST_USERNAME` / `TEST_PASSWORD`

## 使用流程

1. 打开前端并登录。
2. 上传 `.pptx` 或 `.pdf`。
3. 左侧查看页面缩略图，中间查看当前页预览，右侧进入工作流。
4. 当前页会显示本地解析出的正文。切换页面时，系统会恢复该页上传时解析出的原始正文；如果你手动删改了正文，切页后会重新显示原始解析文本。
5. 在“图表意图”步骤运行意图分析，查看 `intent`、`chartType`、`source`、`confidence`、`extracted` 等结果。
6. 在“数据图表”步骤生成图表。主流程会生成 ECharts option 并渲染预览。
7. 在图表代码实验面板中，可以生成 ECharts、Chart.js、Mermaid 三种表示；三个预览按纵向排列，每个图独占一行。
8. 在「文生图插图」步骤：先在预览区框选文字并写入正文，再点击 **根据选中文字生成图片** 调用阿里云万相；也可先生成本地插图 Prompt 策略。

## 万相文生图

接口：`POST /api/flux/generate-image`（需登录，路径保留兼容）

1. 预览区点击 **框选文字**，确认后 **写入正文框**。
2. 进入工作流第 3 步「文生图插图」。
3. 选择万相模型与宽高比，点击 **根据选中文字生成图片**。
4. 默认 `wan2.6-t2i` 同步出图；其它模型异步轮询，返回 `resultImageUrl`（约 10 秒–2 分钟）。

说明：万相文生图不支持「编辑当前页预览图」；该能力需图生图/图像编辑 API，当前未接入。

文档级一致性 / 多图协同（文生图）：

- 上传后自动 `POST /api/document/analyze-consistency`，流水线：
`Document Understanding → Visual Planner → Consistency Controller → Prompt Builder`
- **Consistency Controller** 五层约束：
  1. **Style**：color_theme / illustration_style / visual_density / shape_language / render_style
  2. **Entity**：跨页 visual_anchor + 别名合并（如 CTCS / 列控系统）
  3. **Narrative**：page_role（overview / detail / process / case / summary）
  4. **Primitive**：train_object / workflow_arrow / architecture_block 等跨页复用
  5. **Cross-page**：typed slide_graph（overview_to_detail / process_to_metric 等）
- 出图时注入压缩版 consistency 后缀（`[Document Style]` / `[Current Page]` / `[Entities]`，约 150~250 tokens），避免 Prompt 过长导致约束失效。
- **Windows 控制台乱码**：若 `chcp` 显示 `936`，Python 打印中文可能乱码；可 `chcp 65001` 或设置 `$env:PYTHONIOENCODING="utf-8"`。后端启动时会尝试将 stdout/stderr 设为 UTF-8。
- 前端「文生图插图」可开关：统一全文档风格、多图协同（共享实体库）。

配图质量流水线（`Generate × N → Evaluate → Select Best`）：

- **通用模式**：使用同一 Prompt **独立生成 3 张候选**，分别评分后取综合分最高者（`selectedAttempt`）。不做多轮增量 Prompt 改写（PPT 信息图重绘易破坏文字与布局）。
- **极速模式**：只生成 1 次并评分。
- 六维评分（PPT 配图专用，按 `slide_type` 动态权重）：
  - 语义一致性（VL 只评主题/主体/布局，**不**评文字对错；OCR 失真时会下调 VL 语义分）
  - **文字真实性**（仅 OCR 负责；封面/分隔页权重降至 5%，精确文字应由 PPT 文本层渲染）
  - 视觉清晰度、风格一致性（VL 分数统一归一化：0.91→91，9→90）、配色一致性、布局质量（四象限均衡+留白启发式）
- 封面页请在「幻灯片类型」选 **cover**，或在正文中含报告人/学号等字段时自动识别。
- 及格线默认 `72`（`IMAGE_EVAL_PASS_SCORE`）。
- 可选 `IMAGE_EVAL_USE_VL=true` 调用 `qwen-vl-plus` 增强语义与风格评分。
- **已知缺口**：当前为单页评分，尚未做整份 PPT（Deck-Level）跨页视觉一致性评分；后续可基于 `doc_consistency` 扩展。

## AI 使用阶段

### 1. 上传文本解析

接口：`POST /api/extract-text`

这一阶段不调用 DeepSeek。后端使用本地库解析：

- PPTX：`python-pptx`
- PDF：`pypdf`
- 页面预览：优先 PowerPoint/LibreOffice 转 PDF，再用本地渲染；失败时使用文本预览图回退

这样做的原因是上传解析需要稳定、快速、低成本，并且不依赖外部模型。

### 2. 意图分析和数据抽取

接口：

- `POST /api/analyze`
- `POST /api/viz-lab/intent`

这一阶段可以使用 DeepSeek，前提是：

- `.env` 中设置了 `DEEPSEEK_API_KEY`
- `MOCK_MODE=false`
- 请求 `mode` 为 `auto` 或 `deepseek`

如果 DeepSeek 不可用，系统会回退到本地规则，并在结果中标记 `source=fallback` 或 `source=mock`。

语义分析的 AI 输出被约束为严格 JSON，核心字段包括：

- `intent`、`chartType`、`reason`、`extracted`
- `confidence`、`intentConfidence`、`dataExtractionConfidence`、`chartSuitabilityConfidence`
- `dataQuality`、`warnings`
- `requestedMode`、`runtimeMode`、`llmAttempted`、`llmSucceeded`、`fallbackReason`

数据抽取要求模型先识别字段语义角色，再抽取图表数据。时间、类别、实体、指标名、单位等维度字段用于标签、坐标轴或系列名；可度量数值字段用于 `values`、`y` 或 `series.values`。当正文和数据描述冲突时，系统要求模型按结构化程度、字段完整性、数值可解释性和一致性选择更可靠的数据，并在 `warnings` 中说明。

### 3. 多格式图表代码生成

接口：`POST /api/viz-lab/chart-code`

这一阶段在有 Key 时会尝试调用 DeepSeek，默认生成三类代码：

- `echartsOption`
- `chartJsConfig`
- `mermaidSource`

图表代码生成 prompt 会把语义分析结果作为 `semantic_hint`，要求模型不得重新发明数据。固定返回 JSON：

```json
{
  "echartsOption": {},
  "chartJsConfig": {},
  "mermaidSource": "",
  "notes": [],
  "warnings": []
}
```

如果模型失败或只返回部分结果，系统会用本地规则补齐缺失部分，并返回 `source=llm+fallback` 或 `source=fallback`。响应还会包含 `generatedTargets`、`validationIssues`、`llmAttempted`、`llmSucceeded`、`fallbackReason` 和 `rawLlmExcerpt`，用于判断到底是否调用了 API、调用是否成功、哪些格式由 fallback 补齐。

### 4. 插图策略

接口：

- `POST /api/illustration`
- `POST /api/viz-lab/illustration`

这一阶段根据页面文本和语义结果生成插图关键词、prompt 和原因说明。当前 Demo 不直接生成图片。

## 图表意图和 chartType

当前支持的主要意图：

- `trend`：趋势，默认 `trend_line`
- `comparison`：对比，默认 `comparison_bar`
- `comparison_grouped`：多实体多指标分组柱状图
- `proportion`：同一整体构成，默认 `proportion_pie`
- `process`：流程，默认 `process_flow`
- `hierarchy`：层级，默认 `hierarchy_tree`
- `relation`：流向关系，默认 `relation_sankey`
- `data_table`：显式表格或矩阵

稳定性规则重点：

- 年份只作为 x 轴，不作为 y 值。
- `data_description` 中的结构化数据优先于正文自然语言。
- 增长率、转化率、同比、环比虽然带 `%`，默认是对比，不是饼图。
- 只有同一整体构成且合计接近 100 的百分比数据才使用饼图。
- 多实体多指标优先使用 `comparison_grouped`。
- 明确要求表格或矩阵时优先输出 `data_table`。
- 多条“来源 -> 目标 = 数值”的流向数据优先输出 `relation_sankey`。

## 主要接口

### `POST /api/extract-text`

上传 `.pptx` 或 `.pdf`，返回逐页文本和预览图地址。

### `POST /api/analyze`

请求体：

```json
{
  "topic": "年度营收趋势",
  "body": "过去5年营收持续增长，2021年120万元，2022年150万元，2023年190万元，2024年230万元，2025年280万元。",
  "data_description": "时间序列：2021,2022,2023,2024,2025；营收：120,150,190,230,280；单位：万元。",
  "slide_type": "content",
  "mode": "auto"
}
```

返回重点字段：

- `semantic.intent`
- `semantic.chartType`
- `semantic.extracted`
- `semantic.source`
- `chart.echartsOption`

### `POST /api/viz-lab/chart-code`

生成 ECharts / Chart.js / Mermaid 多格式图表代码，适合调试不同图表引擎的表达差异。

### `POST /api/illustration`

生成插图策略，包括是否需要插图、关键词、prompt 和原因。

## 稳定性测试

测试资产位于：

- `test/intent_chart_stability_test_deck.pptx`
- `test/intent_chart_stability_manifest.json`

重点回归用例：

- `T01` 年度营收趋势：必须输出 `trend / trend_line`，x 为 `2021..2025`，y 为 `120,150,190,230,280`。
- `T04` 多产品多指标：必须输出 `comparison / comparison_grouped`。
- `T05` 市场份额构成：必须输出 `proportion / proportion_pie`。
- `T06` 增长率不是构成占比：必须输出 `comparison / comparison_bar`。
- `T09` 预算流向关系：必须输出 `relation / relation_sankey`。
- `T10` 价格矩阵：必须输出 `comparison / data_table`。
- `T12` 中英混合转化率：必须输出 `comparison / comparison_bar`。

建议在每次修改意图分析或图表生成后批量跑 manifest，并检查前端图表预览。

## 常见问题

### 为什么上传解析没有使用 DeepSeek？

上传解析是文件结构读取和页面文本抽取，当前使用本地库完成，不调用模型。DeepSeek 主要用于语义分析、数据抽取归一化和多格式图表代码生成。

### 为什么我填了 DeepSeek Key，结果还是 mock？

检查 `.env`：

```env
MOCK_MODE=false
DEEPSEEK_API_KEY=你的 Key
```

如果 `MOCK_MODE=true`，`mode=auto` 会继续走本地规则。也可以在请求中设置 `mode=deepseek` 强制尝试模型。

### 图表生成效果差应该看哪里？

优先检查：

- `data_description` 是否提供了清晰结构化数据。
- `semantic.source` 是 `mock`、`deepseek` 还是 `fallback`。
- `semantic.extracted` 中的 x/y、labels/values、series 是否正确。
- `chart.chartType` 是否符合页面意图。

### Chart.js / Mermaid 和 ECharts 是什么关系？

ECharts 是主流程图表输出；Chart.js 和 Mermaid 是实验面板中的辅助表示，用来对比不同图表引擎的表达能力。复杂业务图表以 ECharts 的质量为主。