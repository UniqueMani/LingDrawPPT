<script setup lang="ts">
import { Chart, registerables } from "chart.js";
import * as echarts from "echarts";
import mermaid from "mermaid";
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import { store } from "../store";
import { vizLabChartCode } from "../api/client";
import SlideInputForm from "../components/SlideInputForm.vue";
import type { SlideRequest, VizLabChartCodeResponse } from "../types";

Chart.register(...registerables);
mermaid.initialize({ startOnLoad: false, securityLevel: "loose", theme: "neutral" });

const slide = ref<SlideRequest>({
  topic: "",
  body: "",
  data_description: "",
  slide_type: "content",
  mode: "auto",
});

const tgtEcharts = ref(true);
const tgtChartjs = ref(true);
const tgtMermaid = ref(true);
const instructions = ref(
  "三套表示数据一致；柱状/折线需坐标轴；饼图切片名不重复；Mermaid 使用合法 pie / xychart-beta / flowchart 语法。"
);

const loading = ref(false);
const err = ref("");
const result = ref<VizLabChartCodeResponse | null>(null);

const chartJsCanvas = ref<HTMLCanvasElement | null>(null);
const mermaidHost = ref<HTMLDivElement | null>(null);
const echartsEl = ref<HTMLDivElement | null>(null);
let chartJsInstance: Chart | null = null;
let echartsInstance: echarts.ECharts | null = null;

function destroyChartJs() {
  if (chartJsInstance) {
    chartJsInstance.destroy();
    chartJsInstance = null;
  }
}

function destroyEcharts() {
  if (echartsInstance) {
    echartsInstance.dispose();
    echartsInstance = null;
  }
}

async function renderMermaid(code: string) {
  const el = mermaidHost.value;
  if (!el) return;
  el.innerHTML = "";
  if (!code?.trim()) {
    el.textContent = "（无 Mermaid）";
    return;
  }
  try {
    const id = `mmd-${Date.now().toString(36)}`;
    const { svg } = await mermaid.render(id, code);
    el.innerHTML = svg;
  } catch (e: any) {
    el.textContent = e?.message || String(e);
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
  () => result.value?.chartJsConfig,
  async (cfg) => {
    await nextTick();
    if (cfg) renderChartJs(cfg);
  }
);
watch(
  () => result.value?.mermaidSource,
  async (code) => {
    await nextTick();
    if (code) await renderMermaid(code);
  }
);
watch(
  () => result.value?.echartsOption,
  async (opt) => {
    await nextTick();
    if (opt) renderEcharts(opt);
  }
);

onBeforeUnmount(() => {
  destroyChartJs();
  destroyEcharts();
});
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>图表代码自动生成</h1>
      <p class="lead">
        利用 LLM（若已配置 API Key）或规则降级，直接产出<strong>ECharts option</strong>、<strong>Chart.js 配置</strong>与
        <strong>Mermaid 源码</strong>；后端附带<strong>自动校验</strong>（series、坐标轴、结构等）。本页<strong>不做文生图</strong>。
      </p>
    </header>

    <div class="panel">
      <h2>输入与 Prompt 约束</h2>
      <SlideInputForm v-model="slide" />
      <div class="targets">
        <span class="tl">输出形态</span>
        <label><input v-model="tgtEcharts" type="checkbox" /> ECharts JSON</label>
        <label><input v-model="tgtChartjs" type="checkbox" /> Chart.js JSON</label>
        <label><input v-model="tgtMermaid" type="checkbox" /> Mermaid</label>
      </div>
      <div class="f">
        <label class="tl">附加约束（写入 LLM）</label>
        <textarea v-model="instructions" class="ta" rows="3" />
      </div>
      <button class="btn" type="button" :disabled="loading || !slide.topic.trim()" @click="run">
        {{ loading ? "生成中…" : "生成可渲染代码" }}
      </button>
      <p v-if="err" class="err">{{ err }}</p>
    </div>

    <div v-if="result" class="panel">
      <span class="src">来源：{{ result.source }}</span>
      <div v-if="result.validationIssues?.length" class="issues">
        <h3>自动校验</h3>
        <ul>
          <li v-for="(it, i) in result.validationIssues" :key="i" :class="it.severity">
            <b>{{ it.target }}</b> — {{ it.message }}
          </li>
        </ul>
      </div>
      <p v-else class="ok">未报告 error 级问题（仍需人工核对语义）。</p>
      <details v-if="result.rawLlmExcerpt">
        <summary>LLM 原文摘录</summary>
        <pre class="pre sm">{{ result.rawLlmExcerpt }}</pre>
      </details>
    </div>

    <div v-if="result" class="previews">
      <div v-if="result.echartsOption && tgtEcharts" class="pv">
        <h3>ECharts 预览</h3>
        <div ref="echartsEl" class="ech" />
        <details><summary>JSON</summary><pre class="pre">{{ JSON.stringify(result.echartsOption, null, 2) }}</pre></details>
      </div>
      <div v-if="result.chartJsConfig && tgtChartjs" class="pv">
        <h3>Chart.js 预览</h3>
        <div class="cj"><canvas ref="chartJsCanvas" width="420" height="260" /></div>
        <details><summary>JSON</summary><pre class="pre">{{ JSON.stringify(result.chartJsConfig, null, 2) }}</pre></details>
      </div>
      <div v-if="result.mermaidSource && tgtMermaid" class="pv wide">
        <h3>Mermaid 预览</h3>
        <div ref="mermaidHost" class="mmd" />
        <details><summary>源码</summary><pre class="pre">{{ result.mermaidSource }}</pre></details>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 28px 24px 48px;
}
.hero {
  margin-bottom: 24px;
}
.tag {
  display: inline-block;
  margin: 0 0 10px;
  font-size: 11px;
  font-weight: 800;
  color: #1d4ed8;
  background: #dbeafe;
  padding: 4px 10px;
  border-radius: 6px;
}
.hero h1 {
  margin: 0 0 12px;
  font-size: 28px;
  font-weight: 800;
  color: #0f172a;
}
.lead {
  margin: 0;
  font-size: 15px;
  line-height: 1.65;
  color: #475569;
}
.panel {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 22px 24px;
  margin-bottom: 18px;
}
.panel h2,
.panel h3 {
  margin: 0 0 14px;
  font-size: 16px;
  font-weight: 800;
  color: #1e293b;
}
.targets {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px 20px;
  margin: 16px 0;
  font-size: 14px;
}
.tl {
  font-weight: 800;
  color: #475569;
  margin-right: 4px;
}
.f {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ta {
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
  font-family: inherit;
}
.btn {
  margin-top: 14px;
  padding: 12px 24px;
  border: none;
  border-radius: 10px;
  background: #2563eb;
  color: #fff;
  font-weight: 800;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.err {
  color: #b91c1c;
  margin-top: 10px;
}
.src {
  font-size: 12px;
  font-weight: 700;
  color: #4338ca;
}
.issues ul {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 13px;
}
.issues li.error {
  color: #b91c1c;
}
.issues li.warn {
  color: #a16207;
}
.ok {
  font-size: 13px;
  color: #15803d;
}
.previews {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.pv {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 18px;
}
.pv.wide {
  grid-column: 1 / -1;
}
.pv h3 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 800;
}
.ech {
  width: 100%;
  height: 300px;
}
.mmd {
  min-height: 180px;
  padding: 12px;
  background: #fafafa;
  border-radius: 10px;
  overflow: auto;
}
.mmd :deep(svg) {
  max-width: 100%;
  height: auto;
}
.mmd-err {
  color: #b91c1c;
  white-space: pre-wrap;
  font-size: 12px;
}
.cj {
  overflow-x: auto;
}
details summary {
  cursor: pointer;
  font-weight: 700;
  font-size: 12px;
  margin: 10px 0 6px;
  color: #475569;
}
.pre {
  background: #0f172a;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 10px;
  font-size: 11px;
  overflow: auto;
  max-height: 260px;
}
.pre.sm {
  max-height: 140px;
}
@media (max-width: 880px) {
  .previews {
    grid-template-columns: 1fr;
  }
}
</style>
