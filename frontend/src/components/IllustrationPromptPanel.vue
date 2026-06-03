<script setup lang="ts">
import { computed, ref } from "vue";
import { analyzeDocumentConsistency, fluxGenerateImage } from "../api/client";
import { store } from "../store";
import SlideInputForm from "./SlideInputForm.vue";
import type { AnalyzeDocumentResponse, FluxGenerateImageResponse, SlideRequest } from "../types";

const slide = defineModel<SlideRequest>("slide", { required: true });
const props = defineProps<{
  slidePage?: number;
  docConsistency?: AnalyzeDocumentResponse | null;
  previewUrl?: string;
  initialFluxImage?: FluxGenerateImageResponse | null;
}>();
const emit = defineEmits<{
  fluxResult: [result: FluxGenerateImageResponse];
  fluxError: [message: string];
  fluxLoading: [loading: boolean];
}>();

const extraStyleWords = ref("");
const wanModel = ref("wan2.6-t2i");
const aspectRatio = ref("16:9");
const promptExtend = ref(true);
const useDocStyle = ref(true);
const useEntitySync = ref(true);
const docAnalyzing = ref(false);

const fluxLoading = ref(false);
const fluxErr = ref("");
const fluxResult = ref<FluxGenerateImageResponse | null>(null);

const displayFluxImage = computed(() => fluxResult.value || props.initialFluxImage || null);
const selectedText = computed(() => slide.value.body?.trim() || "");
const canGenerateFlux = computed(() => Boolean(selectedText.value || slide.value.topic?.trim()));

const docProfile = computed(() => props.docConsistency || store.docConsistency || null);

const currentSlidePlan = computed(() => {
  const page = props.slidePage || 1;
  return docProfile.value?.slide_plans?.find((p) => p.page === page) || null;
});

const currentPageEntities = computed(() => {
  if (!docProfile.value?.entities?.length) return [];
  const plan = currentSlidePlan.value;
  if (!plan?.entity_ids?.length) return docProfile.value.entities.slice(0, 3);
  const ids = new Set(plan.entity_ids);
  return docProfile.value.entities.filter((e) => ids.has(e.id));
});

const aspectRatioOptions = [
  { value: "16:9", label: "16:9 宽屏" },
  { value: "4:3", label: "4:3 标准" },
  { value: "1:1", label: "1:1 方形" },
  { value: "9:16", label: "9:16 竖屏" },
  { value: "21:9", label: "21:9 超宽" },
];

function previewPathFromUrl(url?: string) {
  if (!url) return null;
  try {
    return new URL(url, window.location.origin).pathname;
  } catch {
    return url.startsWith("/") ? url : null;
  }
}

function scoreTone(score: number) {
  if (score >= 72) return "good";
  if (score >= 55) return "mid";
  return "low";
}

function openFluxImage(url: string) {
  if (url) window.open(url, "_blank", "noopener,noreferrer");
}

async function rerunDocAnalysis() {
  if (!store.slides.length) return;
  docAnalyzing.value = true;
  try {
    store.docConsistency = await analyzeDocumentConsistency(store.baseUrl, {
      doc_title: store.docName,
      pages: store.slides.map((s) => ({
        page: s.page,
        topic: s.input.topic,
        body: s.input.body || s.sourceText || "",
      })),
    });
    store.addLog(store.docConsistency.summary);
  } catch (e: any) {
    store.addLog(`文档分析失败: ${e?.message || e}`);
  } finally {
    docAnalyzing.value = false;
  }
}

async function runFluxGenerate() {
  if (!canGenerateFlux.value) {
    fluxErr.value = "请先在预览区框选文字并写入正文，或填写页面主题。";
    emit("fluxError", fluxErr.value);
    return;
  }

  fluxLoading.value = true;
  fluxErr.value = "";
  emit("fluxLoading", true);
  try {
    fluxResult.value = await fluxGenerateImage(store.baseUrl, {
      selected_text: selectedText.value,
      topic: slide.value.topic,
      slide_page: props.slidePage || 1,
      use_doc_style: useDocStyle.value,
      use_entity_sync: useEntitySync.value,
      doc_consistency: useDocStyle.value || useEntitySync.value ? docProfile.value : null,
      preview_path: previewPathFromUrl(props.previewUrl),
      aspect_ratio: aspectRatio.value,
      model: wanModel.value,
      prompt_extend: promptExtend.value,
      extra_style_words: extraStyleWords.value.trim() || null,
    });
    emit("fluxResult", fluxResult.value);
  } catch (e: any) {
    fluxErr.value = e?.message || String(e);
    emit("fluxError", fluxErr.value);
  } finally {
    fluxLoading.value = false;
    emit("fluxLoading", false);
  }
}
</script>

<template>
  <div class="panel-root">
    <div class="panel flux-panel">
      <h2>万相文生图</h2>

      <div v-if="selectedText" class="selected-preview">
        <span class="selected-label">将用于出图的文字</span>
        <div class="selected-text">{{ selectedText }}</div>
      </div>
      <p v-else class="warn">正文为空：请框选文字写入正文，或填写页面主题。</p>

      <SlideInputForm v-model="slide" variant="meta" />

      <div class="doc-consistency-panel">
        <div class="doc-consistency-head">
          <span class="doc-consistency-title">文档级一致性 / 多图协同</span>
          <button type="button" class="btn-link" :disabled="docAnalyzing" @click="rerunDocAnalysis">
            {{ docAnalyzing ? "分析中…" : "重新分析文档" }}
          </button>
        </div>
        <p v-if="!docProfile" class="doc-hint">
          上传文档后将自动抽取全篇风格与共享实体库。
        </p>
        <template v-else>
          <div class="style-tokens">
            <span v-for="t in docProfile.style.style_tokens" :key="t" class="token">{{ t }}</span>
          </div>
          <p class="doc-style-zh">{{ docProfile.style.style_prompt_zh }}</p>
          <p v-if="currentSlidePlan" class="slide-plan">
            本页角色：<b>{{ currentSlidePlan.slide_role }}</b> · {{ currentSlidePlan.visual_focus }}
          </p>
          <ul v-if="currentPageEntities.length" class="entity-list">
            <li v-for="ent in currentPageEntities" :key="ent.id">
              <b>{{ ent.name }}</b>
              <span class="ent-anchor">{{ ent.visual_anchor }}</span>
            </li>
          </ul>
        </template>
        <div class="row2 checks">
          <label class="check">
            <input v-model="useDocStyle" type="checkbox" />
            统一全文档风格（Style Tokens）
          </label>
          <label class="check">
            <input v-model="useEntitySync" type="checkbox" />
            多图协同（共享实体库）
          </label>
        </div>
      </div>

      <div class="row2">
        <div class="f">
          <label>万相模型</label>
          <select v-model="wanModel" class="sel">
            <option value="wan2.6-t2i">wan2.6-t2i（推荐）</option>
            <option value="wan2.5-t2i-preview">wan2.5-t2i-preview</option>
            <option value="wan2.2-t2i-flash">wan2.2-t2i-flash（极速）</option>
            <option value="wan2.2-t2i-plus">wan2.2-t2i-plus（专业）</option>
          </select>
        </div>
        <div class="f">
          <label>宽高比</label>
          <select v-model="aspectRatio" class="sel">
            <option v-for="opt in aspectRatioOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>
      </div>

      <div class="row2 checks">
        <label class="check">
          <input v-model="promptExtend" type="checkbox" />
          智能改写 Prompt
        </label>
      </div>

      <div class="f">
        <label>追加风格词</label>
        <textarea v-model="extraStyleWords" class="ta" rows="2" placeholder="如：扁平矢量、科技蓝、无文字" />
      </div>

      <button class="btn flux-btn" type="button" :disabled="fluxLoading || !canGenerateFlux" @click="runFluxGenerate">
        {{ fluxLoading ? "生成与质量评估中…" : "根据选中文字生成图片" }}
      </button>
      <p v-if="fluxErr" class="err">{{ fluxErr }}</p>

      <div v-if="displayFluxImage" class="flux-result">
        <div class="pill-row">
          <span class="pill">文生图</span>
          <span v-if="displayFluxImage.attempts && displayFluxImage.attempts > 1" class="pill muted">
            共 {{ displayFluxImage.attempts }} 轮生成（质量未达标时自动重试）
          </span>
          <span
            v-if="displayFluxImage.evaluation"
            class="pill"
            :class="displayFluxImage.evaluation.passed ? 'pill-pass' : 'pill-warn'"
          >
            质量 {{ displayFluxImage.evaluation.totalScore.toFixed(0) }} 分
            {{ displayFluxImage.evaluation.passed ? "· 通过" : "· 未达标" }}
          </span>
        </div>

        <img
          class="flux-img"
          :src="displayFluxImage.resultImageUrl"
          alt="万相生成配图"
          title="点击在新标签页查看大图"
          @click="openFluxImage(displayFluxImage.resultImageUrl)"
        />
        <a class="link" :href="displayFluxImage.resultImageUrl" target="_blank" rel="noopener noreferrer">在新标签页打开</a>

        <div v-if="displayFluxImage.evaluation" class="eval-panel">
          <p class="eval-feedback">{{ displayFluxImage.evaluation.feedback }}</p>
          <div
            v-for="dim in displayFluxImage.evaluation.dimensions"
            :key="dim.key"
            class="eval-row"
          >
            <div class="eval-meta">
              <span class="eval-label">{{ dim.label }}</span>
              <span class="eval-score" :class="scoreTone(dim.score)">{{ dim.score.toFixed(0) }}</span>
            </div>
            <div class="eval-bar">
              <div class="eval-bar-fill" :class="scoreTone(dim.score)" :style="{ width: `${dim.score}%` }" />
            </div>
          </div>
        </div>
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
}
.panel h2 {
  margin: 0 0 var(--space-4);
  font-size: 16px;
  font-weight: 800;
}
.warn {
  margin: 0 0 var(--space-4);
  padding: var(--space-3);
  border-radius: var(--radius-control);
  background: #fff8eb;
  border: 1px solid #fde68a;
  color: #92400e;
  font-size: 13px;
}
.row2 {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-bottom: var(--space-4);
}
.checks {
  align-items: center;
}
.check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-soft);
  cursor: pointer;
}
.doc-consistency-panel {
  margin-bottom: var(--space-4);
  padding: var(--space-3);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-card);
  background: var(--color-primary-soft);
}
.doc-consistency-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.doc-consistency-title {
  font-size: 12px;
  font-weight: 800;
  color: var(--color-primary);
}
.btn-link {
  border: none;
  background: transparent;
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  padding: 0;
}
.btn-link:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.doc-hint,
.doc-style-zh {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-soft);
}
.style-tokens {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.token {
  padding: 3px 8px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid var(--color-primary-border);
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 700;
}
.slide-plan {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--color-text);
}
.entity-list {
  margin: 0 0 8px;
  padding-left: 18px;
  font-size: 11px;
  color: var(--color-muted);
}
.entity-list li {
  margin-bottom: 4px;
}
.ent-anchor {
  display: block;
  margin-top: 2px;
  font-size: 10px;
  line-height: 1.35;
  color: var(--color-muted);
}
.f {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 180px;
}
label {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-muted);
}
.sel,
.ta {
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  min-height: var(--control-lg);
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
}
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
  margin-top: var(--space-2);
  padding: 0 24px;
  border: none;
  border-radius: var(--radius-control);
  background: var(--color-primary);
  color: #fff;
  font-weight: 800;
  cursor: pointer;
}
.btn.flux-btn {
  width: 100%;
}
.btn:hover:not(:disabled) {
  transform: translateY(-1px);
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
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
}
.selected-preview {
  margin-bottom: var(--space-4);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-card);
  background: var(--color-primary-soft);
  padding: var(--space-3);
}
.selected-label {
  display: block;
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 800;
  color: var(--color-primary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.selected-text {
  max-height: 120px;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.55;
  color: var(--color-text);
}
.flux-result {
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px dashed var(--color-border);
}
.pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.flux-img {
  display: block;
  width: 100%;
  max-height: min(56vh, 560px);
  object-fit: contain;
  cursor: zoom-in;
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  background: var(--color-bg-muted);
  margin: var(--space-3) 0;
}
.link {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-primary);
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
}
.pill.muted {
  background: var(--color-bg-muted);
  color: var(--color-muted);
  border-color: var(--color-border);
}
.pill-pass {
  background: #ecfdf5;
  color: #047857;
  border-color: #a7f3d0;
}
.pill-warn {
  background: #fff7ed;
  color: #c2410c;
  border-color: #fed7aa;
}
.eval-panel {
  margin-top: var(--space-4);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
.eval-feedback {
  margin: 0 0 var(--space-3);
  font-size: 13px;
  color: var(--color-text-soft);
  line-height: 1.5;
}
.eval-row + .eval-row {
  margin-top: 10px;
}
.eval-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 12px;
}
.eval-label {
  font-weight: 700;
  color: var(--color-muted);
}
.eval-score {
  font-weight: 800;
}
.eval-score.good {
  color: #047857;
}
.eval-score.mid {
  color: #b45309;
}
.eval-score.low {
  color: #b91c1c;
}
.eval-bar {
  height: 6px;
  border-radius: 999px;
  background: var(--color-bg-muted);
  overflow: hidden;
}
.eval-bar-fill {
  height: 100%;
  border-radius: 999px;
}
.eval-bar-fill.good {
  background: #10b981;
}
.eval-bar-fill.mid {
  background: #f59e0b;
}
.eval-bar-fill.low {
  background: #ef4444;
}
</style>
