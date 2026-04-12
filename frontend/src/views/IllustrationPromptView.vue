<script setup lang="ts">
import { ref } from "vue";
import { store } from "../store";
import { vizLabIllustration } from "../api/client";
import SlideInputForm from "../components/SlideInputForm.vue";
import type { SlideRequest, VizLabIllustrationResponse } from "../types";

const slide = ref<SlideRequest>({
  topic: "",
  body: "",
  data_description: "",
  slide_type: "content",
  mode: "auto",
});

const imageModel = ref<"flux" | "sd" | "other">("flux");
const styleRefUrl = ref("");
const loraHint = ref("");
const extraStyleWords = ref("");

const loading = ref(false);
const err = ref("");
const result = ref<VizLabIllustrationResponse | null>(null);

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
      <h1>语义配图与文生图 Prompt</h1>
      <p class="lead">
        根据页面主题与正文摘要生成<strong>关键词</strong>与<strong>文生图 Prompt</strong>，并记录目标模型（FLUX / SD）、风格参考图
        URL、LoRA 提示等实验字段，便于你对接真实出图 API、IP-Adapter 与风格一致性实验。本页<strong>不生成数据图表</strong>。
      </p>
    </header>

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

    <div v-if="result" class="panel out">
      <div class="pill">{{ result.needIllus ? "建议配图" : "不强依赖配图" }}</div>
      <h3>关键词</h3>
      <div class="tags">
        <span v-for="k in result.keywords" :key="k" class="tag">{{ k }}</span>
      </div>
      <h3>文生图 Prompt</h3>
      <div class="prompt">{{ result.prompt }}</div>
      <p class="reason">{{ result.reason }}</p>
      <details open>
        <summary>experiment 元数据</summary>
        <pre class="pre">{{ JSON.stringify(result.experiment, null, 2) }}</pre>
      </details>
      <div class="ph">
        <span class="ico">🖼️</span>
        <p>真实出图结果可在此占位展示：接入你的 FLUX/SD HTTP 接口后返回图片 URL 或 base64。</p>
      </div>
    </div>

    <p class="foot">
      若需先做数据图表，请使用顶部<strong>「图表意图」</strong>或<strong>「图表代码」</strong>；流水线整合可在<strong>工作台</strong>分按钮执行。
    </p>
  </div>
</template>

<style scoped>
.page {
  max-width: 880px;
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
  color: #86198f;
  background: #fae8ff;
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
.panel h2 {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 800;
}
.panel h3 {
  margin: 18px 0 10px;
  font-size: 13px;
  font-weight: 800;
  color: #64748b;
}
.row2 {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 14px;
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
  color: #475569;
}
.inp,
.sel,
.ta {
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
}
.sel {
  cursor: pointer;
  font-weight: 600;
}
.btn {
  margin-top: 14px;
  padding: 12px 24px;
  border: none;
  border-radius: 10px;
  background: #7c3aed;
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
.pill {
  display: inline-block;
  background: #ede9fe;
  color: #5b21b6;
  padding: 6px 12px;
  border-radius: 8px;
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
  background: #f1f5f9;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}
.prompt {
  background: #faf5ff;
  border: 1px solid #e9d5ff;
  border-radius: 12px;
  padding: 14px;
  font-size: 14px;
  line-height: 1.6;
  color: #1e1b4b;
  white-space: pre-wrap;
}
.reason {
  font-size: 13px;
  color: #64748b;
  margin-top: 10px;
}
details summary {
  cursor: pointer;
  font-weight: 700;
  margin-top: 16px;
  font-size: 13px;
}
.pre {
  background: #0f172a;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 10px;
  font-size: 12px;
  overflow: auto;
  max-height: 200px;
}
.ph {
  margin-top: 20px;
  padding: 22px;
  border: 2px dashed #e2e8f0;
  border-radius: 12px;
  text-align: center;
  color: #64748b;
  font-size: 13px;
}
.ico {
  font-size: 26px;
  display: block;
  margin-bottom: 8px;
}
.foot {
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
  margin: 0;
}
</style>
