<script setup lang="ts">
import { computed, ref } from "vue";
import { analyzeDocumentConsistency } from "../api/client";
import { store } from "../store";
import type {
  AnalyzeDocumentResponse,
  FluxGenerateImagePayload,
  FluxGenerateImageResponse,
  ImageGenAttemptLog,
  SlideRequest,
} from "../types";

const slide = defineModel<SlideRequest>("slide", { required: true });
const props = defineProps<{
  slidePage?: number;
  docConsistency?: AnalyzeDocumentResponse | null;
  previewUrl?: string;
  initialFluxImage?: FluxGenerateImageResponse | null;
  fluxLoading?: boolean;
  fluxError?: string;
}>();
const emit = defineEmits<{
  fluxGenerateRequest: [payload: FluxGenerateImagePayload];
}>();

const extraStyleWords = ref("");
const wanModel = ref("wan2.6-t2i");
const aspectRatio = ref("16:9");
const generationMode = ref<"standard" | "fast">("standard");
const promptExtend = ref(true);
const useDocStyle = ref(true);
const useEntitySync = ref(true);
const docAnalyzing = ref(false);

const fluxErr = ref("");

const displayFluxImage = computed(() => props.initialFluxImage || null);
const displayFluxImageUrl = computed(() => displayFluxImage.value?.resultImageUrl || "");
const displayFluxAttempts = computed(() => displayFluxImage.value?.attempts || 0);
const displaySelectedAttempt = computed(() => displayFluxImage.value?.selectedAttempt || displayFluxAttempts.value || 1);
const displayFluxAttemptsLog = computed(() => displayFluxImage.value?.attemptsLog || []);
const displayFluxEvaluation = computed(() => displayFluxImage.value?.evaluation || null);
const displayFluxScore = computed(() => displayFluxEvaluation.value?.totalScore ?? 0);
const displayFluxThreshold = computed(() => displayFluxEvaluation.value?.passThreshold ?? 72);
const displayFluxPassed = computed(() => Boolean(displayFluxEvaluation.value?.passed));
const displayFluxFeedback = computed(() => displayFluxEvaluation.value?.feedback || "");
const displayFluxFeedbackLines = computed(() => splitEvaluationText(displayFluxFeedback.value));
const displayFluxDimensions = computed(() => displayFluxEvaluation.value?.dimensions || []);
const hasFluxEvaluation = computed(() => Boolean(displayFluxEvaluation.value));
const displayFluxError = computed(() => fluxErr.value || props.fluxError || "");
const isFluxLoading = computed(() => Boolean(props.fluxLoading));
const selectedText = computed(() => slide.value.body?.trim() || "");
const canGenerateFlux = computed(() => Boolean(selectedText.value || slide.value.topic?.trim()));
const fluxScoreRows = computed(() =>
  displayFluxDimensions.value.map((item) => {
    const maxScore = item.maxScore || 100;
    const score = Math.max(0, Math.min(maxScore, Number(item.score) || 0));
    const deducted = item.deducted ?? Math.max(0, maxScore - score);
    const percent = maxScore > 0 ? Math.max(0, Math.min(100, (score / maxScore) * 100)) : 0;
    const deductionLines = formatDimensionLines(item, deducted);
    return {
      ...item,
      maxScore,
      score,
      deducted,
      percent,
      tone: scoreTone(score),
      deductionReason: deductionLines.join("；"),
      deductionLines,
    };
  })
);

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

function dimensionScore(entry: ImageGenAttemptLog, key: string) {
  return entry.evaluation?.dimensions?.find((item) => item.key === key)?.score ?? null;
}

const fluxCandidateDetails = computed(() =>
  displayFluxAttemptsLog.value.map((entry: ImageGenAttemptLog) => ({
    attempt: entry.attempt,
    score: entry.evaluation?.totalScore ?? 0,
    selected: entry.attempt === displaySelectedAttempt.value,
    textFidelity: dimensionScore(entry, "text_fidelity"),
    semantic: dimensionScore(entry, "semantic_alignment"),
    layout: dimensionScore(entry, "layout_quality"),
    feedback: entry.evaluation?.feedback || "",
    feedbackLines: splitEvaluationText(entry.evaluation?.feedback || ""),
  }))
);

const fluxRoundSummaries = computed(() =>
  displayFluxAttemptsLog.value.map((entry: ImageGenAttemptLog) => ({
    attempt: entry.attempt,
    score: entry.evaluation?.totalScore ?? 0,
    passed: Boolean(entry.evaluation?.passed),
    selected: entry.attempt === displaySelectedAttempt.value,
  }))
);

function openFluxImage(url: string) {
  if (url) window.open(url, "_blank", "noopener,noreferrer");
}

function splitEvaluationText(text: string) {
  const normalized = String(text || "")
    .replace(/\s+/g, " ")
    .replace(/[•●]/g, "；")
    .trim();
  if (!normalized) return [];

  const roughParts = normalized
    .split(/[；;。\n]+/)
    .map((item) => item.trim().replace(/^[-·]\s*/, ""))
    .filter(Boolean);

  const parts: string[] = [];
  for (const part of roughParts) {
    if (part.length <= 72) {
      parts.push(part);
      continue;
    }
    let buffer = "";
    for (const segment of part.split(/[，,]/).map((item) => item.trim()).filter(Boolean)) {
      const next = buffer ? `${buffer}，${segment}` : segment;
      if (next.length > 72 && buffer) {
        parts.push(buffer);
        buffer = segment;
      } else {
        buffer = next;
      }
    }
    if (buffer) parts.push(buffer);
  }
  return parts;
}

function stripDeductionPrefix(text: string) {
  return String(text || "")
    .replace(/^[^：:]{0,16}扣\s*\d+(?:\.\d+)?\s*分[：:]\s*/, "")
    .trim();
}

function formatDimensionLines(item: any, deducted: number) {
  const lines: string[] = [];
  if (deducted > 0.5) {
    lines.push(`${item.label || "该维度"}扣 ${deducted.toFixed(0)} 分`);
  } else {
    lines.push("未明显扣分");
  }

  const detailText = stripDeductionPrefix(item.detail || item.deductionReason || "");
  const detailLines = splitEvaluationText(detailText);
  if (detailLines.length) {
    lines.push(...detailLines);
  } else if (deducted > 0.5) {
    lines.push("该维度仍有优化空间");
  }

  return Array.from(new Set(lines));

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

function runFluxGenerate() {
  if (!canGenerateFlux.value) {
    fluxErr.value = "请先在预览区框选文字并写入正文，或填写页面主题。";
    return;
  }

  fluxErr.value = "";
  emit("fluxGenerateRequest", {
    selected_text: selectedText.value,
    topic: slide.value.topic,
    slide_page: props.slidePage || 1,
    slide_type: slide.value.slide_type || "content",
    use_doc_style: useDocStyle.value,
    use_entity_sync: useEntitySync.value,
    doc_consistency: useDocStyle.value || useEntitySync.value ? docProfile.value : null,
    preview_path: previewPathFromUrl(props.previewUrl),
    aspect_ratio: aspectRatio.value,
    model: wanModel.value,
    generation_mode: generationMode.value,
    prompt_extend: promptExtend.value,
    extra_style_words: extraStyleWords.value.trim() || null,
  });
}

defineExpose({ runFluxGenerate, getAspectRatio });
</script>

<template>
  <div class="panel-root">
    <div class="panel flux-panel">
      <h2>万相文生图</h2>

      <p v-if="!selectedText" class="warn">正文为空：请在当前页输入正文，或填写页面主题。</p>

      <div class="row2 flux-params">
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

      <div class="mode-segment" aria-label="文生图生成模式">
        <button
          type="button"
          class="mode-option"
          :class="{ active: generationMode === 'standard' }"
          @click="generationMode = 'standard'"
        >
          <strong>通用模式</strong>
          <span>独立生成 3 张候选，评分后选最优</span>
        </button>
        <button
          type="button"
          class="mode-option"
          :class="{ active: generationMode === 'fast' }"
          @click="generationMode = 'fast'"
        >
          <strong>极速模式</strong>
          <span>只生成 1 次，并直接输出质量评估</span>
        </button>
      </div>

      <div class="row2 checks config-checks">
        <label class="check">
          <input v-model="promptExtend" type="checkbox" />
          智能改写 Prompt
        </label>
      </div>

      <div class="doc-consistency-panel">
        <div class="doc-consistency-head">
          <span class="doc-consistency-title">文档级一致性 / 多图协同</span>
          <button type="button" class="btn-link" :disabled="docAnalyzing" @click="rerunDocAnalysis">
            {{ docAnalyzing ? "分析中..." : "重新分析文档" }}
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
            本页：<b>{{ currentSlidePlan.page_role || currentSlidePlan.slide_role }}</b>
            <template v-if="currentSlidePlan.topic_type || currentSlidePlan.content_intent">
              · topic={{ currentSlidePlan.topic_type || "—" }}
              · intent={{ currentSlidePlan.content_intent || "—" }}
              · visual={{ currentSlidePlan.visual_type || "—" }}
            </template>
            <br />
            {{ currentSlidePlan.visual_focus }}
            <span v-if="currentSlidePlan.related_pages?.length" class="related-pages">
              （关联页：{{ currentSlidePlan.related_pages.join(", ") }}）
            </span>
            <span v-if="currentSlidePlan.primitive_keys?.length" class="primitive-keys">
              · 复用组件：{{ currentSlidePlan.primitive_keys.join(", ") }}
            </span>
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

      <div class="field-stack">
        <div class="f">
          <label>结构化数据（可选）</label>
          <textarea
            v-model="slide.data_description"
            class="ta dim"
            rows="3"
            placeholder="实体、指标、数值等结构化补充；用于辅助插图 Prompt。"
          />
        </div>
        <div class="f">
          <label>追加风格词</label>
          <textarea v-model="extraStyleWords" class="ta" rows="2" placeholder="如：扁平矢量、科技蓝、无文字" />
        </div>
      </div>

      <button class="btn flux-btn" type="button" :disabled="isFluxLoading || !canGenerateFlux" @click="runFluxGenerate">
        {{ isFluxLoading ? "生成与质量评估中..." : "根据选中文字生成图片" }}
      </button>
      <p v-if="displayFluxError" class="err">{{ displayFluxError }}</p>

      <div v-if="displayFluxImageUrl" class="flux-result">
        <div class="pill-row">
          <span class="pill">文生图</span>
          <span v-if="displayFluxAttempts > 1" class="pill muted">
            共 {{ displayFluxAttempts }} 轮 · 选用第 {{ displaySelectedAttempt }} 轮
          </span>
          <span
            v-if="hasFluxEvaluation"
            class="pill"
            :class="displayFluxPassed ? 'pill-pass' : 'pill-warn'"
          >
            质量 {{ displayFluxScore.toFixed(0) }} 分
            {{ displayFluxPassed ? "· 通过" : "· 未达标" }}
          </span>
        </div>

        <img
          class="flux-img"
          :src="displayFluxImageUrl"
          alt="万相生成配图"
          title="点击在新标签页查看大图"
          @click="openFluxImage(displayFluxImageUrl)"
        />
        <a class="link" :href="displayFluxImageUrl" target="_blank" rel="noopener noreferrer">点击下载</a>

        <div v-if="hasFluxEvaluation" class="eval-panel">
          <div class="eval-summary">
            <div>
              <span class="eval-kicker">综合分 / 及格线</span>
              <strong>{{ displayFluxScore.toFixed(0) }} / {{ displayFluxThreshold.toFixed(0) }}</strong>
              <span class="eval-score-note">左侧为最终选用图的综合分，右侧为通过阈值（默认 72）</span>
            </div>
            <span :class="displayFluxPassed ? 'eval-status pass' : 'eval-status warn'">
              {{ displayFluxPassed ? "通过" : "未达标" }}
            </span>
          </div>
          <div v-if="displayFluxFeedbackLines.length" class="eval-feedback-card">
            <span class="eval-section-title">主要建议</span>
            <ul class="eval-note-list">
              <li v-for="line in displayFluxFeedbackLines" :key="line">{{ line }}</li>
            </ul>
          </div>
          <div v-if="fluxRoundSummaries.length > 1" class="eval-rounds">
            <span class="eval-rounds-title">各轮得分</span>
            <div class="eval-rounds-row">
              <span
                v-for="item in fluxRoundSummaries"
                :key="item.attempt"
                class="eval-round-chip"
                :class="{ selected: item.selected }"
              >
                第 {{ item.attempt }} 轮 {{ item.score.toFixed(0) }} 分
                <template v-if="item.selected">（选用）</template>
              </span>
            </div>
          </div>
          <details v-if="fluxCandidateDetails.length > 1" class="refine-panel">
            <summary class="refine-title">候选对比（独立生成，同一 Prompt）</summary>
            <article v-for="item in fluxCandidateDetails" :key="item.attempt" class="refine-step">
              <header class="refine-step-head">
                <strong>候选 {{ item.attempt }}</strong>
                <span>
                  综合 {{ item.score.toFixed(0) }} 分
                  <template v-if="item.selected"> · 已选用</template>
                </span>
              </header>
              <p class="refine-meta">
                文字真实性 {{ item.textFidelity?.toFixed(0) ?? "-" }} ·
                语义 {{ item.semantic?.toFixed(0) ?? "-" }} ·
                布局 {{ item.layout?.toFixed(0) ?? "-" }}
              </p>
              <ul v-if="item.feedbackLines.length" class="eval-note-list compact">
                <li v-for="line in item.feedbackLines" :key="line">{{ line }}</li>
              </ul>
            </article>
          </details>
          <details v-if="fluxScoreRows.length" class="eval-detail-panel">
            <summary class="eval-section-title">维度评分详情</summary>
            <div class="eval-list">
            <div v-for="item in fluxScoreRows" :key="item.key" class="eval-row">
              <div class="eval-meta">
                <span class="eval-label">{{ item.label }}</span>
                <span class="eval-score" :class="item.tone">
                  {{ item.score.toFixed(0) }} / {{ item.maxScore.toFixed(0) }}
                </span>
              </div>
              <div class="eval-bar" :aria-label="`${item.label} ${item.score.toFixed(0)} 分`">
                <div class="eval-bar-fill" :class="item.tone" :style="{ width: `${item.percent}%` }" />
              </div>
              <ul class="eval-note-list compact">
                <li v-for="line in item.deductionLines" :key="line">{{ line }}</li>
              </ul>
            </div>
            </div>
          </details>
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
  margin-bottom: 0;
}
.flux-params {
  margin-bottom: var(--space-3);
}
.mode-segment {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: var(--space-4);
}
.mode-option {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--motion-base), background var(--motion-base), box-shadow var(--motion-base);
}
.mode-option strong,
.mode-option span {
  display: block;
}
.mode-option strong {
  font-size: 13px;
  font-weight: 900;
}
.mode-option span {
  margin-top: 3px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--color-muted);
}
.mode-option.active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  box-shadow: 0 0 0 3px rgba(139, 41, 66, 0.1);
}
.checks {
  align-items: center;
}
.config-checks {
  padding-top: 2px;
  margin-bottom: var(--space-4);
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
  flex: 1 1 180px;
  min-width: 0;
}
.field-stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.field-stack .f {
  flex: 0 0 auto;
}
label {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-muted);
}
.sel,
.ta {
  width: 100%;
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
.ta.dim {
  background: var(--color-primary-soft);
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
.eval-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.eval-summary strong {
  display: block;
  margin-top: 2px;
  font-size: 18px;
  color: var(--color-primary);
}
.eval-kicker {
  display: block;
  font-size: 11px;
  font-weight: 800;
  color: var(--color-muted);
}
.eval-status {
  flex: 0 0 auto;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
}
.eval-status.pass {
  background: var(--color-primary-soft);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-border);
}
.eval-status.warn {
  background: var(--color-danger-soft);
  color: var(--color-danger);
  border: 1px solid #fecaca;
}
.eval-feedback-card {
  margin: 0 0 var(--space-4);
  padding: var(--space-3);
  border-left: 4px solid var(--color-primary);
  border-radius: var(--radius-control);
  background: var(--color-bg-muted);
}
.eval-section-title {
  display: block;
  font-size: 13px;
  font-weight: 800;
  color: var(--color-text);
}
.eval-feedback-card .eval-section-title {
  margin-bottom: 8px;
}
.eval-note-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  color: var(--color-text-soft);
  font-size: 13px;
  line-height: 1.5;
}
.eval-note-list li {
  padding-left: 2px;
}
.eval-note-list.compact {
  margin-top: 8px;
  gap: 4px;
  font-size: 12px;
}
.eval-score-note {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-muted);
  font-weight: 500;
}
.eval-rounds {
  margin-bottom: var(--space-4);
}
.eval-rounds-title,
.refine-title {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 800;
  color: var(--color-text-soft);
}
.eval-rounds-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.eval-round-chip {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-muted);
  font-size: 12px;
  color: var(--color-text-soft);
}
.eval-round-chip.selected {
  border-color: var(--color-primary-border);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-weight: 700;
}
.refine-panel {
  margin-bottom: var(--space-4);
  padding: var(--space-3);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-control);
  background: #fff;
}
.refine-panel[open] {
  background: #fffafa;
}
.refine-panel summary,
.eval-detail-panel summary {
  cursor: pointer;
  user-select: none;
}
.eval-detail-panel {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: #fff;
}
.eval-detail-panel[open] .eval-section-title {
  margin-bottom: var(--space-3);
}
.refine-step + .refine-step {
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border);
}
.refine-step-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 13px;
}
.refine-step-head span {
  font-size: 12px;
  color: var(--color-muted);
}
.refine-meta,
.refine-discarded,
.refine-next {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--color-text-soft);
  line-height: 1.5;
}
.refine-fix-list {
  margin: 0 0 8px;
  padding-left: 18px;
  font-size: 12px;
  color: var(--color-text);
}
.refine-fix-list li + li {
  margin-top: 4px;
}
.refine-fix-area {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 700;
}
.refine-next code {
  display: block;
  margin-top: 4px;
  padding: 8px;
  border-radius: var(--radius-control);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 11px;
}
.eval-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.eval-row {
  padding: 10px 0;
}
.eval-row + .eval-row {
  border-top: 1px solid var(--color-border);
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
  min-width: 0;
}
.eval-score {
  font-weight: 800;
  white-space: nowrap;
}
.eval-score.good {
  color: var(--color-primary);
}
.eval-score.mid {
  color: #b45309;
}
.eval-score.low {
  color: #b91c1c;
}
.eval-bar {
  height: 8px;
  border-radius: 999px;
  background: var(--color-bg-muted);
  overflow: hidden;
}
.eval-bar-fill {
  height: 100%;
  border-radius: 999px;
}
.eval-bar-fill.good {
  background: var(--color-primary);
}
.eval-bar-fill.mid {
  background: #f59e0b;
}
.eval-bar-fill.low {
  background: #ef4444;
}
</style>
