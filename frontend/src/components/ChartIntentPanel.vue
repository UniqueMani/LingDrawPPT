<script setup lang="ts">
import { computed, ref } from "vue";
import { store } from "../store";
import { vizLabIntent } from "../api/client";
import SlideInputForm from "./SlideInputForm.vue";
import type { SlideRequest } from "../types";

const slide = defineModel<SlideRequest>("slide", { required: true });
const props = defineProps<{
  initialSemantic?: Record<string, any> | null;
  initialReason?: string | null;
  initialChartType?: string | null;
  hideSlideInput?: boolean;
  externalLoading?: boolean;
}>();
const emit = defineEmits<{
  result: [semantic: Record<string, any>];
  loadingChange: [loading: boolean];
}>();

const loading = ref(false);
const isBusy = computed(() => loading.value || props.externalLoading);
const err = ref("");
const semantic = ref<Record<string, any> | null>(null);
const displaySemantic = computed(() => semantic.value || props.initialSemantic || null);
const displayReason = computed(() => displaySemantic.value?.reason || props.initialReason || "");
const displayChartType = computed(() => displaySemantic.value?.chartType || props.initialChartType || "");
const confidenceBreakdown = computed(() => displaySemantic.value?.confidenceBreakdown || null);
const coreSummary = computed(() => {
  const item = displaySemantic.value;
  if (!item) return [];
  return [
    item.intent ? { label: "意图", value: labelOf(intentLabels, item.intent) } : null,
    displayChartType.value ? { label: "图表类型", value: labelOf(chartTypeLabels, displayChartType.value) } : null,
    item.confidence != null ? { label: "置信度", value: formatPercent(item.confidence) } : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>;
});

const runDetailItems = computed(() => {
  const item = displaySemantic.value;
  if (!item) return [];
  return [
    item.source ? { label: "来源", value: labelOf(sourceLabels, item.source) } : null,
    item.runtimeMode ? { label: "运行模式", value: labelOf(sourceLabels, item.runtimeMode) } : null,
    item.llmAttempted != null ? { label: "大模型状态", value: llmStatusLabel(item) } : null,
    item.intentConfidence != null ? { label: "意图判断", value: formatPercent(item.intentConfidence) } : null,
    item.dataExtractionConfidence != null ? { label: "数据抽取", value: formatPercent(item.dataExtractionConfidence) } : null,
    item.chartSuitabilityConfidence != null ? { label: "图表适配", value: formatPercent(item.chartSuitabilityConfidence) } : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>;
});

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
  "deepseek+validated": "DeepSeek 模型（已校验）",
  llm: "大模型生成",
  "llm+fallback": "大模型生成 + 本地规则补全",
  fallback: "本地规则补全",
  mock: "演示规则",
};

function labelOf(map: Record<string, string>, value: unknown) {
  const key = String(value || "");
  return map[key] || key || "未知";
}

function formatPercent(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(0)}%` : "-";
}

function llmStatusLabel(item: Record<string, any>) {
  if (!item.llmAttempted) return "未调用大模型";
  return item.llmSucceeded ? "调用成功" : "调用失败，已降级";
}

async function run() {
  if (isBusy.value) return;
  loading.value = true;
  emit("loadingChange", true);
  err.value = "";
  semantic.value = null;
  try {
    const r = await vizLabIntent(store.baseUrl, slide.value);
    semantic.value = r.semantic;
    emit("result", r.semantic);
  } catch (e: any) {
    err.value = e?.message || String(e);
  } finally {
    loading.value = false;
    emit("loadingChange", false);
  }
}
</script>

<template>
  <div class="panel-root">
    <div class="panel">
      <h2 v-if="!hideSlideInput">输入一页内容</h2>
      <SlideInputForm v-model="slide" :variant="hideSlideInput ? 'meta' : 'full'" />
      <button
        class="btn primary"
        type="button"
        :disabled="isBusy || !(slide.topic?.trim() || slide.body?.trim())"
        @click="run"
      >
        {{ isBusy ? "分析中..." : "运行意图分析" }}
      </button>
      <p v-if="err" class="err">{{ err }}</p>
    </div>

    <div v-if="displaySemantic" class="panel result">
      <h2>解析结果</h2>
      <div class="summary-grid">
        <article v-for="item in coreSummary" :key="item.label" class="summary-item">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </div>
      <p v-if="displayReason" class="reason">{{ displayReason }}</p>
      <details v-if="runDetailItems.length" class="run-details">
        <summary>运行详情</summary>
        <div class="detail-grid">
          <span v-for="item in runDetailItems" :key="item.label">{{ item.label }}：{{ item.value }}</span>
        </div>
      </details>
      <details v-if="confidenceBreakdown" class="breakdown">
        <summary>置信度解释</summary>
        <pre class="pre">{{ JSON.stringify(confidenceBreakdown, null, 2) }}</pre>
      </details>
      <details>
        <summary>semantic JSON（含 scores 可导出做实验）</summary>
        <pre class="pre">{{ JSON.stringify(displaySemantic, null, 2) }}</pre>
      </details>
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
.panel h2 {
  margin: 0 0 var(--space-5);
  font-size: 16px;
  font-weight: 800;
  color: var(--color-text);
}
.btn {
  min-height: var(--control-lg);
  margin-top: var(--space-5);
  padding: 0 24px;
  border: none;
  border-radius: var(--radius-control);
  font-weight: 800;
  cursor: pointer;
  font-size: 14px;
  transition: background var(--motion-base), transform var(--motion-base), box-shadow var(--motion-base);
}
.btn.primary {
  background: var(--color-primary);
  color: #fff;
}
.btn.primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-card);
}
.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.err {
  margin-top: var(--space-3);
  color: var(--color-danger);
  font-size: 14px;
  background: var(--color-danger-soft);
  border: 1px solid #fee2e2;
  border-radius: var(--radius-control);
  padding: var(--space-3);
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.summary-item {
  min-width: 0;
  background: rgba(255, 250, 251, 0.78);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  padding: 10px 12px;
}
.summary-item span {
  display: block;
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 4px;
}
.summary-item strong {
  display: block;
  color: var(--color-primary);
  font-size: 14px;
  font-weight: 800;
  line-height: 1.35;
}
.note {
  margin: 0 0 10px;
  padding: 10px 12px;
  border-left: 4px solid var(--color-primary);
  border-radius: var(--radius-control);
  background: var(--color-bg-muted);
  color: var(--color-muted);
  line-height: 1.7;
  font-size: 13px;
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
.run-details {
  margin-top: 8px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 8px;
  margin-top: 8px;
}
.detail-grid span {
  min-width: 0;
  padding: 8px 10px;
  border-radius: var(--radius-control);
  background: var(--color-bg-muted);
  color: var(--color-muted);
  font-size: 12px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
details {
  margin-top: 10px;
}
details summary {
  cursor: pointer;
  font-weight: 700;
  font-size: 13px;
  color: var(--color-muted);
  margin-bottom: 8px;
}
.pre {
  background: #1f1720;
  color: #f8eef1;
  padding: 14px;
  border-radius: var(--radius-control);
  font-size: 12px;
  overflow: auto;
  max-height: 320px;
}
</style>
