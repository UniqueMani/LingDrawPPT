<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
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
const viewportWidth = ref(typeof window !== "undefined" ? window.innerWidth : 1280);
const handleResize = () => {
  viewportWidth.value = window.innerWidth;
};
const chartWidth = computed(() => {
  if (viewportWidth.value < 680) return Math.max(260, viewportWidth.value - 120);
  if (viewportWidth.value < 1100) return Math.max(420, viewportWidth.value - 220);
  return 920;
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

onMounted(() => {
  window.addEventListener("resize", handleResize);
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
});
</script>

<template>
  <div class="result">
    <div class="row">
      <div class="card left">
        <div class="cardTitle">语义识别</div>
        <div v-if="slide.statusAnalyze === 'loading'" class="muted">图表生成中…</div>
        <div v-if="slide.statusAnalyze === 'error'" class="error">{{ slide.errorAnalyze }}</div>

        <div v-if="slide.statusAnalyze === 'success'">
          <div class="pills">
            <span class="pill">intent: {{ slide.analyze?.chart?.intent }}</span>
            <span class="pill">chart: {{ slide.analyze?.chart?.chartType }}</span>
          </div>
          <div class="reason">{{ slide.analyze?.chart?.reason }}</div>
          <details class="details">
            <summary>查看 extracted</summary>
            <pre class="pre">{{ JSON.stringify(slide.analyze?.chart?.extracted || {}, null, 2) }}</pre>
          </details>
        </div>
        <div v-else class="muted">尚未生成图表。</div>
      </div>

      <div class="card right">
        <div class="cardTitle">图表预览</div>
        <div v-if="slide.statusAnalyze === 'loading'" class="muted">加载中…</div>
        <div v-else class="chartWrap">
          <ChartPreview
            :option="slide.analyze?.chart?.echartsOption"
            :width="chartWidth"
            :height="420"
          />
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
      <div v-if="slide.statusIllustration === 'loading'" class="muted">插图策略生成中…</div>
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
  gap: 14px;
}
.row {
  display: flex;
  gap: 14px;
  align-items: stretch;
  flex-wrap: wrap;
}
.card {
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 14px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
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
}
.cardTitle { font-weight: 800; margin-bottom: 16px; color: #0f172a; display: flex; align-items: center; gap: 8px; font-size: 15px; }

.loading-state { padding: 20px 0; }
.skeleton-text { height: 12px; background: #f1f5f9; border-radius: 4px; margin-bottom: 10px; animation: pulse 1.5s infinite; }
.skeleton-text.short { width: 60%; }
@keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }

.intent-badges { display: flex; gap: 12px; margin-bottom: 16px; }
.intent-badge { background: #f0fdf4; border: 1px solid #dcfce7; padding: 8px 12px; border-radius: 8px; display: flex; flex-direction: column; }
.intent-badge.chart { background: #eff6ff; border-color: #dbeafe; }
.intent-badge .label { font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 700; }
.intent-badge .val { font-size: 14px; font-weight: 800; color: #1f9d60; }
.intent-badge.chart .val { color: #2563eb; }

.reason-box { background: #f8fafc; border-radius: 8px; padding: 12px; font-size: 13px; line-height: 1.5; color: #334155; border-left: 4px solid #1f9d60; margin-bottom: 16px; }

.extracted-section { margin-top: 16px; }
.section-subtitle { font-size: 12px; font-weight: 700; color: #64748b; margin-bottom: 8px; }
.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th { text-align: left; background: #f8fafc; padding: 8px; border-bottom: 1px solid #e2e8f0; color: #64748b; }
.data-table td { padding: 8px; border-bottom: 1px solid #f1f5f9; color: #0f172a; }
.data-table td.empty { text-align: center; color: #94a3b8; padding: 20px; }

.action-footer { display: flex; gap: 10px; margin-top: 20px; padding-top: 16px; border-top: 1px solid #f1f5f9; }
.btn-sm { padding: 6px 12px; border-radius: 6px; border: none; font-size: 12px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
.btn-sm.primary { background: #1f9d60; color: white; }
.btn-sm.secondary { background: #f1f5f9; color: #475569; }
.btn-sm:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }

.loading-chart { height: 300px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: #64748b; font-size: 13px; }
.spinner { width: 30px; height: 30px; border: 3px solid #f1f5f9; border-top-color: #1f9d60; border-radius: 50%; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.error-box { background: #fef2f2; border: 1px solid #fee2e2; color: #b91c1c; padding: 12px; border-radius: 8px; font-size: 13px; display: flex; align-items: center; gap: 8px; }
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
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  padding: 10px;
  outline: none;
}
</style>

