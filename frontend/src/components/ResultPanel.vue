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
.cardTitle {
  font-weight: 700;
  margin-bottom: 10px;
  color: #111827;
}
.muted {
  color: #6b7280;
  font-size: 13px;
}
.error {
  color: #b91c1c;
  font-size: 13px;
  white-space: pre-wrap;
}
.pills {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.pill {
  display: inline-block;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 999px;
  background: #eaf9f0;
  color: #0f5132;
}
.pill.muted {
  background: #f9fafb;
  color: #6b7280;
}
.reason {
  font-size: 13px;
  color: #111827;
  white-space: pre-wrap;
}
.details {
  margin-top: 10px;
}
.pre {
  white-space: pre-wrap;
  margin: 0;
  font-size: 12px;
  color: #111827;
}
.btnRow {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.chartWrap {
  width: 100%;
  overflow-x: auto;
}
.btn {
  border: 1px solid #1f9d60;
  background: #1f9d60;
  color: #fff;
  border-radius: 10px;
  padding: 8px 10px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 16px rgba(79, 70, 229, 0.25);
}
.btn.secondary {
  background: #fff;
  color: #0f5132;
  border-color: #96d5b2;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
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

