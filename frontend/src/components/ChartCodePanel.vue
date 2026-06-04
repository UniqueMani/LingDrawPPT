<script setup lang="ts">
import { Chart, registerables } from "chart.js";
import * as echarts from "echarts";
import mermaid from "mermaid";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { store } from "../store";
import { vizLabChartCode } from "../api/client";
import SlideInputForm from "./SlideInputForm.vue";
import type { SlideRequest, VizLabChartCodeResponse } from "../types";

Chart.register(...registerables);
mermaid.initialize({ startOnLoad: false, securityLevel: "loose", theme: "neutral" });

const slide = defineModel<SlideRequest>("slide", { required: true });
const props = defineProps<{
  initialResult?: VizLabChartCodeResponse | null;
  initialEchartsOption?: Record<string, any> | null;
  initialIntent?: string | null;
  initialChartType?: string | null;
  initialReason?: string | null;
  hideSlideInput?: boolean;
}>();
const emit = defineEmits<{
  result: [result: VizLabChartCodeResponse];
}>();

const tgtEcharts = ref(true);
const tgtChartjs = ref(true);
const tgtMermaid = ref(true);
const instructions = ref(
  "三套表示数据一致；柱状/折线需坐标轴；饼图切片名不重复；Mermaid 使用合法 pie / xychart-beta / flowchart 语法。"
);

const loading = ref(false);
const err = ref("");
const result = ref<VizLabChartCodeResponse | null>(null);
const displayResult = computed(() => result.value || props.initialResult || null);
const displayEchartsOption = computed(() =>
  displayResult.value ? displayResult.value.echartsOption || null : props.initialEchartsOption || null
);
const hasDisplayResult = computed(() => Boolean(displayResult.value || displayEchartsOption.value));

const intentLabels: Record<string, string> = {
  trend: "趋势分析",
  comparison: "对比分析",
  proportion: "占比构成",
  process: "流程步骤",
  hierarchy: "层级结构",
  relation: "关系流向",
};

const chartTypeLabels: Record<string, string> = {
  trend_line: "折线趋势图",
  comparison_bar: "柱状对比图",
  comparison_grouped: "分组柱状图",
  proportion_pie: "饼图",
  process_flow: "流程图",
  hierarchy_tree: "层级树图",
  relation_sankey: "桑基关系图",
  data_table: "数据表格",
};

const sourceLabels: Record<string, string> = {
  deepseek: "DeepSeek 模型",
  llm: "大模型生成",
  "llm+fallback": "大模型生成 + 本地规则补全",
  fallback: "本地规则补全",
  mock: "演示规则",
};

const targetLabels: Record<string, string> = {
  echarts: "ECharts 图表配置",
  chartjs: "Chart.js 图表配置",
  mermaid: "Mermaid 图示源码",
};

const chartJsCanvas = ref<HTMLCanvasElement | null>(null);
const mermaidHost = ref<HTMLDivElement | null>(null);
const echartsEl = ref<HTMLDivElement | null>(null);
let chartJsInstance: Chart | null = null;
let echartsInstance: echarts.ECharts | null = null;
let echartsResizeObserver: ResizeObserver | null = null;

function labelOf(map: Record<string, string>, value: unknown) {
  const key = String(value || "");
  return map[key] || key || "未知";
}

function targetLabelList(values: string[] | undefined) {
  return (values || []).map((item) => labelOf(targetLabels, item)).join("、");
}

function llmStatusLabel(item: VizLabChartCodeResponse) {
  if (!item.llmAttempted) return "未调用大模型";
  return item.llmSucceeded ? "调用成功" : "调用失败，已降级";
}

function cleanupMermaidArtifacts(id: string) {
  document.getElementById(id)?.remove();
  document.querySelectorAll(`[id^="${id}"]`).forEach((node) => {
    if (node instanceof HTMLElement || node instanceof SVGElement) node.remove();
  });
}

function destroyChartJs() {
  if (chartJsInstance) {
    chartJsInstance.destroy();
    chartJsInstance = null;
  }
}

function destroyEcharts() {
  echartsResizeObserver?.disconnect();
  echartsResizeObserver = null;
  if (echartsInstance) {
    echartsInstance.dispose();
    echartsInstance = null;
  }
}

async function renderMermaid(code: string) {
  const el = mermaidHost.value;
  if (!el) return;
  el.innerHTML = "";
  el.classList.remove("mmd-err");
  if (!code?.trim()) {
    el.textContent = "（无 Mermaid）";
    return;
  }
  const id = `mmd-${Date.now().toString(36)}`;
  try {
    await (mermaid as any).parse(code);
    const { svg } = await mermaid.render(id, code);
    el.innerHTML = svg;
  } catch (e: any) {
    cleanupMermaidArtifacts(id);
    const message = String(e?.message || e || "未知 Mermaid 渲染错误").split("\n").slice(0, 3).join("\n");
    el.textContent = `Mermaid 预览失败：源码语法仍需调整。\n${message}`;
    el.classList.add("mmd-err");
  }
}

function renderChartJs(cfg: Record<string, any> | null | undefined) {
  destroyChartJs();
  const canvas = chartJsCanvas.value;
  if (!canvas || !cfg || typeof cfg !== "object") return;
  try {
    chartJsInstance = new Chart(canvas, cfg as any);
  } catch (e) {
    console.warn(e);
  }
}

function renderEcharts(opt: Record<string, any> | null | undefined) {
  destroyEcharts();
  const dom = echartsEl.value;
  if (!dom || !opt || typeof opt !== "object" || !Object.keys(opt).length) return;
  try {
    echartsInstance = echarts.init(dom, undefined, { renderer: "svg" });
    echartsResizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(() => {
        echartsInstance?.resize();
      });
    });
    echartsResizeObserver.observe(dom);
    echartsInstance.resize();
    echartsInstance.setOption(opt, true);
  } catch (e) {
    console.warn(e);
  }
}

async function run() {
  loading.value = true;
  err.value = "";
  result.value = null;
  destroyChartJs();
  destroyEcharts();
  if (mermaidHost.value) {
    mermaidHost.value.innerHTML = "";
    mermaidHost.value.classList.remove("mmd-err");
  }

  const targets: string[] = [];
  if (tgtEcharts.value) targets.push("echarts");
  if (tgtChartjs.value) targets.push("chartjs");
  if (tgtMermaid.value) targets.push("mermaid");
  if (!targets.length) {
    err.value = "请至少选择一种输出形态。";
    loading.value = false;
    return;
  }

  try {
    const r = await vizLabChartCode(store.baseUrl, {
      slide: slide.value,
      targets,
      instructions: instructions.value || null,
    });
    result.value = r;
    emit("result", r);
    await nextTick();
    await nextTick();
    if (r.echartsOption) renderEcharts(r.echartsOption);
    if (r.chartJsConfig) renderChartJs(r.chartJsConfig);
    if (r.mermaidSource) await renderMermaid(r.mermaidSource);
  } catch (e: any) {
    err.value = e?.message || String(e);
  } finally {
    loading.value = false;
  }
}

watch(
  () => displayResult.value?.chartJsConfig,
  async (cfg) => {
    await nextTick();
    if (cfg) renderChartJs(cfg);
  },
  { immediate: true }
);
watch(
  () => displayResult.value?.mermaidSource,
  async (code) => {
    await nextTick();
    if (code) await renderMermaid(code);
  },
  { immediate: true }
);
watch(
  () => displayEchartsOption.value,
  async (opt) => {
    await nextTick();
    if (opt) renderEcharts(opt);
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  destroyChartJs();
  destroyEcharts();
});
</script>

<template>
  <div class="panel-root">
    <div class="panel">
      <h2>{{ hideSlideInput ? "图表生成配置" : "输入与 Prompt 约束" }}</h2>
      <SlideInputForm v-model="slide" :variant="hideSlideInput ? 'chart' : 'full'" />
      <div class="f">
        <label class="tl">附加约束（写入 LLM）</label>
        <textarea v-model="instructions" class="ta" rows="3" />
      </div>
      <div class="targets">
        <span class="tl">输出形态</span>
        <div class="target-options">
          <label><input v-model="tgtEcharts" type="checkbox" /> ECharts JSON</label>
          <label><input v-model="tgtChartjs" type="checkbox" /> Chart.js JSON</label>
          <label><input v-model="tgtMermaid" type="checkbox" /> Mermaid</label>
        </div>
      </div>
      <button
        class="btn"
        type="button"
        :disabled="loading || !(slide.topic?.trim() || slide.body?.trim())"
        @click="run"
      >
        {{ loading ? "生成中…" : "生成可渲染代码" }}
      </button>
      <p v-if="err" class="err">{{ err }}</p>
    </div>

    <div v-if="hasDisplayResult" class="panel meta">
      <div class="pills">
        <span v-if="props.initialIntent" class="pill">意图：{{ labelOf(intentLabels, props.initialIntent) }}</span>
        <span v-if="props.initialChartType" class="pill">图表类型：{{ labelOf(chartTypeLabels, props.initialChartType) }}</span>
        <span v-if="displayResult?.source" class="pill">来源：{{ labelOf(sourceLabels, displayResult.source) }}</span>
        <span v-if="displayResult?.generatedTargets?.length" class="pill">
          输出：{{ targetLabelList(displayResult.generatedTargets) }}
        </span>
        <span v-if="displayResult?.llmAttempted != null" class="pill">
          大模型状态：{{ llmStatusLabel(displayResult) }}
        </span>
      </div>
      <p v-if="props.initialReason" class="reason">{{ props.initialReason }}</p>
      <p v-if="displayResult?.fallbackReason" class="reason warn">降级原因：{{ displayResult.fallbackReason }}</p>
      <span v-if="displayResult" class="src">来源：{{ labelOf(sourceLabels, displayResult.source) }}</span>
      <div v-if="displayResult?.validationIssues?.length" class="issues">
        <h3>自动校验</h3>
        <ul>
          <li v-for="(it, i) in displayResult.validationIssues" :key="i" :class="it.severity">
            <b>{{ it.target }}</b> — {{ it.message }}
          </li>
        </ul>
      </div>
      <p v-else-if="displayResult" class="ok">未报告错误级问题（仍需人工核对语义）。</p>
      <details v-if="displayResult?.rawLlmExcerpt">
        <summary>LLM 原文摘录</summary>
        <pre class="pre sm">{{ displayResult.rawLlmExcerpt }}</pre>
      </details>
    </div>

    <div v-if="hasDisplayResult" class="previews">
      <div v-if="displayEchartsOption && tgtEcharts" class="pv">
        <h3>ECharts 预览</h3>
        <div ref="echartsEl" class="ech" />
        <details><summary>JSON</summary><pre class="pre">{{ JSON.stringify(displayEchartsOption, null, 2) }}</pre></details>
      </div>
      <div v-if="displayResult?.chartJsConfig && tgtChartjs" class="pv">
        <h3>Chart.js 预览</h3>
        <div class="cj"><canvas ref="chartJsCanvas" width="420" height="260" /></div>
        <details><summary>JSON</summary><pre class="pre">{{ JSON.stringify(displayResult.chartJsConfig, null, 2) }}</pre></details>
      </div>
      <div v-if="displayResult?.mermaidSource && tgtMermaid" class="pv wide">
        <h3>Mermaid 预览</h3>
        <p class="hint">Mermaid 会渲染为浏览器内的 SVG 图示，适合流程图、关系图和简易数据图，不是单独的 PPT 图片文件。</p>
        <div ref="mermaidHost" class="mmd" />
        <details><summary>源码</summary><pre class="pre">{{ displayResult.mermaidSource }}</pre></details>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel-root {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.panel {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0 0 var(--space-6);
  box-shadow: none;
  border-bottom: 1px solid var(--color-border);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
  transition: transform var(--motion-base) var(--motion-ease), box-shadow var(--motion-base) var(--motion-ease);
}
.panel:hover {
  box-shadow: none;
}
.panel h2,
.panel h3 {
  margin: 0 0 14px;
  font-size: 16px;
  font-weight: 800;
  color: var(--color-text);
}
.targets {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-2);
  margin: var(--space-4) 0 0;
}
.target-options {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3) var(--space-5);
  font-size: 14px;
}
.target-options label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-lg);
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text-soft);
  font-weight: 700;
}
.tl {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-muted);
}
.f {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-4);
}
.ta {
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  min-height: var(--control-lg);
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
  color: var(--color-text);
  background: var(--color-surface);
}
.ta:focus {
  border-color: var(--color-primary);
  outline: none;
  box-shadow: var(--shadow-focus);
}
.btn {
  min-height: var(--control-lg);
  margin-top: var(--space-4);
  padding: 0 24px;
  border: none;
  border-radius: var(--radius-control);
  background: var(--color-primary);
  color: #fff;
  font-weight: 800;
  cursor: pointer;
  transition: background var(--motion-base), transform var(--motion-base), box-shadow var(--motion-base);
}
.btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-card);
}
.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.err {
  color: var(--color-danger);
  margin-top: var(--space-3);
  background: var(--color-danger-soft);
  border: 1px solid #fee2e2;
  border-radius: var(--radius-control);
  padding: var(--space-3);
}
.pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.pill {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-border);
  padding: 6px 11px;
  border-radius: var(--radius-control);
  font-size: 12px;
  font-weight: 700;
}
.reason {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-primary);
  border-radius: var(--radius-control);
  padding: var(--space-3);
  font-size: 14px;
  color: var(--color-text-soft);
  line-height: 1.55;
  margin: 0 0 12px;
}
.reason.warn {
  border-left-color: var(--color-warning);
}
.src {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary);
}
.issues ul {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 13px;
}
.issues li.error {
  color: var(--color-danger);
}
.issues li.warn {
  color: var(--color-warning);
}
.ok {
  font-size: 13px;
  color: var(--color-primary);
}
.previews {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
}
.pv {
  min-width: 0;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  padding: var(--space-5);
  box-shadow: var(--shadow-card);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
}
.pv.wide {
  grid-column: auto;
}
.pv h3 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 800;
}
.hint {
  margin: -4px 0 12px;
  color: var(--color-muted);
  font-size: 13px;
  line-height: 1.6;
}
.ech {
  width: 100%;
  min-width: 0;
  height: clamp(340px, 46vh, 520px);
}
.mmd {
  min-height: 180px;
  padding: 12px;
  background: var(--color-bg);
  border-radius: var(--radius-control);
  overflow: auto;
}
.mmd :deep(svg) {
  max-width: 100%;
  height: auto;
}
.mmd-err {
  color: var(--color-danger);
  white-space: pre-wrap;
  font-size: 12px;
}
.cj {
  overflow-x: auto;
  min-height: 320px;
}
.cj canvas {
  width: 100% !important;
  max-height: 420px;
}
details summary {
  cursor: pointer;
  font-weight: 700;
  font-size: 12px;
  margin: 10px 0 6px;
  color: var(--color-muted);
}
.pre {
  background: #1f1720;
  color: #f8eef1;
  padding: 12px;
  border-radius: var(--radius-control);
  font-size: 11px;
  overflow: auto;
  max-height: 260px;
}
.pre.sm {
  max-height: 140px;
}
.hint {
  font-size: 13px;
  color: var(--color-muted);
  line-height: 1.5;
  margin: 0;
}
@media (max-width: 880px) {
  .previews {
    grid-template-columns: 1fr;
  }
}
</style>
