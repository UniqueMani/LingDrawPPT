<script setup lang="ts">
import { ref } from "vue";
import { store } from "../store";
import { vizLabIntent } from "../api/client";
import SlideInputForm from "./SlideInputForm.vue";
import type { SlideRequest } from "../types";

const slide = defineModel<SlideRequest>("slide", { required: true });

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
  <div class="panel-root">
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
      需要生成可执行图表代码？返回预览后进入<strong>「图表代码」</strong>。需要文生图 Prompt？进入<strong>「文生图配图」</strong>。
    </p>
  </div>
</template>

<style scoped>
.panel-root {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 22px 24px;
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
  max-height: 320px;
}
.hint {
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
  margin: 0;
}
</style>
