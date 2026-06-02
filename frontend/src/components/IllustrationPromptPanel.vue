<script setup lang="ts">
import { computed, ref } from "vue";
import { store } from "../store";
import { vizLabIllustration } from "../api/client";
import SlideInputForm from "./SlideInputForm.vue";
import type { SlideRequest, VizLabIllustrationResponse } from "../types";

type DisplayIllustrationResult = {
  needIllus: boolean;
  keywords: string[];
  prompt: string;
  reason: string;
  experiment?: Record<string, any> | null;
};

const slide = defineModel<SlideRequest>("slide", { required: true });
const props = defineProps<{
  initialResult?: DisplayIllustrationResult | null;
}>();
const emit = defineEmits<{
  result: [result: VizLabIllustrationResponse];
}>();

const imageModel = ref<"flux" | "sd" | "other">("flux");
const styleRefUrl = ref("");
const loraHint = ref("");
const extraStyleWords = ref("");

const loading = ref(false);
const err = ref("");
const result = ref<VizLabIllustrationResponse | null>(null);
const displayResult = computed<DisplayIllustrationResult | null>(() => result.value || props.initialResult || null);

async function run() {
  loading.value = true;
  err.value = "";
  result.value = null;
  try {
    result.value = await vizLabIllustration(store.baseUrl, {
      slide: slide.value,
      image_model: imageModel.value,
      style_ref_url: styleRefUrl.value.trim() || null,
      lora_hint: loraHint.value.trim() || null,
      extra_style_words: extraStyleWords.value.trim() || null,
    });
    emit("result", result.value);
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
      <h2>页面内容</h2>
      <SlideInputForm v-model="slide" />
    </div>

    <div class="panel">
      <h2>文生图实验参数</h2>
      <div class="row2">
        <div class="f">
          <label>目标模型族</label>
          <select v-model="imageModel" class="sel">
            <option value="flux">FLUX / 同类</option>
            <option value="sd">Stable Diffusion</option>
            <option value="other">其他</option>
          </select>
        </div>
        <div class="f grow">
          <label>风格参考图 URL（待接 IP-Adapter）</label>
          <input v-model="styleRefUrl" type="url" class="inp" placeholder="https://..." />
        </div>
      </div>
      <div class="f">
        <label>LoRA / 风格触发</label>
        <input v-model="loraHint" class="inp" placeholder="如：扁平矢量、科技蓝" />
      </div>
      <div class="f">
        <label>追加风格词（写入 Prompt）</label>
        <textarea v-model="extraStyleWords" class="ta" rows="2" />
      </div>
      <button class="btn" type="button" :disabled="loading || !slide.topic.trim()" @click="run">
        {{ loading ? "生成中…" : "生成配图 Prompt" }}
      </button>
      <p v-if="err" class="err">{{ err }}</p>
    </div>

    <div v-if="displayResult" class="panel out">
      <div class="pill">{{ displayResult.needIllus ? "建议配图" : "不强依赖配图" }}</div>
      <h3>关键词</h3>
      <div class="tags">
        <span v-for="k in displayResult.keywords" :key="k" class="tag">{{ k }}</span>
      </div>
      <h3>文生图 Prompt</h3>
      <div class="prompt">{{ displayResult.prompt }}</div>
      <p class="reason">{{ displayResult.reason }}</p>
      <details v-if="displayResult.experiment" open>
        <summary>experiment 元数据</summary>
        <pre class="pre">{{ JSON.stringify(displayResult.experiment, null, 2) }}</pre>
      </details>
      <div class="ph">
        <p>待接入出图服务后展示最终图片。</p>
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
.panel h2 {
  margin: 0 0 var(--space-4);
  font-size: 16px;
  font-weight: 800;
}
.panel h3 {
  margin: 18px 0 10px;
  font-size: 13px;
  font-weight: 800;
  color: var(--color-muted);
}
.row2 {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-bottom: var(--space-4);
}
.f {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 180px;
}
.f.grow {
  flex: 1;
  min-width: 220px;
}
label {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-muted);
}
.inp,
.sel,
.ta {
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  min-height: var(--control-lg);
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
}
.inp:focus,
.sel:focus,
.ta:focus {
  border-color: var(--color-primary);
  outline: none;
  box-shadow: var(--shadow-focus);
}
.sel {
  cursor: pointer;
  font-weight: 600;
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
.pill {
  display: inline-block;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-border);
  padding: 6px 12px;
  border-radius: var(--radius-control);
  font-size: 12px;
  font-weight: 800;
  margin-bottom: 8px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tag {
  background: var(--color-bg-muted);
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  border-radius: var(--radius-control);
  font-size: 12px;
  font-weight: 600;
}
.prompt {
  background: var(--color-surface);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-card);
  padding: var(--space-4);
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-soft);
  white-space: pre-wrap;
}
.reason {
  font-size: 13px;
  color: var(--color-muted);
  margin-top: 10px;
}
details summary {
  cursor: pointer;
  font-weight: 700;
  margin-top: 16px;
  font-size: 13px;
}
.pre {
  background: #1f1720;
  color: #f8eef1;
  padding: 12px;
  border-radius: var(--radius-control);
  font-size: 12px;
  overflow: auto;
  max-height: 200px;
}
.ph {
  margin-top: 20px;
  padding: var(--space-5);
  border: 2px dashed var(--color-primary-border);
  border-radius: var(--radius-card);
  text-align: center;
  color: var(--color-muted);
  font-size: 13px;
}
.ico {
  font-size: 26px;
  display: block;
  margin-bottom: 8px;
}
.foot {
  font-size: 13px;
  color: var(--color-muted);
  line-height: 1.5;
  margin: 0;
}
</style>
