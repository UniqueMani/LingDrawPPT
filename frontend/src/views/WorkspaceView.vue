<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { store } from "../store";
import { analyze, extractText, illustration } from "../api/client";
import ChartIntentPanel from "../components/ChartIntentPanel.vue";
import ChartCodePanel from "../components/ChartCodePanel.vue";
import IllustrationPromptPanel from "../components/IllustrationPromptPanel.vue";
import ResultPanel from "../components/ResultPanel.vue";
import type { SlideRequest } from "../types";

type FunctionMode = "preview" | "intent" | "code" | "illustration";

const functionMode = ref<FunctionMode>("preview");
const fileInput = ref<HTMLInputElement | null>(null);
const uploadLoading = ref(false);
const uploadMessage = ref("");

const previewBodyRef = ref<HTMLElement | null>(null);
const selectedSnippet = ref("");

/** 文档缩放档位（类似 PDF 阅读器） */
const zoomSteps = [0.82, 0.88, 1, 1.12, 1.24] as const;
const zoomIdx = ref(2);
const zoomScale = computed(() => zoomSteps[zoomIdx.value] ?? 1);
const zoomPercent = computed(() => Math.round(zoomScale.value * 100));

function zoomIn() {
  if (zoomIdx.value < zoomSteps.length - 1) zoomIdx.value += 1;
}

function zoomOut() {
  if (zoomIdx.value > 0) zoomIdx.value -= 1;
}

/** 左侧：文档版式 vs 纯解析文本 */
const leftTab = ref<"document" | "parsed">("document");
/** 右侧：配图操作 vs 生成流水线 */
const rightTab = ref<"fig" | "gen">("fig");

const currentSlide = computed(() => store.slides[store.currentIndex] ?? null);
const hasDoc = computed(() => store.slides.length > 0);
const pageLabel = computed(() => `${store.currentIndex + 1} / ${store.slides.length}`);
const canPrev = computed(() => store.currentIndex > 0);
const canNext = computed(() => store.currentIndex < store.slides.length - 1);

function newId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function createInputFromPage(title: string, text: string): SlideRequest {
  return { topic: title || "未命名页面", body: text || "", data_description: "", slide_type: "content", mode: "auto" };
}

async function onPickFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  uploadLoading.value = true;
  uploadMessage.value = "正在解析文档...";
  try {
    const resp = await extractText(store.baseUrl, file);
    store.docName = resp.filename;
    store.slides = [];

    const pages =
      resp.pages_detail.length > 0 ? resp.pages_detail : [{ page: 1, title: resp.title || "第1页", text: resp.text }];

    for (const p of pages) {
      store.slides.push({
        id: `${newId()}_${p.page}`,
        input: createInputFromPage(p.title || `第 ${p.page} 页`, p.text || ""),
        statusAnalyze: "idle",
        statusIllustration: "idle",
        history: [],
      });
    }
    store.currentIndex = 0;
    functionMode.value = "preview";
    selectedSnippet.value = "";
    zoomIdx.value = 2;
    leftTab.value = "document";
    rightTab.value = "fig";
    uploadMessage.value = "";  // 上传成功后清空状态消息
    store.addLog(`成功上传并解析文件: ${resp.filename}，共 ${store.slides.length} 页`);
  } catch (e: any) {
    uploadMessage.value = e?.message || "上传失败";
  } finally {
    uploadLoading.value = false;
    input.value = "";
  }
}

function triggerFilePick() {
  fileInput.value?.click();
}

function resetDocument() {
  if (!hasDoc.value) return;
  if (!window.confirm("确定要更换文件吗？当前所有已生成结果将被清除，此操作不可撤销。")) return;
  store.slides = [];
  store.currentIndex = 0;
  store.docName = "";
  uploadMessage.value = "";
  functionMode.value = "preview";
  selectedSnippet.value = "";
  zoomIdx.value = 2;
  store.addLog("已清除当前文档，可重新上传");
}

function prevPage() {
  if (canPrev.value) {
    store.currentIndex -= 1;
    selectedSnippet.value = "";
  }
}

function nextPage() {
  if (canNext.value) {
    store.currentIndex += 1;
    selectedSnippet.value = "";
  }
}

function goToPage(i: number) {
  if (i < 0 || i >= store.slides.length) return;
  store.currentIndex = i;
  selectedSnippet.value = "";
}

function captureSelection() {
  const root = previewBodyRef.value;
  if (!root) return;
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) return;
  const text = sel.toString().trim();
  if (!text) return;

  const anchor = sel.anchorNode;
  const focusNode = sel.focusNode;
  const endEl = (focusNode?.nodeType === Node.TEXT_NODE ? focusNode.parentElement : focusNode) as Node | null;
  const startEl = (anchor?.nodeType === Node.TEXT_NODE ? anchor.parentElement : anchor) as Node | null;
  if (!startEl || !endEl) return;
  if (!root.contains(startEl) || !root.contains(endEl)) return;

  selectedSnippet.value = text;
}

function applySelectionAsRequirement() {
  const slide = currentSlide.value;
  if (!slide || !selectedSnippet.value.trim()) return;
  slide.input.body = selectedSnippet.value.trim();
  store.addLog(`已将选中文字写入第 ${store.currentIndex + 1} 页「正文 / 需求」`);
}

function goToFunction(mode: Exclude<FunctionMode, "preview">) {
  functionMode.value = mode;
}

function backToPreview() {
  functionMode.value = "preview";
}

function onPreviewKeydown(e: KeyboardEvent) {
  if (functionMode.value !== "preview") return;
  if (e.key === "ArrowLeft") {
    e.preventDefault();
    prevPage();
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    nextPage();
  }
}

function slideStatusShort(sl: (typeof store.slides)[0]) {
  const c =
    sl.statusAnalyze === "success" ? "图表✓" : sl.statusAnalyze === "loading" ? "图表…" : "图表—";
  const i =
    sl.statusIllustration === "success"
      ? "配图✓"
      : sl.statusIllustration === "loading"
        ? "配图…"
        : "配图—";
  return `${c} · ${i}`;
}

async function generateChartOnly() {
  const slide = currentSlide.value;
  if (!slide) return;
  slide.statusAnalyze = "loading";
  slide.errorAnalyze = undefined;
  try {
    slide.analyze = await analyze(store.baseUrl, slide.input);
    slide.statusAnalyze = "success";
    store.addLog(`第 ${store.currentIndex + 1} 页：已生成数据图表`);
  } catch (e: any) {
    slide.statusAnalyze = "error";
    slide.errorAnalyze = e?.message || String(e);
    store.addLog(`图表失败: ${slide.errorAnalyze}`);
  }
}

async function generateIllusOnly() {
  const slide = currentSlide.value;
  if (!slide) return;
  slide.statusIllustration = "loading";
  slide.errorIllustration = undefined;
  try {
    slide.illustration = await illustration(store.baseUrl, slide.input);
    slide.statusIllustration = "success";
    store.addLog(`第 ${store.currentIndex + 1} 页：已生成配图策略`);
  } catch (e: any) {
    slide.statusIllustration = "error";
    slide.errorIllustration = e?.message || String(e);
    store.addLog(`配图失败: ${slide.errorIllustration}`);
  }
}

async function generateBoth() {
  const slide = currentSlide.value;
  if (!slide) return;
  slide.statusAnalyze = "loading";
  slide.statusIllustration = "loading";
  slide.errorAnalyze = undefined;
  slide.errorIllustration = undefined;

  // 独立处理两个请求，避免 Promise.all 让一个失败连累另一个状态
  const [analyzeResult, illusResult] = await Promise.allSettled([
    analyze(store.baseUrl, slide.input),
    illustration(store.baseUrl, slide.input),
  ]);

  if (analyzeResult.status === "fulfilled") {
    slide.analyze = analyzeResult.value;
    slide.statusAnalyze = "success";
  } else {
    slide.statusAnalyze = "error";
    slide.errorAnalyze = analyzeResult.reason?.message || String(analyzeResult.reason);
    store.addLog(`图表失败: ${slide.errorAnalyze}`);
  }

  if (illusResult.status === "fulfilled") {
    slide.illustration = illusResult.value;
    slide.statusIllustration = "success";
  } else {
    slide.statusIllustration = "error";
    slide.errorIllustration = illusResult.reason?.message || String(illusResult.reason);
    store.addLog(`配图失败: ${slide.errorIllustration}`);
  }

  if (analyzeResult.status === "fulfilled" && illusResult.status === "fulfilled") {
    store.addLog(`第 ${store.currentIndex + 1} 页：图表与配图均已生成`);
  }
}

const chartBusy = computed(() => currentSlide.value?.statusAnalyze === "loading");
const illusBusy = computed(() => currentSlide.value?.statusIllustration === "loading");
const anyBusy = computed(() => chartBusy.value || illusBusy.value);

function updateIllustration(next: { keywords: string[]; prompt: string }) {
  const slide = currentSlide.value;
  if (!slide?.illustration) return;
  slide.illustration.illustration.keywords = next.keywords;
  slide.illustration.illustration.prompt = next.prompt;
}

/** 可拖拽调节左右栏比例（桌面横向分栏时显示分隔条） */
const SPLITTER_PX = 6;
/** 与下方 @media (max-width: 768px) 对齐：≤768 纵向堆叠，不显示拖拽条 */
const SPLIT_LAYOUT_MIN_PX = 769;
const SPLIT_RATIO_MIN = 0.18;
const SPLIT_RATIO_MAX = 0.82;

const workFullRef = ref<HTMLElement | null>(null);
const windowWidth = ref(typeof window !== "undefined" ? window.innerWidth : 1024);
const splitRatio = ref(0.5);
const isSplitDragging = ref(false);

const splitLayoutHorizontal = computed(() => windowWidth.value >= SPLIT_LAYOUT_MIN_PX);

const workFullStyle = computed(() => {
  if (functionMode.value !== "preview") return {};
  if (!splitLayoutHorizontal.value) {
    return { display: "flex", flexDirection: "column" as const };
  }
  const L = splitRatio.value * 1000;
  const R = (1 - splitRatio.value) * 1000;
  return {
    display: "grid",
    gridTemplateColumns: `${L}fr ${SPLITTER_PX}px ${R}fr`,
    alignItems: "stretch",
  };
});

function updateSplitFromClientX(clientX: number) {
  const el = workFullRef.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const inner = rect.width - SPLITTER_PX;
  if (inner <= 0) return;
  const pos = Math.min(Math.max(0, clientX - rect.left), inner);
  let ratio = pos / inner;
  ratio = Math.min(SPLIT_RATIO_MAX, Math.max(SPLIT_RATIO_MIN, ratio));
  splitRatio.value = ratio;
}

function onSplitPointerMove(e: PointerEvent) {
  if (!isSplitDragging.value) return;
  updateSplitFromClientX(e.clientX);
}

function endSplitDrag() {
  if (!isSplitDragging.value) return;
  isSplitDragging.value = false;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  window.removeEventListener("pointermove", onSplitPointerMove);
  window.removeEventListener("pointerup", endSplitDrag);
  window.removeEventListener("pointercancel", endSplitDrag);
}

function startSplitDrag(e: PointerEvent) {
  if (functionMode.value !== "preview" || !splitLayoutHorizontal.value) return;
  e.preventDefault();
  isSplitDragging.value = true;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  updateSplitFromClientX(e.clientX);
  window.addEventListener("pointermove", onSplitPointerMove);
  window.addEventListener("pointerup", endSplitDrag);
  window.addEventListener("pointercancel", endSplitDrag);
}

function onWindowResize() {
  windowWidth.value = window.innerWidth;
  if (window.innerWidth < SPLIT_LAYOUT_MIN_PX) endSplitDrag();
}

function previewKeydownSplitAware(e: KeyboardEvent) {
  if (isSplitDragging.value && e.key === "Escape") {
    e.preventDefault();
    endSplitDrag();
    return;
  }
  onPreviewKeydown(e);
}

watch(
  () => functionMode.value,
  () => {
    endSplitDrag();
  },
);

onMounted(() => {
  window.addEventListener("keydown", previewKeydownSplitAware);
  window.addEventListener("resize", onWindowResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", previewKeydownSplitAware);
  window.removeEventListener("resize", onWindowResize);
  endSplitDrag();
});
</script>

<template>
  <div class="workspace-root">
    <div v-if="!hasDoc" class="upload-phase">
      <div class="upload-card">
        <p class="upload-badge">第一步</p>
        <h2>上传 PDF 或 PPT</h2>
        <p class="upload-lead">
          支持 .pptx 与 .pdf。解析后左侧为全宽文档预览，右侧为翻页、缩放、配图与生成等全部操作。
        </p>

        <div class="drop-zone" @click="triggerFilePick">
          <div v-if="!uploadLoading" class="hint">
            <span class="icon">📁</span>
            <span>点击选择文件</span>
          </div>
          <div v-else class="loader">
            <div class="spinner"></div>
            <p>{{ uploadMessage }}</p>
          </div>
        </div>

        <input ref="fileInput" type="file" accept=".pptx,.pdf" class="hidden" @change="onPickFile" />

        <p v-if="uploadMessage && !uploadLoading" class="msg">{{ uploadMessage }}</p>
      </div>
    </div>

    <div v-else ref="workFullRef" class="work-full" :style="workFullStyle">
      <template v-if="functionMode === 'preview'">
        <!-- 左：仅文档预览区（PDF 式纸张） -->
        <section class="reader-column" aria-label="文档预览">
          <div class="reader-viewport reader-viewport--solo">
            <div class="paper-scale" :style="{ transform: `scale(${zoomScale})` }">
              <article class="paper">
                <p v-if="leftTab === 'document'" class="paper-kicker">阅读视图 · 文本来自解析结果（非嵌入式 PDF 二进制）</p>
                <p v-else class="paper-kicker muted">解析文本 · 便于对照复制</p>
                <h2 class="paper-title">{{ currentSlide?.input.topic }}</h2>
                <div
                  ref="previewBodyRef"
                  class="paper-body selectable"
                  :class="{ 'paper-body--cols': leftTab === 'document', 'paper-body--parsed': leftTab === 'parsed' }"
                  @mouseup="captureSelection"
                >
                  {{ currentSlide?.input.body || "（本页无正文）" }}
                </div>
                <div v-if="currentSlide?.input.data_description" class="paper-extra">
                  <span class="paper-extra-label">结构化数据</span>
                  <pre class="paper-extra-pre">{{ currentSlide.input.data_description }}</pre>
                </div>
              </article>
            </div>
          </div>
        </section>

        <div
          v-if="splitLayoutHorizontal"
          class="pane-splitter"
          :class="{ dragging: isSplitDragging }"
          role="separator"
          aria-orientation="vertical"
          aria-label="拖动调节左右栏宽度"
          title="拖动调节左右栏宽度"
          @pointerdown="startSplitDrag"
        />

        <!-- 右：视图切换、导航、缩放与全部操作 -->
        <aside class="tools-column">
          <div class="pane-tabs doc-view-tabs">
            <button type="button" class="pane-tab" :class="{ active: leftTab === 'document' }" @click="leftTab = 'document'">
              文档
            </button>
            <button type="button" class="pane-tab" :class="{ active: leftTab === 'parsed' }" @click="leftTab = 'parsed'">
              解析文本
            </button>
          </div>

          <header class="preview-toolbar">
            <div class="tb-left">
              <span class="tb-doc">{{ store.docName }}</span>
              <span v-if="currentSlide" class="tb-status">{{ slideStatusShort(currentSlide) }}</span>
            </div>
            <div class="tb-center">
              <button type="button" class="tb-icon" :disabled="!canPrev" title="上一页（←）" @click="prevPage">‹</button>
              <span class="tb-page">第 {{ pageLabel }} 页</span>
              <button type="button" class="tb-icon" :disabled="!canNext" title="下一页（→）" @click="nextPage">›</button>
            </div>
            <div class="tb-zoom" aria-label="缩放">
              <button type="button" class="tb-zoom-btn" :disabled="zoomIdx <= 0" title="缩小" @click="zoomOut">−</button>
              <span class="tb-zoom-val">{{ zoomPercent }}%</span>
              <button
                type="button"
                class="tb-zoom-btn"
                :disabled="zoomIdx >= zoomSteps.length - 1"
                title="放大"
                @click="zoomIn"
              >
                +
              </button>
            </div>
            <button type="button" class="tb-replace" @click="resetDocument">更换文件</button>
          </header>

          <div class="page-chips" aria-label="页面">
            <button
              v-for="(s, i) in store.slides"
              :key="s.id"
              type="button"
              class="page-chip"
              :class="{ active: i === store.currentIndex }"
              @click="goToPage(i)"
            >
              {{ i + 1 }}
            </button>
          </div>

          <div class="pane-tabs tools-tabs">
            <button type="button" class="pane-tab" :class="{ active: rightTab === 'fig' }" @click="rightTab = 'fig'">配图</button>
            <button type="button" class="pane-tab" :class="{ active: rightTab === 'gen' }" @click="rightTab = 'gen'">生成</button>
          </div>

          <div class="tools-scroll">
            <div v-show="rightTab === 'fig'" class="tools-section">
              <p class="sec-label">选区与需求</p>
              <div class="selection-row">
                <div class="selection-preview">{{ selectedSnippet || "在左侧正文拖选文字…" }}</div>
                <button type="button" class="btn-use" :disabled="!selectedSnippet.trim()" @click="applySelectionAsRequirement">
                  写入本页正文
                </button>
              </div>
              <p class="sec-label">功能入口</p>
              <div class="jump-stack">
                <button type="button" class="jump" @click="goToFunction('intent')">图表意图</button>
                <button type="button" class="jump" @click="goToFunction('code')">图表代码</button>
                <button type="button" class="jump" @click="goToFunction('illustration')">文生图配图</button>
              </div>
            </div>

            <div v-show="rightTab === 'gen'" class="tools-section gen-section">
              <p class="sec-label">经典流水线</p>
              <p class="sec-hint">/api/analyze 与 /api/illustration</p>
              <div class="pipeline-actions">
                <button type="button" class="btn ghost" :disabled="anyBusy || !currentSlide" @click="generateChartOnly">
                  <span v-if="chartBusy" class="btn-spinner wine-spin"></span>
                  仅数据图表
                </button>
                <button type="button" class="btn ghost" :disabled="anyBusy || !currentSlide" @click="generateIllusOnly">
                  <span v-if="illusBusy" class="btn-spinner wine-spin"></span>
                  仅文生图策略
                </button>
                <button type="button" class="btn solid" :disabled="anyBusy || !currentSlide" @click="generateBoth">
                  <span v-if="chartBusy && illusBusy" class="btn-spinner"></span>
                  图表 + 配图
                </button>
              </div>
              <div v-if="currentSlide && (currentSlide.analyze || currentSlide.illustration)" class="pipeline-result">
                <ResultPanel
                  :slide="currentSlide"
                  :onRerunChart="generateChartOnly"
                  :onRerunIllustration="generateIllusOnly"
                  :onRerunBoth="generateBoth"
                  :onChangeIllustration="updateIllustration"
                />
              </div>
              <p v-else class="pipeline-empty">运行上方按钮后展示结果。</p>
            </div>
          </div>
        </aside>
      </template>

      <div v-else class="function-shell">
        <header class="fn-toolbar">
          <button type="button" class="fn-back" @click="backToPreview">← 返回文档阅读</button>
          <span class="fn-title">{{
            functionMode === "intent" ? "图表意图" : functionMode === "code" ? "图表代码" : "文生图配图"
          }}</span>
          <span class="fn-meta">第 {{ pageLabel }} 页 · {{ currentSlide?.input.topic }}</span>
        </header>
        <div class="fn-scroll">
          <ChartIntentPanel v-if="functionMode === 'intent' && currentSlide" v-model:slide="currentSlide.input" />
          <ChartCodePanel v-if="functionMode === 'code' && currentSlide" v-model:slide="currentSlide.input" />
          <IllustrationPromptPanel
            v-if="functionMode === 'illustration' && currentSlide"
            v-model:slide="currentSlide.input"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.workspace-root {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: calc(100vh - 70px);
  background: #fafafa;
  color: #1a1a1a;
}

.upload-phase {
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 40px 24px;
  background: #fafafa;
}

.upload-card {
  background: #ffffff;
  padding: 36px 40px;
  border-radius: 8px;
  border: 1px solid #e8e0e2;
  width: min(640px, 100%);
  text-align: center;
  box-shadow: 0 4px 24px rgba(139, 41, 66, 0.06);
}

.upload-badge {
  display: inline-block;
  margin: 0 0 12px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #ffffff;
  background: #8b2942;
  padding: 6px 14px;
  border-radius: 4px;
}

.upload-card h2 {
  margin: 0 0 12px;
  font-size: 22px;
  font-weight: 700;
  color: #1a1a1a;
}

.upload-lead {
  margin: 0 0 28px;
  font-size: 14px;
  line-height: 1.65;
  color: #5c5c5c;
}

.drop-zone {
  border: 1px dashed #c4b8bc;
  border-radius: 8px;
  padding: 56px 24px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.drop-zone:hover {
  background: #fffafb;
  border-color: #8b2942;
}

.hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  color: #3d3d3d;
}

.icon {
  font-size: 48px;
}

.loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #6b6b6b;
  font-size: 14px;
}

.spinner {
  border: 3px solid #eee;
  border-top: 3px solid #8b2942;
  border-radius: 50%;
  width: 32px;
  height: 32px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.hidden {
  display: none;
}

.msg {
  margin-top: 16px;
  color: #8b2942;
  font-size: 14px;
}

.work-full {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  direction: ltr;
  align-items: stretch;
  background: #fafafa;
}

/* 预览模式下宽度由 grid + 可拖拽分隔条控制 */
.reader-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: none;
  background: #f3f1f2;
}

.tools-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #ffffff;
}

.pane-splitter {
  z-index: 2;
  width: 6px;
  margin: 0 -1px;
  flex-shrink: 0;
  cursor: col-resize;
  touch-action: none;
  background: linear-gradient(90deg, #dcd4d7 0%, #ebe6e8 50%, #dcd4d7 100%);
  box-shadow: inset 0 0 0 1px rgba(139, 41, 66, 0.12);
  transition: background 0.12s ease, box-shadow 0.12s ease;
}

.pane-splitter:hover,
.pane-splitter.dragging {
  background: #8b2942;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2);
}

.pane-splitter.dragging {
  cursor: col-resize;
}

.pane-tabs {
  display: flex;
  gap: 0;
  padding: 0 12px;
  border-bottom: 1px solid #e8e0e2;
  background: #ffffff;
}

.pane-tab {
  padding: 12px 18px;
  border: none;
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  color: #8a8a8a;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.15s;
}

.pane-tab:hover {
  color: #5c5c5c;
}

.pane-tab.active {
  color: #8b2942;
  border-bottom-color: #8b2942;
}

.tools-tabs {
  background: #fafafa;
}

.doc-view-tabs {
  background: #ffffff;
}

.preview-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px 12px;
  padding: 10px 14px;
  background: #ffffff;
  border-bottom: 1px solid #e8e0e2;
}

.tb-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.tb-doc {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a1a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.tb-status {
  font-size: 11px;
  font-weight: 600;
  color: #7a7a7a;
}

.tb-center {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tb-page {
  font-size: 13px;
  font-weight: 600;
  color: #3d3d3d;
  min-width: 96px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.tb-icon {
  width: 34px;
  height: 34px;
  border-radius: 6px;
  border: 1px solid #d9cdd1;
  background: #ffffff;
  color: #2d2d2d;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

.tb-icon:hover:not(:disabled) {
  border-color: #8b2942;
  color: #8b2942;
}

.tb-icon:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.tb-zoom {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tb-zoom-btn {
  width: 30px;
  height: 30px;
  border-radius: 6px;
  border: 1px solid #d9cdd1;
  background: #ffffff;
  font-size: 16px;
  font-weight: 600;
  color: #2d2d2d;
  cursor: pointer;
  line-height: 1;
}

.tb-zoom-btn:hover:not(:disabled) {
  border-color: #8b2942;
  color: #8b2942;
}

.tb-zoom-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.tb-zoom-val {
  font-size: 12px;
  font-weight: 600;
  color: #5c5c5c;
  min-width: 44px;
  text-align: center;
}

.tb-replace {
  flex-shrink: 0;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #d9cdd1;
  background: #ffffff;
  color: #3d3d3d;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.tb-replace:hover {
  border-color: #8b2942;
  color: #8b2942;
}

.reader-viewport {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 20px 24px 12px;
  background: #f3f1f2;
  display: flex;
  justify-content: center;
  align-items: flex-start;
}

.reader-viewport--solo {
  flex: 1;
  min-height: 0;
}

.paper-scale {
  transform-origin: top center;
  transition: transform 0.18s ease;
  margin-bottom: 24px;
}

.paper {
  width: min(720px, 100%);
  background: #ffffff;
  border: 1px solid #e0d8db;
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  padding: clamp(24px, 3vw, 40px);
  box-sizing: border-box;
}

.paper-kicker {
  margin: 0 0 12px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #8b2942;
}

.paper-kicker.muted {
  color: #8a8a8a;
}

.paper-title {
  margin: 0 0 20px;
  font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", SimSun, serif;
  font-size: clamp(20px, 2.4vw, 26px);
  font-weight: 700;
  color: #1a1a1a;
  line-height: 1.35;
}

.paper-body {
  font-size: 14px;
  line-height: 1.75;
  color: #2d2d2d;
  white-space: pre-wrap;
  word-break: break-word;
}

.paper-body--cols {
  column-count: 2;
  column-gap: 28px;
}

.paper-body--parsed {
  column-count: 1;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 13px;
  line-height: 1.65;
}

@media (max-width: 720px) {
  .paper-body--cols {
    column-count: 1;
  }
}

.paper-body.selectable {
  user-select: text;
  cursor: text;
}

.paper-body::selection {
  background: #f5d4dc;
  color: #1a1a1a;
}

.paper-extra {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px dashed #ddd5d8;
}

.paper-extra-label {
  font-size: 10px;
  font-weight: 700;
  color: #8b2942;
  display: block;
  margin-bottom: 8px;
}

.paper-extra-pre {
  margin: 0;
  font-size: 12px;
  color: #4a4a4a;
  white-space: pre-wrap;
}

.page-chips {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px 12px;
  border-top: 1px solid #e8e0e2;
  border-bottom: 1px solid #e8e0e2;
  background: #fafafa;
  max-height: 120px;
  overflow-y: auto;
}

.page-chip {
  min-width: 36px;
  padding: 6px 10px;
  border-radius: 4px;
  border: 1px solid #d9cdd1;
  background: #ffffff;
  font-size: 12px;
  font-weight: 600;
  color: #5c5c5c;
  cursor: pointer;
}

.page-chip:hover {
  border-color: #8b2942;
  color: #8b2942;
}

.page-chip.active {
  background: #8b2942;
  border-color: #8b2942;
  color: #ffffff;
}

.tools-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 16px 24px;
}

.tools-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sec-label {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #6b6b6b;
}

.sec-hint {
  margin: -8px 0 8px;
  font-size: 12px;
  color: #9a9a9a;
}

.selection-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.selection-preview {
  min-height: 56px;
  max-height: 100px;
  overflow-y: auto;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #e0d8db;
  background: #fafafa;
  font-size: 13px;
  line-height: 1.45;
  color: #2d2d2d;
}

.btn-use {
  align-self: flex-start;
  padding: 10px 16px;
  border-radius: 6px;
  border: 1px solid #8b2942;
  background: #ffffff;
  color: #8b2942;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}

.btn-use:hover:not(:disabled) {
  background: #8b2942;
  color: #ffffff;
}

.btn-use:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.jump-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.jump {
  padding: 12px 14px;
  border-radius: 6px;
  border: 1px solid #8b2942;
  background: #ffffff;
  color: #8b2942;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.jump:hover {
  background: #8b2942;
  color: #ffffff;
}

.gen-section .pipeline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.btn {
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn.ghost {
  border: 1px solid #c4b8bc;
  background: #ffffff;
  color: #4a4a4a;
}

.btn.ghost:hover:not(:disabled) {
  border-color: #8b2942;
  color: #8b2942;
}

.btn.solid {
  border: 1px solid #8b2942;
  background: #8b2942;
  color: #ffffff;
}

.btn.solid:hover:not(:disabled) {
  filter: brightness(1.05);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pipeline-result {
  margin-top: 12px;
}

.pipeline-empty {
  margin: 12px 0 0;
  font-size: 12px;
  color: #8a8a8a;
}

.btn-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.btn-spinner.wine-spin {
  border-color: rgba(139, 41, 66, 0.25);
  border-top-color: #8b2942;
}

.function-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fafafa;
}

.fn-toolbar {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  padding: 12px 16px;
  background: #ffffff;
  border-bottom: 1px solid #e8e0e2;
}

.fn-back {
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid #d9cdd1;
  background: #ffffff;
  font-size: 13px;
  font-weight: 600;
  color: #3d3d3d;
  cursor: pointer;
}

.fn-back:hover {
  border-color: #8b2942;
  color: #8b2942;
}

.fn-title {
  font-size: 15px;
  font-weight: 700;
  color: #1a1a1a;
}

.fn-meta {
  margin-left: auto;
  font-size: 12px;
  font-weight: 500;
  color: #7a7a7a;
}

.fn-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px 32px;
}

@media (max-width: 768px) {
  .work-full {
    flex-direction: column;
  }

  .reader-column {
    flex: 1 1 auto;
    border-right: none;
    border-bottom: 1px solid #e8e0e2;
    min-height: 48vh;
    max-height: 56vh;
  }

  .tools-column {
    flex: 1 1 auto;
    min-width: 0;
    max-width: none;
    width: 100%;
    max-height: none;
  }

  .preview-toolbar {
    justify-content: flex-start;
  }

  .page-chips {
    max-height: 88px;
  }
}
</style>
