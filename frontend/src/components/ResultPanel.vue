<script setup lang="ts">
import { computed } from "vue";
import type { SlideState } from "../types";
import ChartPreview from "./ChartPreview.vue";

const props = defineProps<{
  slide: SlideState;
  onRerunChart: () => void;
  onRerunIllustration: () => void;
  onRerunBoth: () => void;
  onChangeIllustration: (next: { keywords: string[]; prompt: string }) => void;
}>();

const illus = computed(() => props.slide.illustration?.illustration);

const tablePreview = computed(() => {
  const chart = props.slide.analyze?.chart;
  if (!chart || chart.chartType !== "data_table") return null;
  const ex = chart.extracted || {};
  const columns = ex.columns;
  const rows = ex.rows;
  if (!Array.isArray(columns) || !Array.isArray(rows)) return null;
  return { columns: columns as string[], rows: rows as unknown[][] };
});

const keywordsText = computed({
  get() {
    return (illus.value?.keywords || []).join("\n");
  },
  set(v: string) {
    const nextKeywords = v
      .split(/\n+/g)
      .map((x) => x.trim())
      .filter(Boolean)
      .slice(0, 30);
    props.onChangeIllustration({
      keywords: nextKeywords,
      prompt: illus.value?.prompt || "",
    });
  },
});

const promptText = computed({
  get() {
    return illus.value?.prompt || "";
  },
  set(v: string) {
    props.onChangeIllustration({
      keywords: illus.value?.keywords || [],
      prompt: v,
    });
  },
});

function needIllusText() {
  if (!illus.value) return "";
  return illus.value.needIllus ? "需要插图" : "不强需插图";
}

</script>

<template>
  <div class="result">
    <div class="row">
      <div class="card left">
        <div class="cardTitle">语义识别</div>
        <div v-if="slide.statusAnalyze === 'loading'" class="loading-state">
          <div class="skeleton-text"></div>
          <div class="skeleton-text short"></div>
          <span>图表生成中…</span>
        </div>
        <div v-if="slide.statusAnalyze === 'error'" class="error">{{ slide.errorAnalyze }}</div>

        <div v-if="slide.statusAnalyze === 'success'">
          <div class="pills">
            <span class="pill">intent: {{ slide.analyze?.chart?.intent }}</span>
            <span class="pill">chart: {{ slide.analyze?.chart?.chartType }}</span>
          </div>
          <div class="reason">{{ slide.analyze?.chart?.reason }}</div>
          <div v-if="slide.analyze?.semantic && slide.analyze.semantic.confidence != null" class="conf">
            规则置信度（无 LLM 时）：{{ (slide.analyze.semantic.confidence * 100).toFixed(0) }}%
          </div>
          <details class="details">
            <summary>查看 extracted</summary>
            <pre class="pre">{{ JSON.stringify(slide.analyze?.chart?.extracted || {}, null, 2) }}</pre>
          </details>
        </div>
        <div v-else class="muted">尚未生成图表。</div>
      </div>

      <div class="card right">
        <div class="cardTitle">图表预览</div>
        <div v-if="slide.statusAnalyze === 'loading'" class="loading-chart">
          <div class="spinner"></div>
          <span>加载中…</span>
        </div>
        <div v-else class="chartWrap">
          <div v-if="tablePreview" class="tableWrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th v-for="(c, i) in tablePreview.columns" :key="i">{{ c }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in tablePreview.rows" :key="ri">
                  <td v-for="(cell, ci) in row" :key="ci">{{ cell ?? "—" }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <ChartPreview v-else :option="slide.analyze?.chart?.echartsOption" :height="420" />
        </div>

        <div class="btnRow">
          <button class="btn" @click="onRerunChart" :disabled="slide.statusAnalyze === 'loading'">
            重新生成图表
          </button>
          <button
            class="btn secondary"
            @click="onRerunIllustration"
            :disabled="slide.statusIllustration === 'loading'"
          >
            重新生成插图策略
          </button>
          <button class="btn" @click="onRerunBoth" :disabled="slide.statusAnalyze === 'loading' || slide.statusIllustration === 'loading'">
            一键重跑
          </button>
        </div>
      </div>
    </div>

    <div class="card illusCard">
      <div class="cardTitle">插图策略</div>
      <div v-if="slide.statusIllustration === 'loading'" class="loading-state">
        <div class="skeleton-text"></div>
        <div class="skeleton-text short"></div>
        <span>插图策略生成中…</span>
      </div>
      <div v-if="slide.statusIllustration === 'error'" class="error">{{ slide.errorIllustration }}</div>

      <div v-if="slide.statusIllustration === 'success' && illus">
        <div class="pills">
          <span class="pill">{{ needIllusText() }}</span>
          <span class="pill muted">keywords 数：{{ illus.keywords.length }}</span>
        </div>

        <div class="formRow">
          <label>keywords（每行一个）</label>
          <textarea v-model="keywordsText" class="ta"></textarea>
        </div>

        <div class="formRow">
          <label>prompt（给生成/检索用）</label>
          <textarea v-model="promptText" class="ta"></textarea>
        </div>

        <div class="reason" style="margin-top:8px">{{ illus.reason }}</div>
      </div>

      <div v-else class="muted">尚未生成插图策略。</div>
    </div>
  </div>
</template>

<style scoped>
.result {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.row {
  display: flex;
  gap: var(--space-4);
  align-items: stretch;
  flex-wrap: wrap;
}
.card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  padding: var(--space-4);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
  transition: transform var(--motion-base) var(--motion-ease), box-shadow var(--motion-base) var(--motion-ease), border-color var(--motion-base) var(--motion-ease);
}
.card:hover {
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-2px);
}
.left {
  flex: 1 1 320px;
}
.right {
  flex: 2 1 540px;
  min-width: 0;
}
.illusCard {
  flex: 1 1 100%;
  animation-delay: 80ms;
}
.cardTitle { font-weight: 800; margin-bottom: var(--space-4); color: var(--color-text); display: flex; align-items: center; gap: 8px; font-size: 15px; }
.muted {
  color: var(--color-muted);
  font-size: 13px;
}
.error {
  color: var(--color-danger);
  background: var(--color-danger-soft);
  border: 1px solid #fee2e2;
  border-radius: var(--radius-control);
  padding: var(--space-3);
  font-size: 13px;
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
  padding: 0 10px;
  border-radius: var(--radius-control);
  background: var(--color-primary-soft);
  border: 1px solid var(--color-primary-border);
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 700;
}
.pill.muted {
  background: var(--color-bg-muted);
  border-color: var(--color-border);
  color: var(--color-muted);
}
.reason {
  background: var(--color-primary-soft);
  border-left: 4px solid var(--color-primary);
  border-radius: var(--radius-control);
  padding: var(--space-3);
  font-size: 13px;
  line-height: 1.55;
  color: var(--color-text-soft);
}
.details summary {
  cursor: pointer;
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 700;
  margin-top: 12px;
}
.pre {
  background: #1f1720;
  color: #f8eef1;
  border-radius: var(--radius-control);
  padding: var(--space-3);
  font-size: 12px;
  overflow: auto;
}
.btnRow {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-4);
}
.btn {
  min-height: var(--control-md);
  padding: 0 12px;
  border-radius: var(--radius-control);
  border: 1px solid var(--color-primary);
  background: var(--color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background var(--motion-base), border-color var(--motion-base), color var(--motion-base), transform var(--motion-base), box-shadow var(--motion-base);
}
.btn.secondary {
  background: var(--color-surface);
  color: var(--color-primary);
}
.btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  color: #fff;
  transform: translateY(-1px);
  box-shadow: var(--shadow-card);
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state {
  padding: var(--space-4);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  color: var(--color-muted);
  font-size: 13px;
}
.skeleton-text {
  height: 12px;
  background: linear-gradient(90deg, var(--color-bg-muted), var(--color-primary-soft), var(--color-bg-muted));
  background-size: 240% 100%;
  border-radius: 4px;
  margin-bottom: 10px;
  animation: soft-pulse 1.2s linear infinite;
}
.skeleton-text.short { width: 60%; }
@keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }

.intent-badges { display: flex; gap: 12px; margin-bottom: 16px; }
.intent-badge { background: var(--color-primary-soft); border: 1px solid var(--color-border); padding: 8px 12px; border-radius: var(--radius-control); display: flex; flex-direction: column; }
.intent-badge.chart { background: var(--color-primary-soft); border-color: var(--color-primary-border); }
.intent-badge .label { font-size: 10px; text-transform: uppercase; color: var(--color-muted); font-weight: 700; }
.intent-badge .val { font-size: 14px; font-weight: 800; color: var(--color-primary); }
.intent-badge.chart .val { color: var(--color-primary); }

.reason-box { background: var(--color-primary-soft); border-radius: var(--radius-control); padding: 12px; font-size: 13px; line-height: 1.5; color: var(--color-text-soft); border-left: 4px solid var(--color-primary); margin-bottom: 16px; }
.conf { font-size: 12px; color: var(--color-muted); margin: 8px 0 0; }
.chartWrap {
  width: 100%;
  min-width: 0;
  overflow: hidden;
}
.tableWrap { overflow-x: auto; max-width: 100%; }
.chartWrap .data-table { margin-top: 0; }

.extracted-section { margin-top: 16px; }
.section-subtitle { font-size: 12px; font-weight: 700; color: var(--color-muted); margin-bottom: 8px; }
.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th { text-align: left; background: var(--color-bg-muted); padding: 8px; border-bottom: 1px solid var(--color-border); color: var(--color-muted); }
.data-table td { padding: 8px; border-bottom: 1px solid var(--color-border); color: var(--color-text); }
.data-table td.empty { text-align: center; color: #94a3b8; padding: 20px; }

.action-footer { display: flex; gap: 10px; margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--color-border); }
.btn-sm { min-height: var(--control-sm); padding: 0 12px; border-radius: var(--radius-control); border: none; font-size: 12px; font-weight: 700; cursor: pointer; transition: all var(--motion-base); }
.btn-sm.primary { background: var(--color-primary); color: white; }
.btn-sm.secondary { background: var(--color-bg-muted); color: var(--color-text-soft); }
.btn-sm:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }

.loading-chart { min-height: 300px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--color-muted); font-size: 13px; background: var(--color-bg); border: 1px solid var(--color-border); border-radius: var(--radius-card); }
.spinner { width: 30px; height: 30px; border: 3px solid var(--color-bg-muted); border-top-color: var(--color-primary); border-radius: 50%; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.error-box { background: var(--color-danger-soft); border: 1px solid #fee2e2; color: var(--color-danger); padding: 12px; border-radius: var(--radius-control); font-size: 13px; display: flex; align-items: center; gap: 8px; }
.formRow {
  margin-top: 10px;
}
.formRow label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}
.ta {
  width: 100%;
  min-height: 90px;
  resize: vertical;
  font-size: 13px;
  border-radius: var(--radius-control);
  border: 1px solid var(--color-primary-border);
  padding: var(--space-3);
  outline: none;
}
.ta:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}
</style>

