# LingDraw PPT Demo

一个用于课堂演示的轻量级端到端 Demo：支持输入幻灯片文本 → 语义识别 → 生成 ECharts 图表配置 → 输出插图策略（关键词 + Prompt）。

默认情况下走 **Mock/规则模式**，确保你不配置任何 API Key 也能跑通；如配置 `DEEPSEEK_API_KEY` 可在 `auto` 模式下调用 DeepSeek。

## 目录

- `backend/`：FastAPI 后端（`/api/analyze`、`/api/illustration`）
- `frontend/`：Vue3+Vite 前端（多页输入、图表预览、插图策略、导出 JSON/PPTX）

## 运行步骤

### 1) 后端启动

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

可选：配置环境变量

- 复制并编辑 `.env.example`，设置 `DEEPSEEK_API_KEY`（不想调用模型可保持空）
- 默认 `MOCK_MODE=true`，因此不会强制调用 DeepSeek

### 2) 启动前端

在仓库根目录执行：

```powershell
cd frontend
npm install
npm run dev
```

然后打开浏览器访问：
- `http://localhost:5173`

页面内有“后端地址”输入框，默认是 `http://127.0.0.1:8000`（保持后端端口一致即可）。

## 测试账号（启动后自动创建）

后端启动时会自动确保以下两个账号存在，方便前端登录测试：

- 管理员账号
  - 用户名：`admin`
  - 密码：`admin123`
- 普通用户账号
  - 用户名：`tester`
  - 密码：`tester123`

你可以在 `.env` 中修改：

- `ADMIN_USERNAME` / `ADMIN_PASSWORD`
- `TEST_USERNAME` / `TEST_PASSWORD`

## 接口说明

1. `POST /api/analyze`
   - 输入：`topic`、`body`、`data_description`、`slide_type`、`mode`
   - 输出：`intent`、`chartType`、`echartsOption`（前端直接渲染）

2. `POST /api/illustration`
   - 输入同上
   - 输出：`needIllus`、`keywords`、`prompt`、`reason`

## 代表性测试用例（Mock 模式）

1. 趋势（折线图）
   - body：`过去5年销售额逐年增长，从100万增至500万`

2. 对比（柱状图）
   - body：`A产品评分4.2，B产品3.8，C产品4.5`

3. 比例（饼图）
   - body：`市场份额：我方40%，竞品A 35%，竞品B 25%`

前端会自动调用后端并渲染 ECharts 结果。

