<script setup lang="ts">
import { ref } from "vue";
import { store } from "../store";
import { vizLabIntent } from "../api/client";
import SlideInputForm from "../components/SlideInputForm.vue";
import type { SlideRequest } from "../types";

const slide = ref<SlideRequest>({
  topic: "",
  body: "",
  data_description: "",
  slide_type: "content",
  mode: "auto",
});

const loading = ref(false);
const err = ref("");
const semantic = ref<Record<string, any> | null>(null);

async function run() {
  loading.value = true;
  err.value = "";
  semantic.value = null;
  try {
    const r = await vizLabIntent(store.baseUrl, slide.value);
    semantic.value = r.semantic;
  } catch (e: any) {
    err.value = e?.message || String(e);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>图表意图与图型选择</h1>
      <p class="lead">
        从自然语言或结构化数据中识别<strong>比较 / 占比 / 趋势 / 关系 / 表格</strong>等意图，并映射到推荐图型（柱状、饼图、折线、桑基、表格等）。本页<strong>不生成文生图</strong>、不输出完整
        ECharts 配置，只做语义解析，便于单独统计识别准确率。
      </p>
    </header>

    <div class="panel">
      <h2>输入一页内容</h2>
      <SlideInputForm v-model="slide" />
      <button class="btn primary" type="button" :disabled="loading || !slide.topic.trim()" @click="run">
        {{ loading ? "分析中…" : "运行意图分析" }}
      </button>
      <p v-if="err" class="err">{{ err }}</p>
    </div>

    <div v-if="semantic" class="panel result">
      <h2>解析结果</h2>
      <div class="pills">
        <span v-if="semantic.intent" class="pill">intent: {{ semantic.intent }}</span>
        <span v-if="semantic.chartType" class="pill">chartType: {{ semantic.chartType }}</span>
        <span v-if="semantic.confidence != null" class="pill"
          >confidence: {{ (Number(semantic.confidence) * 100).toFixed(0) }}%</span
        >
      </div>
      <p v-if="semantic.reason" class="reason">{{ semantic.reason }}</p>
      <details open>
        <summary>semantic JSON（含 scores 可导出做实验）</summary>
        <pre class="pre">{{ JSON.stringify(semantic, null, 2) }}</pre>
      </details>
    </div>

    <p class="hint">
      需要生成可执行图表代码？请前往顶部导航<strong>「图表代码生成」</strong>。需要文生图 Prompt？请前往<strong>「文生图配图」</strong>。
    </p>
  </div>
</template>

<style scoped>
.page {
  max-width: 920px;
  margin: 0 auto;
  padding: 28px 24px 48px;
}
.hero {
  margin-bottom: 28px;
}
.tag {
  display: inline-block;
  margin: 0 0 10px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #0369a1;
  background: #e0f2fe;
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
  margin-bottom: 20px;
  box-shadow: 0 4px 18px rgba(15, 23, 42, 0.04);
}
.panel h2 {
  margin: 0 0 18px;
  font-size: 16px;
  font-weight: 800;
  color: #1e293b;
}
.btn {
  margin-top: 18px;
  padding: 12px 24px;
  border: none;
  border-radius: 10px;
  font-weight: 800;
  cursor: pointer;
  font-size: 14px;
}
.btn.primary {
  background: #0ea5e9;
  color: #fff;
}
.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.err {
  margin-top: 12px;
  color: #b91c1c;
  font-size: 14px;
}
.pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.pill {
  background: #eff6ff;
  color: #1d4ed8;
  padding: 6px 11px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
}
.reason {
  font-size: 14px;
  color: #334155;
  line-height: 1.55;
  margin: 0 0 12px;
}
details summary {
  cursor: pointer;
  font-weight: 700;
  font-size: 13px;
  color: #475569;
  margin-bottom: 8px;
}
.pre {
  background: #0f172a;
  color: #e2e8f0;
  padding: 14px;
  border-radius: 10px;
  font-size: 12px;
  overflow: auto;
  max-height: 400px;
}
.hint {
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
  margin: 0;
}
</style>
