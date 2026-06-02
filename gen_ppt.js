// LingDraw PPT - Milestone 1 Review PPT Generator
// Reference: Team06 style, detailed WBS breakdown
const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "LingDraw PPT - Milestone 1 Review";

// ============================================================
// Color Palette
// ============================================================
const C = {
  darkBg: "0D1B2A",       // dark navy bg
  accentBlue: "1A6EBD",   // primary blue
  accentCyan: "0EA5E9",   // cyan highlight
  accentGold: "F59E0B",   // gold accent
  accentGreen: "10B981",  // green (done)
  accentRed: "EF4444",    // red (risk)
  white: "FFFFFF",
  lightBg: "F0F4F8",
  cardBg: "FFFFFF",
  textDark: "1E293B",
  textGray: "64748B",
  borderGray: "CBD5E1",
  headerBg: "1A6EBD",
};

const FONT = "Microsoft YaHei";

// ============================================================
// Helper: shadow factory (fresh object each time - avoid mutation bug)
// ============================================================
function mkShadow() {
  return { type: "outer", color: "000000", blur: 6, offset: 2, angle: 135, opacity: 0.12 };
}

// ============================================================
// Helper: section header bar
// ============================================================
function addSectionBadge(slide, label, x, y) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.06, h: 0.3,
    fill: { color: C.accentCyan }, line: { color: C.accentCyan }
  });
  slide.addText(label, {
    x: x + 0.12, y: y, w: 5, h: 0.3,
    fontSize: 13, bold: true, color: C.accentBlue, fontFace: FONT, margin: 0, valign: "middle"
  });
}

// ============================================================
// Helper: WBS tag badge (small colored label)
// ============================================================
function addWbsTag(slide, tag, x, y, color) {
  const col = color || C.accentBlue;
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 1.1, h: 0.28,
    fill: { color: col }, line: { color: col }, rectRadius: 0.05
  });
  slide.addText(tag, {
    x: x + 0.05, y: y + 0.02, w: 1.0, h: 0.24,
    fontSize: 9, bold: true, color: C.white, fontFace: FONT,
    align: "center", valign: "middle", margin: 0
  });
}

// ============================================================
// Helper: status badge
// ============================================================
function addStatusBadge(slide, status, x, y) {
  const cfg = status === "done"
    ? { label: "已完成", color: C.accentGreen }
    : status === "partial"
    ? { label: "进行中", color: C.accentGold }
    : { label: "待完成", color: C.textGray };
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 0.9, h: 0.26,
    fill: { color: cfg.color }, line: { color: cfg.color }
  });
  slide.addText(cfg.label, {
    x, y, w: 0.9, h: 0.26,
    fontSize: 9, bold: true, color: C.white,
    fontFace: FONT, align: "center", valign: "middle", margin: 0
  });
}

// ============================================================
// Helper: content card (white card with shadow)
// ============================================================
function addCard(slide, x, y, w, h) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: C.cardBg }, line: { color: C.borderGray, width: 0.5 },
    shadow: mkShadow()
  });
}

// ============================================================
// Slide 1: Cover
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.darkBg };

  // Left accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.08, h: 5.625,
    fill: { color: C.accentCyan }, line: { color: C.accentCyan }
  });

  // Top right corner decoration
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 8.5, y: 0, w: 1.5, h: 1.8,
    fill: { color: C.accentBlue, transparency: 60 }, line: { color: C.accentBlue, transparency: 60 }
  });

  // Project name
  slide.addText("LingDraw PPT", {
    x: 0.5, y: 0.65, w: 9, h: 0.9,
    fontSize: 48, bold: true, color: C.white, fontFace: FONT
  });

  // Subtitle
  slide.addText("Milestone 1 评审汇报", {
    x: 0.5, y: 1.65, w: 9, h: 0.55,
    fontSize: 26, bold: false, color: C.accentCyan, fontFace: FONT
  });

  // Separator
  slide.addShape(pres.shapes.LINE, {
    x: 0.5, y: 2.35, w: 9, h: 0,
    line: { color: C.accentBlue, width: 1.5 }
  });

  // Meta info
  slide.addText([
    { text: "项目：", options: { bold: true, color: C.accentGold } },
    { text: "智能 PPT 配图与图表生成平台", options: { color: "B0C4DE" } },
    { text: "\n阶段：", options: { bold: true, color: C.accentGold } },
    { text: "Sprint 1 + Sprint 2（WBS 1.0 ~ 10.0）", options: { color: "B0C4DE" } },
    { text: "\n日期：", options: { bold: true, color: C.accentGold } },
    { text: "2026 年 5 月", options: { color: "B0C4DE" } },
  ], {
    x: 0.5, y: 2.55, w: 7, h: 1.2,
    fontSize: 15, fontFace: FONT, lineSpacingMultiple: 1.4
  });

  // Team members
  slide.addText("团队成员：UniqueMani · airaaaali · iAcane0963", {
    x: 0.5, y: 3.85, w: 9, h: 0.35,
    fontSize: 13, color: "7090A8", fontFace: FONT
  });

  // Bottom bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 5.3, w: 10, h: 0.325,
    fill: { color: C.accentBlue, transparency: 40 }, line: { color: C.accentBlue, transparency: 40 }
  });
  slide.addText("软件工程管理与经济 · LingDraw PPT Team", {
    x: 0.5, y: 5.3, w: 9, h: 0.325,
    fontSize: 10, color: "8AAFC8", fontFace: FONT, valign: "middle"
  });
}

// ============================================================
// Slide 2: Table of Contents
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  // Header
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("目  录", {
    x: 0.4, y: 0, w: 9.2, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });

  const items = [
    { num: "01", title: "项目背景与目标", sub: "问题定义 / 核心功能 / 技术路线" },
    { num: "02", title: "WBS 工时总览", sub: "预估 vs 实际工时 / 完成情况" },
    { num: "03", title: "Sprint 1 详细成果", sub: "WBS 1.0–5.0 / 章程·需求·架构·环境" },
    { num: "04", title: "Sprint 2 详细成果", sub: "WBS 6.0–10.0 / 语义·图表·配图·前端·联调" },
    { num: "05", title: "系统演示", sub: "前端界面 / 功能截图" },
    { num: "06", title: "问题与风险", sub: "遇到的挑战 / 应对措施" },
    { num: "07", title: "下一步计划", sub: "Milestone 2 目标" },
  ];

  items.forEach((item, i) => {
    const col = i < 4 ? 0 : 1;
    const row = i < 4 ? i : i - 4;
    const x = col === 0 ? 0.4 : 5.3;
    const y = 0.95 + row * 1.05;
    const w = 4.6;
    const h = 0.92;

    addCard(slide, x, y, w, h);

    // Number accent
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.55, h,
      fill: { color: C.accentBlue }, line: { color: C.accentBlue }
    });
    slide.addText(item.num, {
      x, y, w: 0.55, h,
      fontSize: 18, bold: true, color: C.white, fontFace: FONT, align: "center", valign: "middle", margin: 0
    });

    slide.addText(item.title, {
      x: x + 0.65, y: y + 0.1, w: w - 0.75, h: 0.35,
      fontSize: 13, bold: true, color: C.textDark, fontFace: FONT, margin: 0
    });
    slide.addText(item.sub, {
      x: x + 0.65, y: y + 0.46, w: w - 0.75, h: 0.35,
      fontSize: 10, color: C.textGray, fontFace: FONT, margin: 0
    });
  });
}

// ============================================================
// Slide 3: Project Background & Goal
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("01  项目背景与目标", {
    x: 0.4, y: 0, w: 9.2, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });

  // Left: Problem
  addCard(slide, 0.3, 0.9, 4.5, 2.2);
  addSectionBadge(slide, "痛点场景", 0.5, 0.98);
  slide.addText([
    { text: "制作 PPT 时，演讲者面临：", options: { breakLine: true } },
    { text: "  - 手动找图耗时，风格难以统一", options: { bullet: false, breakLine: true } },
    { text: "  - 图表类型选择困难，描述与图表语义对不上", options: { bullet: false, breakLine: true } },
    { text: "  - 配图与主题颜色不协调，美观度差", options: { bullet: false, breakLine: true } },
    { text: "  - 缺乏智能推荐，只能靠经验和审美", options: { bullet: false } },
  ], {
    x: 0.5, y: 1.35, w: 4.1, h: 1.6,
    fontSize: 12, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.4
  });

  // Right: Goal
  addCard(slide, 5.2, 0.9, 4.5, 2.2);
  addSectionBadge(slide, "项目目标（MOV）", 5.4, 0.98);
  slide.addText([
    { text: "让用户只需输入文字描述，系统自动：", options: { breakLine: true } },
    { text: "  - 分析语义意图，推荐最合适的图表类型", options: { breakLine: true } },
    { text: "  - 生成可编辑图表代码（ECharts / Matplotlib）", options: { breakLine: true } },
    { text: "  - 匹配场景语义，推荐并嵌入高质量配图", options: { breakLine: true } },
    { text: "  - 完整前端工作台，端到端体验", options: {} },
  ], {
    x: 5.4, y: 1.35, w: 4.1, h: 1.6,
    fontSize: 12, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.4
  });

  // Bottom: Tech Stack 3 columns
  const techCols = [
    { title: "前端", items: ["Vue 3 + TypeScript", "Vite + Pinia", "Axios / Router"] },
    { title: "后端", items: ["FastAPI + Uvicorn", "LLM API（Qwen/GPT）", "SQLite + python-pptx"] },
    { title: "工具链", items: ["Git + GitHub", "python-pptx / ECharts", "Markitdown / Playwright"] },
  ];
  techCols.forEach((col, i) => {
    const x = 0.3 + i * 3.2;
    addCard(slide, x, 3.25, 3.0, 1.9);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 3.25, w: 3.0, h: 0.38,
      fill: { color: C.accentBlue }, line: { color: C.accentBlue }
    });
    slide.addText(col.title, {
      x, y: 3.25, w: 3.0, h: 0.38,
      fontSize: 13, bold: true, color: C.white, fontFace: FONT, align: "center", valign: "middle", margin: 0
    });
    col.items.forEach((item, j) => {
      slide.addText(item, {
        x: x + 0.15, y: 3.7 + j * 0.38, w: 2.7, h: 0.35,
        fontSize: 12, color: C.textDark, fontFace: FONT, margin: 0
      });
    });
  });
}

// ============================================================
// Slide 4: WBS Work Hours Overview
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("02  WBS 工时总览", {
    x: 0.4, y: 0, w: 9.2, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });

  // Table
  const headers = [
    { text: "WBS", options: { bold: true, color: C.white, fill: { color: C.accentBlue }, align: "center" } },
    { text: "工作包名称", options: { bold: true, color: C.white, fill: { color: C.accentBlue } } },
    { text: "负责人", options: { bold: true, color: C.white, fill: { color: C.accentBlue }, align: "center" } },
    { text: "预估 (h)", options: { bold: true, color: C.white, fill: { color: C.accentBlue }, align: "center" } },
    { text: "实际 (h)", options: { bold: true, color: C.white, fill: { color: C.accentBlue }, align: "center" } },
    { text: "状态", options: { bold: true, color: C.white, fill: { color: C.accentBlue }, align: "center" } },
  ];

  const rows = [
    ["1.0", "项目章程 & 范围管理", "全体", "8", "9", { text: "✓ 完成", options: { color: C.accentGreen, bold: true, align: "center" } }],
    ["2.0", "RBS 需求分析", "全体", "10", "12", { text: "✓ 完成", options: { color: C.accentGreen, bold: true, align: "center" } }],
    ["3.0", "系统架构设计", "UniqueMani", "12", "14", { text: "✓ 完成", options: { color: C.accentGreen, bold: true, align: "center" } }],
    ["4.0", "开发环境搭建", "全体", "6", "7", { text: "✓ 完成", options: { color: C.accentGreen, bold: true, align: "center" } }],
    ["5.0", "输入预处理模块", "airaaaali", "12", "13", { text: "✓ 完成", options: { color: C.accentGreen, bold: true, align: "center" } }],
    ["6.0", "语义分析与图表推荐", "airaaaali", "15", "16", { text: "✓ 完成", options: { color: C.accentGreen, bold: true, align: "center" } }],
    ["7.0", "图表代码生成", "airaaaali", "15", "17", { text: "✓ 完成", options: { color: C.accentGreen, bold: true, align: "center" } }],
    ["8.0", "配图策略与检索", "UniqueMani", "14", "14", { text: "✓ 完成", options: { color: C.accentGreen, bold: true, align: "center" } }],
    ["9.0", "前端界面开发", "iAcane0963", "18", "20", { text: "✓ 完成", options: { color: C.accentGreen, bold: true, align: "center" } }],
    ["10.0", "前后端联调", "全体", "10", "11", { text: "✓ 完成", options: { color: C.accentGreen, bold: true, align: "center" } }],
    [
      { text: "合计", options: { bold: true } }, "",
      "",
      { text: "120 h", options: { bold: true } },
      { text: "133 h", options: { bold: true, color: C.accentGold } },
      { text: "100%", options: { bold: true, color: C.accentGreen } }
    ],
  ];

  const tableData = [headers, ...rows];

  slide.addTable(tableData, {
    x: 0.3, y: 0.85, w: 9.4, h: 4.5,
    fontSize: 11, fontFace: FONT,
    border: { pt: 0.5, color: C.borderGray },
    rowH: 0.38,
    colW: [0.6, 3.0, 1.3, 0.95, 0.95, 0.95],
  });

  // Note
  slide.addText("* 实际工时含沟通、测试、返工等附加工作量，超出预估约 10.8%，处于合理范围内", {
    x: 0.3, y: 5.35, w: 9.4, h: 0.25,
    fontSize: 9, color: C.textGray, fontFace: FONT, italic: true
  });
}

// ============================================================
// Slide 5: Sprint 1 — WBS 1.0 & 2.0
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("03  Sprint 1 详细成果", {
    x: 0.4, y: 0, w: 7, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });
  slide.addText("WBS 1.0 ~ 5.0", {
    x: 7.5, y: 0, w: 2.2, h: 0.75,
    fontSize: 14, color: C.accentCyan, fontFace: FONT, valign: "middle", align: "right"
  });

  // WBS 1.0
  addCard(slide, 0.3, 0.88, 4.55, 2.3);
  addWbsTag(slide, "WBS 1.0", 0.5, 0.92);
  addStatusBadge(slide, "done", 3.45, 0.92);
  slide.addText("项目章程 & 范围管理", {
    x: 0.5, y: 1.3, w: 4.1, h: 0.32,
    fontSize: 14, bold: true, color: C.textDark, fontFace: FONT, margin: 0
  });
  slide.addText([
    { text: "完成项目章程文档，明确项目目标、范围边界、风险登记册。", options: { breakLine: true } },
    { text: "制定项目管理规范：分支策略（main/dev/feature）、代码审查流程、周会制度。", options: { breakLine: true } },
    { text: "初始化 GitHub 仓库，配置 .gitignore / CI 基础设施。", options: {} },
  ], {
    x: 0.5, y: 1.65, w: 4.15, h: 1.35,
    fontSize: 11, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.45
  });

  // WBS 2.0
  addCard(slide, 5.15, 0.88, 4.55, 2.3);
  addWbsTag(slide, "WBS 2.0", 5.35, 0.92);
  addStatusBadge(slide, "done", 8.3, 0.92);
  slide.addText("RBS 需求分析", {
    x: 5.35, y: 1.3, w: 4.1, h: 0.32,
    fontSize: 14, bold: true, color: C.textDark, fontFace: FONT, margin: 0
  });
  slide.addText([
    { text: "完成 RBS（需求分解结构）文档，识别 7 大功能域：用户管理、输入处理、语义分析、图表生成、配图检索、前端展示、系统集成。", options: { breakLine: true } },
    { text: "用户调研（问卷 + 访谈），确定核心用户画像，提取 MVP 需求集。", options: {} },
  ], {
    x: 5.35, y: 1.65, w: 4.15, h: 1.35,
    fontSize: 11, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.45
  });

  // WBS 3.0
  addCard(slide, 0.3, 3.3, 4.55, 2.2);
  addWbsTag(slide, "WBS 3.0", 0.5, 3.34);
  addStatusBadge(slide, "done", 3.45, 3.34);
  slide.addText("系统架构设计", {
    x: 0.5, y: 3.72, w: 4.1, h: 0.32,
    fontSize: 14, bold: true, color: C.textDark, fontFace: FONT, margin: 0
  });
  slide.addText([
    { text: "确定前后端分离架构（Vue3 + FastAPI）。", options: { breakLine: true } },
    { text: "设计核心数据流：Slide 文本 → NLP 分析 → 图表类型决策 → 代码生成 → 配图嵌入。", options: { breakLine: true } },
    { text: "定义 RESTful API 接口规范（/api/analyze、/api/chart、/api/image）。", options: {} },
  ], {
    x: 0.5, y: 4.07, w: 4.15, h: 1.3,
    fontSize: 11, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.45
  });

  // WBS 4.0
  addCard(slide, 5.15, 3.3, 4.55, 2.2);
  addWbsTag(slide, "WBS 4.0", 5.35, 3.34);
  addStatusBadge(slide, "done", 8.3, 3.34);
  slide.addText("开发环境搭建", {
    x: 5.35, y: 3.72, w: 4.1, h: 0.32,
    fontSize: 14, bold: true, color: C.textDark, fontFace: FONT, margin: 0
  });
  slide.addText([
    { text: "前端：Vite + Vue3 + TypeScript，配置 ESLint / Prettier 规范。", options: { breakLine: true } },
    { text: "后端：FastAPI + Uvicorn，Python 虚拟环境 (.venv) 隔离依赖。", options: { breakLine: true } },
    { text: "全体成员本地联调通过，端口约定：前端 5173，后端 8000。", options: {} },
  ], {
    x: 5.35, y: 4.07, w: 4.15, h: 1.3,
    fontSize: 11, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.45
  });
}

// ============================================================
// Slide 6: Sprint 1 — WBS 5.0
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("03  Sprint 1 详细成果", {
    x: 0.4, y: 0, w: 7, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });
  slide.addText("WBS 5.0", {
    x: 7.5, y: 0, w: 2.2, h: 0.75,
    fontSize: 14, color: C.accentCyan, fontFace: FONT, valign: "middle", align: "right"
  });

  addCard(slide, 0.3, 0.88, 9.4, 4.6);
  addWbsTag(slide, "WBS 5.0", 0.5, 0.95);
  addStatusBadge(slide, "done", 8.5, 0.95);
  slide.addText("输入预处理模块（by airaaaali）", {
    x: 0.5, y: 1.38, w: 9.0, h: 0.38,
    fontSize: 16, bold: true, color: C.textDark, fontFace: FONT, margin: 0
  });

  // 3 sub-modules
  const subCards = [
    {
      title: "5.1 PPT 文本抽取",
      items: [
        "使用 python-pptx 解析 .pptx 文件，逐页提取文本块（标题 + 正文）",
        "保留 Slide 层级结构，输出 JSON 格式（slide_id, title, body）",
        "处理空页、图片占位符、SmartArt 等边界情况",
      ]
    },
    {
      title: "5.2 文本清洗 & 分句",
      items: [
        "去除冗余符号、特殊字符、过短片段（<5 字）",
        "使用 jieba 分词 + 自定义停用词表进行中文预处理",
        "按语义相关性对句子进行分组，为后续意图分析做准备",
      ]
    },
    {
      title: "5.3 数据结构封装",
      items: [
        "定义 SlideContent / ChartHint 数据类，类型安全",
        "实现输入管道：Upload → Parse → Clean → Struct，可复用",
        "单元测试覆盖率 > 80%，通过 5 组真实 PPT 文件测试",
      ]
    },
  ];

  subCards.forEach((card, i) => {
    const x = 0.5 + i * 3.08;
    addCard(slide, x, 1.9, 2.9, 3.3);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.9, w: 2.9, h: 0.38,
      fill: { color: C.accentCyan, transparency: 15 }, line: { color: C.accentCyan, transparency: 15 }
    });
    slide.addText(card.title, {
      x: x + 0.1, y: 1.9, w: 2.7, h: 0.38,
      fontSize: 12, bold: true, color: C.white, fontFace: FONT, valign: "middle", margin: 0
    });
    card.items.forEach((item, j) => {
      slide.addText("• " + item, {
        x: x + 0.12, y: 2.38 + j * 0.82, w: 2.66, h: 0.72,
        fontSize: 11, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.3
      });
    });
  });
}

// ============================================================
// Slide 7: Sprint 2 — WBS 6.0 Semantic Analysis
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("04  Sprint 2 详细成果", {
    x: 0.4, y: 0, w: 7, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });
  slide.addText("WBS 6.0", {
    x: 7.5, y: 0, w: 2.2, h: 0.75,
    fontSize: 14, color: C.accentCyan, fontFace: FONT, valign: "middle", align: "right"
  });

  addCard(slide, 0.3, 0.88, 9.4, 4.6);
  addWbsTag(slide, "WBS 6.0", 0.5, 0.95);
  addStatusBadge(slide, "done", 8.5, 0.95);
  slide.addText("语义分析与图表推荐（by airaaaali）", {
    x: 0.5, y: 1.38, w: 9.0, h: 0.38,
    fontSize: 16, bold: true, color: C.textDark, fontFace: FONT, margin: 0
  });

  const subCards = [
    {
      title: "6.1 LLM 意图识别",
      items: [
        "调用大语言模型（Qwen / GPT）分析 Slide 文本语义意图",
        "识别对比、趋势、占比、流程、关系五类图表语义",
        "输出结构化 JSON：intent / confidence / keywords",
      ]
    },
    {
      title: "6.2 图表类型决策",
      items: [
        "基于意图 + 数据维度规则库推荐图表类型",
        "支持 10+ 种图表：柱状图、折线图、饼图、散点图等",
        "多候选排序输出，前端可交互选择",
      ]
    },
    {
      title: "6.3 Prompt 工程",
      items: [
        "设计 Chain-of-Thought Prompt 模板，减少幻觉",
        "Few-shot 示例覆盖典型业务场景（财务/技术/教学）",
        "A/B 测试 3 版 Prompt，准确率从 68% 提升至 89%",
      ]
    },
  ];

  subCards.forEach((card, i) => {
    const x = 0.5 + i * 3.08;
    addCard(slide, x, 1.9, 2.9, 3.3);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.9, w: 2.9, h: 0.38,
      fill: { color: C.accentBlue, transparency: 10 }, line: { color: C.accentBlue, transparency: 10 }
    });
    slide.addText(card.title, {
      x: x + 0.1, y: 1.9, w: 2.7, h: 0.38,
      fontSize: 12, bold: true, color: C.white, fontFace: FONT, valign: "middle", margin: 0
    });
    card.items.forEach((item, j) => {
      slide.addText("• " + item, {
        x: x + 0.12, y: 2.38 + j * 0.82, w: 2.66, h: 0.72,
        fontSize: 11, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.3
      });
    });
  });
}

// ============================================================
// Slide 8: Sprint 2 — WBS 7.0 Chart Code Generation
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("04  Sprint 2 详细成果", {
    x: 0.4, y: 0, w: 7, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });
  slide.addText("WBS 7.0", {
    x: 7.5, y: 0, w: 2.2, h: 0.75,
    fontSize: 14, color: C.accentCyan, fontFace: FONT, valign: "middle", align: "right"
  });

  addCard(slide, 0.3, 0.88, 9.4, 4.6);
  addWbsTag(slide, "WBS 7.0", 0.5, 0.95);
  addStatusBadge(slide, "done", 8.5, 0.95);
  slide.addText("图表代码生成（by airaaaali）", {
    x: 0.5, y: 1.38, w: 9.0, h: 0.38,
    fontSize: 16, bold: true, color: C.textDark, fontFace: FONT, margin: 0
  });

  const subCards = [
    {
      title: "7.1 ECharts 代码生成",
      items: [
        "LLM 根据图表类型 + 原始数据生成可运行 ECharts option JSON",
        "输出含完整配置：title / legend / xAxis / series / color",
        "前端 ChartCodeView 可直接渲染预览并支持手动编辑",
      ]
    },
    {
      title: "7.2 Viz Engine",
      items: [
        "新增 viz_engine.py，负责图表渲染与导出",
        "支持将 ECharts option 通过 Pyppeteer 无头渲染为 PNG",
        "支持嵌入 python-pptx，生成含图表的完整幻灯片",
      ]
    },
    {
      title: "7.3 质量保障",
      items: [
        "实现代码沙箱执行验证，防止语法错误代码进入导出流程",
        "异常降级：LLM 生成失败时回退至模板图表",
        "chart_code_llm.py 单元测试覆盖 12 类图表场景",
      ]
    },
  ];

  subCards.forEach((card, i) => {
    const x = 0.5 + i * 3.08;
    addCard(slide, x, 1.9, 2.9, 3.3);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.9, w: 2.9, h: 0.38,
      fill: { color: C.accentGold, transparency: 10 }, line: { color: C.accentGold, transparency: 10 }
    });
    slide.addText(card.title, {
      x: x + 0.1, y: 1.9, w: 2.7, h: 0.38,
      fontSize: 12, bold: true, color: C.white, fontFace: FONT, valign: "middle", margin: 0
    });
    card.items.forEach((item, j) => {
      slide.addText("• " + item, {
        x: x + 0.12, y: 2.38 + j * 0.82, w: 2.66, h: 0.72,
        fontSize: 11, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.3
      });
    });
  });
}

// ============================================================
// Slide 9: Sprint 2 — WBS 8.0 Image Strategy
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("04  Sprint 2 详细成果", {
    x: 0.4, y: 0, w: 7, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });
  slide.addText("WBS 8.0", {
    x: 7.5, y: 0, w: 2.2, h: 0.75,
    fontSize: 14, color: C.accentCyan, fontFace: FONT, valign: "middle", align: "right"
  });

  addCard(slide, 0.3, 0.88, 9.4, 4.6);
  addWbsTag(slide, "WBS 8.0", 0.5, 0.95);
  addStatusBadge(slide, "done", 8.5, 0.95);
  slide.addText("配图策略与检索（by UniqueMani）", {
    x: 0.5, y: 1.38, w: 9.0, h: 0.38,
    fontSize: 16, bold: true, color: C.textDark, fontFace: FONT, margin: 0
  });

  const subCards = [
    {
      title: "8.1 语义关键词提取",
      items: [
        "从 Slide 文本提取视觉语义关键词（场景词 + 情感词）",
        "LLM 辅助关键词扩展，提升检索召回率",
        "支持中英文双语检索词生成",
      ]
    },
    {
      title: "8.2 图片检索引擎",
      items: [
        "对接 Unsplash API 实现高清图片检索",
        "基于 CLIP 视觉语义模型做图片相关度排序",
        "IllustrationPromptView 展示候选图并支持一键替换",
      ]
    },
    {
      title: "8.3 配图嵌入导出",
      items: [
        "选定图片自动下载并通过 python-pptx 嵌入目标 Slide",
        "支持图片位置/尺寸自动适配（16:9 比例裁剪）",
        "ResultPanel 实时预览配图效果",
      ]
    },
  ];

  subCards.forEach((card, i) => {
    const x = 0.5 + i * 3.08;
    addCard(slide, x, 1.9, 2.9, 3.3);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.9, w: 2.9, h: 0.38,
      fill: { color: C.accentGreen, transparency: 10 }, line: { color: C.accentGreen, transparency: 10 }
    });
    slide.addText(card.title, {
      x: x + 0.1, y: 1.9, w: 2.7, h: 0.38,
      fontSize: 12, bold: true, color: C.white, fontFace: FONT, valign: "middle", margin: 0
    });
    card.items.forEach((item, j) => {
      slide.addText("• " + item, {
        x: x + 0.12, y: 2.38 + j * 0.82, w: 2.66, h: 0.72,
        fontSize: 11, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.3
      });
    });
  });
}

// ============================================================
// Slide 10: Sprint 2 — WBS 9.0 & 10.0
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("04  Sprint 2 详细成果", {
    x: 0.4, y: 0, w: 7, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });
  slide.addText("WBS 9.0 & 10.0", {
    x: 6.8, y: 0, w: 2.9, h: 0.75,
    fontSize: 14, color: C.accentCyan, fontFace: FONT, valign: "middle", align: "right"
  });

  // WBS 9.0 - Frontend
  addCard(slide, 0.3, 0.88, 9.4, 2.35);
  addWbsTag(slide, "WBS 9.0", 0.5, 0.95);
  addStatusBadge(slide, "done", 8.5, 0.95);
  slide.addText("前端界面开发（by iAcane0963）", {
    x: 0.5, y: 1.36, w: 9.0, h: 0.34,
    fontSize: 15, bold: true, color: C.textDark, fontFace: FONT, margin: 0
  });

  const fe = [
    "Vue Router 路由体系：登录守卫 + 4 大功能页面（HomeView / UploadView / WorkspaceView / ChartIntentView）",
    "全局 reactive Store：封装用户状态、Slide 上下文、图表推荐结果，跨组件共享",
    "WorkspaceView 核心工作台（最大组件 ~600 行）：集成文件上传、语义分析触发、图表/配图预览、导出一键操作",
    "前端重构：将 App.vue 从 615 行精简为 60 行路由出口，拆分职责，性能大幅提升",
  ];
  fe.forEach((item, i) => {
    slide.addText("• " + item, {
      x: 0.5, y: 1.78 + i * 0.35, w: 9.0, h: 0.32,
      fontSize: 11, color: C.textDark, fontFace: FONT, margin: 0, lineSpacingMultiple: 1.2
    });
  });

  // WBS 10.0 - Integration
  addCard(slide, 0.3, 3.35, 9.4, 2.15);
  addWbsTag(slide, "WBS 10.0", 0.5, 3.42);
  addStatusBadge(slide, "done", 8.5, 3.42);
  slide.addText("前后端联调（全体）", {
    x: 0.5, y: 3.83, w: 9.0, h: 0.34,
    fontSize: 15, bold: true, color: C.textDark, fontFace: FONT, margin: 0
  });

  const int = [
    "统一 API 调用规范：前端通过 api/client.ts 封装所有请求，统一错误处理与 Loading 状态",
    "端到端测试：Upload → Analyze → Chart推荐 → 配图检索 → 导出 PPTX，全流程通过验证",
    "CORS 配置、鉴权 Token 传递、跨服务数据格式对齐（字段名 snake_case 统一）",
  ];
  int.forEach((item, i) => {
    slide.addText("• " + item, {
      x: 0.5, y: 4.25 + i * 0.38, w: 9.0, h: 0.34,
      fontSize: 11, color: C.textDark, fontFace: FONT, margin: 0
    });
  });
}

// ============================================================
// Slide 11: System Demo (Screenshots placeholder)
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("05  系统演示", {
    x: 0.4, y: 0, w: 9.2, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });

  const screens = [
    { title: "登录 / 注册页", desc: "用户认证，支持注册与登录" },
    { title: "工作台总览", desc: "文件列表、Slide 预览" },
    { title: "图表意图页", desc: "语义意图选择与图表类型推荐" },
    { title: "配图选择页", desc: "语义关键词 + CLIP 排序结果" },
  ];

  const ssFiles = [
    "screenshots/screenshot-1.png",
    "screenshots/screenshot-2.png",
    "screenshots/screenshot-3.png",
    "screenshots/screenshot-4.png",
  ];

  screens.forEach((s, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.25 + col * 5.0;
    const y = 0.9 + row * 2.35;

    addCard(slide, x, y, 4.6, 2.2);

    // Try to embed screenshot
    try {
      const fs = require("fs");
      if (fs.existsSync(ssFiles[i])) {
        slide.addImage({ path: ssFiles[i], x: x + 0.08, y: y + 0.08, w: 4.44, h: 1.6 });
      } else {
        slide.addShape(pres.shapes.RECTANGLE, {
          x: x + 0.08, y: y + 0.08, w: 4.44, h: 1.6,
          fill: { color: "E2E8F0" }, line: { color: C.borderGray }
        });
        slide.addText("[ 截图待补充 ]", {
          x: x + 0.08, y: y + 0.08, w: 4.44, h: 1.6,
          fontSize: 13, color: C.textGray, fontFace: FONT, align: "center", valign: "middle"
        });
      }
    } catch (e) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: x + 0.08, y: y + 0.08, w: 4.44, h: 1.6,
        fill: { color: "E2E8F0" }, line: { color: C.borderGray }
      });
    }

    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: y + 1.72, w: 4.6, h: 0.48,
      fill: { color: "F8FAFC" }, line: { color: C.borderGray }
    });
    slide.addText(s.title, {
      x: x + 0.1, y: y + 1.75, w: 4.4, h: 0.22,
      fontSize: 11, bold: true, color: C.textDark, fontFace: FONT, margin: 0
    });
    slide.addText(s.desc, {
      x: x + 0.1, y: y + 1.97, w: 4.4, h: 0.2,
      fontSize: 10, color: C.textGray, fontFace: FONT, margin: 0
    });
  });
}

// ============================================================
// Slide 12: Issues & Risks
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("06  遇到的问题与风险", {
    x: 0.4, y: 0, w: 9.2, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });

  const issues = [
    {
      tag: "技术问题",
      color: C.accentRed,
      title: "LLM Prompt 幻觉问题",
      desc: "早期 Prompt 设计过于开放，LLM 偶发生成与数据不符的图表配置。\n应对：引入 Few-shot 示例 + JSON Schema 约束输出格式，准确率从 68% 提升至 89%。",
    },
    {
      tag: "技术问题",
      color: C.accentRed,
      title: "前端重构工作量超估",
      desc: "接手时 App.vue 高达 615 行，职责混乱，需大幅重构才能集成 Router 和 Store。\n应对：用 2 天完成拆分重构，WBS 9.0 实际工时增加约 2h。",
    },
    {
      tag: "协作问题",
      color: C.accentGold,
      title: "API 接口字段命名不一致",
      desc: "前后端在字段命名上（camelCase vs snake_case）出现对接问题，导致联调初期报错。\n应对：建立接口文档规范，统一使用 snake_case，前端封装转换层。",
    },
    {
      tag: "外部依赖",
      color: C.textGray,
      title: "Unsplash API 免费配额限制",
      desc: "Unsplash 免费 API 每小时限 50 次请求，高频测试时触发限流。\n应对：本地缓存已检索图片结果，减少重复请求；申请开发者配额提升。",
    },
  ];

  issues.forEach((issue, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.3 + col * 4.85;
    const y = 0.9 + row * 2.3;

    addCard(slide, x, y, 4.6, 2.15);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.06, h: 2.15,
      fill: { color: issue.color }, line: { color: issue.color }
    });

    // Tag badge
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x + 0.15, y: y + 0.1, w: 0.85, h: 0.24,
      fill: { color: issue.color, transparency: 20 }, line: { color: issue.color }
    });
    slide.addText(issue.tag, {
      x: x + 0.15, y: y + 0.1, w: 0.85, h: 0.24,
      fontSize: 9, bold: true, color: C.white, fontFace: FONT, align: "center", valign: "middle", margin: 0
    });

    slide.addText(issue.title, {
      x: x + 0.15, y: y + 0.42, w: 4.3, h: 0.3,
      fontSize: 13, bold: true, color: C.textDark, fontFace: FONT, margin: 0
    });
    slide.addText(issue.desc, {
      x: x + 0.15, y: y + 0.78, w: 4.35, h: 1.28,
      fontSize: 10.5, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.4
    });
  });
}

// ============================================================
// Slide 13: Next Steps — Milestone 2
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.lightBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.75,
    fill: { color: C.headerBg }, line: { color: C.headerBg }
  });
  slide.addText("07  下一步计划 — Milestone 2", {
    x: 0.4, y: 0, w: 9.2, h: 0.75,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT, valign: "middle"
  });

  const m2Tasks = [
    {
      id: "M2-1",
      color: C.accentBlue,
      title: "Viz Engine 完善",
      owner: "airaaaali",
      items: [
        "支持更多图表类型（雷达图、热力图、旭日图）",
        "图表渲染性能优化，无头浏览器改用 Playwright",
        "导出 PNG / SVG / ECharts JSON 三格式",
      ]
    },
    {
      id: "M2-2",
      color: C.accentCyan,
      title: "配图质量提升",
      owner: "UniqueMani",
      items: [
        "接入 Pexels API 扩充图源",
        "基于 CLIP 实现视觉-语义双重过滤，提升精准度",
        "支持自定义上传图片替换候选",
      ]
    },
    {
      id: "M2-3",
      color: C.accentGold,
      title: "PPTX 导出完整化",
      owner: "全体",
      items: [
        "支持完整幻灯片批量导出（含图表 + 配图）",
        "保留原始 PPT 样式与主题色",
        "导出进度条 UI + 后台任务队列",
      ]
    },
    {
      id: "M2-4",
      color: C.accentGreen,
      title: "测试与文档",
      owner: "iAcane0963",
      items: [
        "端到端自动化测试（Playwright E2E）",
        "API 接口文档（Swagger / Redoc）",
        "用户使用手册 + 视频演示录制",
      ]
    },
  ];

  m2Tasks.forEach((task, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.3 + col * 4.85;
    const y = 0.9 + row * 2.3;

    addCard(slide, x, y, 4.6, 2.2);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 4.6, h: 0.42,
      fill: { color: task.color }, line: { color: task.color }
    });
    slide.addText(task.id + "  " + task.title, {
      x: x + 0.12, y, w: 3.5, h: 0.42,
      fontSize: 13, bold: true, color: C.white, fontFace: FONT, valign: "middle", margin: 0
    });
    slide.addText("By: " + task.owner, {
      x: x + 3.4, y, w: 1.1, h: 0.42,
      fontSize: 10, color: "CCE5FF", fontFace: FONT, valign: "middle", align: "right", margin: 0
    });

    task.items.forEach((item, j) => {
      slide.addText("• " + item, {
        x: x + 0.15, y: y + 0.52 + j * 0.52, w: 4.3, h: 0.48,
        fontSize: 11, color: C.textDark, fontFace: FONT, lineSpacingMultiple: 1.3
      });
    });
  });
}

// ============================================================
// Slide 14: Closing
// ============================================================
{
  const slide = pres.addSlide();
  slide.background = { color: C.darkBg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.08,
    fill: { color: C.accentCyan }, line: { color: C.accentCyan }
  });

  slide.addText("Thank You", {
    x: 0, y: 1.6, w: 10, h: 1.1,
    fontSize: 54, bold: true, color: C.white, fontFace: FONT, align: "center"
  });

  slide.addText("LingDraw PPT · Milestone 1 完成", {
    x: 0, y: 2.85, w: 10, h: 0.5,
    fontSize: 20, color: C.accentCyan, fontFace: FONT, align: "center"
  });

  slide.addShape(pres.shapes.LINE, {
    x: 3, y: 3.5, w: 4, h: 0,
    line: { color: C.accentBlue, width: 1 }
  });

  slide.addText([
    { text: "GitHub: ", options: { bold: true, color: C.accentGold } },
    { text: "github.com/UniqueMani/LingDrawPPT", options: { color: "8AAFC8" } },
    { text: "   Branch: ", options: { bold: true, color: C.accentGold } },
    { text: "aira-4.12version", options: { color: "8AAFC8" } },
  ], {
    x: 0, y: 3.7, w: 10, h: 0.45,
    fontSize: 13, fontFace: FONT, align: "center"
  });

  slide.addText("团队成员：UniqueMani · airaaaali · iAcane0963", {
    x: 0, y: 4.3, w: 10, h: 0.35,
    fontSize: 12, color: "506070", fontFace: FONT, align: "center"
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 5.3, w: 10, h: 0.325,
    fill: { color: C.accentBlue, transparency: 40 }, line: { color: C.accentBlue, transparency: 40 }
  });
  slide.addText("软件工程管理与经济 · LingDraw PPT Team", {
    x: 0.5, y: 5.3, w: 9, h: 0.325,
    fontSize: 10, color: "8AAFC8", fontFace: FONT, valign: "middle"
  });
}

// ============================================================
// Write File
// ============================================================
pres.writeFile({ fileName: "LingDrawPPT-Milestone1-Review-v2.pptx" })
  .then(() => console.log("PPT generated: LingDrawPPT-Milestone1-Review-v2.pptx (14 slides)"))
  .catch(err => console.error("Error:", err));
