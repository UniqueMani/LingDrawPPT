<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { store } from "../store";
import { analyze, extractText, illustration } from "../api/client";
import ChartIntentPanel from "../components/ChartIntentPanel.vue";
import ChartCodePanel from "../components/ChartCodePanel.vue";
import IllustrationPromptPanel from "../components/IllustrationPromptPanel.vue";
import type { SlideRequest } from "../types";

type FunctionMode = "preview" | "intent" | "code" | "illustration";
type WorkflowStep = "intent" | "chart" | "illustration";

const functionMode = ref<FunctionMode>("preview");
const fileInput = ref<HTMLInputElement | null>(null);
const uploadLoading = ref(false);
const uploadMessage = ref("");

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

/** 右侧：配图操作 vs 生成流水线 */
const activeWorkflowStep = ref<WorkflowStep>("intent");

const currentSlide = computed(() => store.slides[store.currentIndex] ?? null);
const currentIllustrationResult = computed(() => {
  const illustrationResult = currentSlide.value?.illustration?.illustration;
  if (!illustrationResult) return null;
  return {
    ...illustrationResult,
    experiment: null,
  };
});
const hasDoc = computed(() => store.slides.length > 0);
const pageLabel = computed(() => `${store.currentIndex + 1} / ${store.slides.length}`);
const canPrev = computed(() => store.currentIndex > 0);
const canNext = computed(() => store.currentIndex < store.slides.length - 1);
const currentPreviewUrl = computed(() => currentSlide.value?.previewUrl || "");
const currentPageTitle = computed(() => currentSlide.value?.input.topic || `第 ${store.currentIndex + 1} 页`);

function resolveAssetUrl(url?: string) {
  if (!url) return "";
  if (/^(https?:)?\/\//.test(url) || url.startsWith("data:")) return url;
  const base = store.baseUrl.replace(/\/$/, "");
  return url.startsWith("/") ? `${base}${url}` : `${base}/${url}`;
}

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
        page: p.page,
        previewUrl: resolveAssetUrl(p.preview_url),
        thumbnailUrl: resolveAssetUrl(p.thumbnail_url || p.preview_url),
        input: createInputFromPage(p.title || `第 ${p.page} 页`, p.text || ""),
        statusAnalyze: "idle",
        statusIllustration: "idle",
        history: [],
      });
    }
    store.currentIndex = 0;
    functionMode.value = "preview";
    activeWorkflowStep.value = "intent";
    zoomIdx.value = 2;
    uploadMessage.value = "";
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
  store.slides = [];
  store.currentIndex = 0;
  store.docName = "";
  functionMode.value = "preview";
  activeWorkflowStep.value = "intent";
  zoomIdx.value = 2;
  uploadMessage.value = "";
  store.addLog("已清除当前文档，可重新上传");
}

function prevPage() {
  if (canPrev.value) {
    store.currentIndex -= 1;
  }
}

function nextPage() {
  if (canNext.value) {
    store.currentIndex += 1;
  }
}

function goToPage(i: number) {
  if (i < 0 || i >= store.slides.length) return;
  store.currentIndex = i;
}

let readerWheelLock = 0;

function onReaderWheel(e: WheelEvent) {
  if (Math.abs(e.deltaY) < 40) return;
  const now = Date.now();
  if (now - readerWheelLock < 420) return;

  if (e.deltaY > 0 && canNext.value) {
    e.preventDefault();
    nextPage();
    readerWheelLock = now;
  } else if (e.deltaY < 0 && canPrev.value) {
    e.preventDefault();
    prevPage();
    readerWheelLock = now;
  }
}

function selectWorkflowStep(step: WorkflowStep) {
  rightCollapsed.value = false;
  activeWorkflowStep.value = step;
  nextTick(() => ensureColumnWidths());
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
  try {
    const [analyzeResp, illusResp] = await Promise.all([
      analyze(store.baseUrl, slide.input),
      illustration(store.baseUrl, slide.input),
    ]);
    slide.analyze = analyzeResp;
    slide.illustration = illusResp;
    slide.statusAnalyze = "success";
    slide.statusIllustration = "success";
    store.addLog(`第 ${store.currentIndex + 1} 页：图表与配图均已生成`);
  } catch (e: any) {
    slide.statusAnalyze = "error";
    slide.statusIllustration = "error";
    const msg = e?.message || String(e);
    slide.errorAnalyze = msg;
    slide.errorIllustration = msg;
    store.addLog(`生成失败: ${msg}`);
  }
}

const chartBusy = computed(() => currentSlide.value?.statusAnalyze === "loading");
const illusBusy = computed(() => currentSlide.value?.statusIllustration === "loading");
const anyBusy = computed(() => chartBusy.value || illusBusy.value);

function workflowStepStatus(step: WorkflowStep) {
  const slide = currentSlide.value;
  if (!slide) return "未运行";
  if (step === "intent") {
    if (slide.statusAnalyze === "loading") return "运行中";
    if (slide.statusAnalyze === "error") return "失败";
    return slide.analyze?.semantic ? "已完成" : "未运行";
  }
  if (step === "chart") {
    if (slide.statusAnalyze === "loading") return "运行中";
    if (slide.statusAnalyze === "error") return "失败";
    return slide.analyze?.chart ? "已完成" : "未运行";
  }
  if (slide.statusIllustration === "loading") return "运行中";
  if (slide.statusIllustration === "error") return "失败";
  return slide.illustration?.illustration ? "已完成" : "未运行";
}

function workflowStepSummary(step: WorkflowStep) {
  const slide = currentSlide.value;
  if (!slide) return "等待上传文档";
  if (step === "intent") {
    const semantic = slide.analyze?.semantic;
    return semantic?.intent || slide.analyze?.chart?.intent || "判断页面是否需要图表";
  }
  if (step === "chart") {
    const chart = slide.analyze?.chart;
    return chart?.chartType ? `已生成 ${chart.chartType}` : "生成数据图表与可渲染配置";
  }
  const illus = slide.illustration?.illustration;
  return illus ? `keywords: ${illus.keywords.length}` : "生成插图关键词与 Prompt";
}

function workflowStepClass(step: WorkflowStep) {
  const status = workflowStepStatus(step);
  return {
    active: activeWorkflowStep.value === step,
    done: status === "已完成",
    running: status === "运行中",
    error: status === "失败",
  };
}


/** 可拖拽调节左右栏比例（桌面横向分栏时显示分隔条） */
const SPLITTER_PX = 6;
/** 与下方 @media (max-width: 768px) 对齐：≤768 纵向堆叠，不显示拖拽条 */
const SPLIT_LAYOUT_MIN_PX = 769;
const COLLAPSED_WIDTH = 44;
const SIDE_LEFT_MIN = 300;
const SIDE_LEFT_MAX = 420;
const SIDE_RIGHT_MIN = 260;
const SIDE_RIGHT_MAX = 760;
const SIDE_RIGHT_MAX_RATIO = 0.5;
const CENTER_MIN = 360;

const workFullRef = ref<HTMLElement | null>(null);
const windowWidth = ref(typeof window !== "undefined" ? window.innerWidth : 1024);
const leftColumnWidth = ref(0);
const rightColumnWidth = ref(0);
const leftCollapsed = ref(false);
const rightCollapsed = ref(false);
const isSplitDragging = ref(false);
const activeSplitter = ref<"left" | "right" | null>(null);

const splitLayoutHorizontal = computed(() => windowWidth.value >= SPLIT_LAYOUT_MIN_PX);

function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n));
}

function normalizeColumnWidths(width: number, left: number, right: number) {
  const usable = width - SPLITTER_PX * 2;
  if (usable <= 0) return { left: SIDE_LEFT_MIN, right: SIDE_RIGHT_MIN };

  const maxLeft = Math.max(SIDE_LEFT_MIN, Math.min(SIDE_LEFT_MAX, usable - right - CENTER_MIN));
  const nextLeft = clamp(left, SIDE_LEFT_MIN, maxLeft);
  const maxRight = Math.max(
    SIDE_RIGHT_MIN,
    Math.min(SIDE_RIGHT_MAX, usable * SIDE_RIGHT_MAX_RATIO, usable - nextLeft - CENTER_MIN),
  );
  const nextRight = clamp(right, SIDE_RIGHT_MIN, maxRight);
  return { left: nextLeft, right: nextRight };
}

function ensureColumnWidths(force = false) {
  const el = workFullRef.value;
  if (!el || !splitLayoutHorizontal.value) return;
  const width = el.getBoundingClientRect().width;
  const defaultLeft = clamp(width * 0.18, SIDE_LEFT_MIN, SIDE_LEFT_MAX);
  const defaultRight = clamp(width * 0.22, SIDE_RIGHT_MIN, Math.min(SIDE_RIGHT_MAX, width * SIDE_RIGHT_MAX_RATIO));
  const baseLeft = force || leftColumnWidth.value === 0 ? defaultLeft : leftColumnWidth.value;
  const baseRight = force || rightColumnWidth.value === 0 ? defaultRight : rightColumnWidth.value;
  const next = normalizeColumnWidths(width, baseLeft, baseRight);
  leftColumnWidth.value = next.left;
  rightColumnWidth.value = next.right;
}

const workFullStyle = computed(() => {
  if (functionMode.value !== "preview") return {};
  if (!splitLayoutHorizontal.value) {
    return { display: "flex", flexDirection: "column" as const };
  }
  const leftWidth = leftCollapsed.value ? COLLAPSED_WIDTH : leftColumnWidth.value || SIDE_LEFT_MIN;
  const rightWidth = rightCollapsed.value ? COLLAPSED_WIDTH : rightColumnWidth.value || SIDE_RIGHT_MIN;
  const leftSplit = leftCollapsed.value ? 0 : SPLITTER_PX;
  const rightSplit = rightCollapsed.value ? 0 : SPLITTER_PX;
  return {
    display: "grid",
    gridTemplateColumns: `${leftWidth}px ${leftSplit}px minmax(${CENTER_MIN}px, 1fr) ${rightSplit}px ${rightWidth}px`,
    alignItems: "stretch",
  };
});

function updateSplitFromClientX(clientX: number) {
  const el = workFullRef.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const width = rect.width;
  if (activeSplitter.value === "left") {
    const desiredLeft = clientX - rect.left;
    const next = normalizeColumnWidths(width, desiredLeft, rightColumnWidth.value || SIDE_RIGHT_MIN);
    leftColumnWidth.value = next.left;
    rightColumnWidth.value = next.right;
  } else if (activeSplitter.value === "right") {
    const desiredRight = rect.right - clientX;
    const next = normalizeColumnWidths(width, leftColumnWidth.value || SIDE_LEFT_MIN, desiredRight);
    leftColumnWidth.value = next.left;
    rightColumnWidth.value = next.right;
  }
}

function onSplitPointerMove(e: PointerEvent) {
  if (!isSplitDragging.value) return;
  updateSplitFromClientX(e.clientX);
}

function endSplitDrag() {
  if (!isSplitDragging.value) return;
  isSplitDragging.value = false;
  activeSplitter.value = null;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  window.removeEventListener("pointermove", onSplitPointerMove);
  window.removeEventListener("pointerup", endSplitDrag);
  window.removeEventListener("pointercancel", endSplitDrag);
}

function startSplitDrag(e: PointerEvent, side: "left" | "right") {
  if (functionMode.value !== "preview" || !splitLayoutHorizontal.value) return;
  if ((side === "left" && leftCollapsed.value) || (side === "right" && rightCollapsed.value)) return;
  e.preventDefault();
  ensureColumnWidths();
  activeSplitter.value = side;
  isSplitDragging.value = true;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  updateSplitFromClientX(e.clientX);
  window.addEventListener("pointermove", onSplitPointerMove);
  window.addEventListener("pointerup", endSplitDrag);
  window.addEventListener("pointercancel", endSplitDrag);
}

function toggleLeftCollapsed() {
  endSplitDrag();
  leftCollapsed.value = !leftCollapsed.value;
  nextTick(() => ensureColumnWidths());
}

function toggleRightCollapsed() {
  endSplitDrag();
  rightCollapsed.value = !rightCollapsed.value;
  nextTick(() => ensureColumnWidths());
}

function onWindowResize() {
  windowWidth.value = window.innerWidth;
  if (window.innerWidth < SPLIT_LAYOUT_MIN_PX) endSplitDrag();
  nextTick(() => ensureColumnWidths());
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
    nextTick(() => ensureColumnWidths());
  },
);

watch(
  () => hasDoc.value,
  (next) => {
    if (next) nextTick(() => ensureColumnWidths(true));
  },
);

onMounted(() => {
  window.addEventListener("keydown", previewKeydownSplitAware);
  window.addEventListener("resize", onWindowResize);
  nextTick(() => ensureColumnWidths(true));
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
        <aside class="page-control-column" :class="{ collapsed: leftCollapsed }" aria-label="页面控制">
          <button
            type="button"
            class="collapse-toggle collapse-toggle--left"
            :title="leftCollapsed ? '展开页面控制' : '收起页面控制'"
            :aria-label="leftCollapsed ? '展开页面控制' : '收起页面控制'"
            @click="toggleLeftCollapsed"
          >
            {{ leftCollapsed ? '›' : '‹' }}
          </button>
          <div v-if="leftCollapsed" class="collapsed-rail-label">页</div>
          <div v-else class="tools-fixed">
            <div class="tool-block page-control-block">
              <p class="tool-block-title">页面控制</p>
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
            </div>

            <div class="tool-block page-navigation-block">
              <p class="tool-block-title">页面导航</p>
              <div class="page-thumbs" aria-label="页面">
                <button
                  v-for="(s, i) in store.slides"
                  :key="s.id"
                  type="button"
                  class="page-thumb"
                  :class="{ active: i === store.currentIndex }"
                  @click="goToPage(i)"
                >
                  <span class="thumb-index">{{ i + 1 }}</span>
                  <span class="thumb-frame">
                    <img v-if="s.thumbnailUrl" :src="s.thumbnailUrl" :alt="s.input.topic" />
                    <span v-else class="thumb-fallback">{{ s.input.topic || `第 ${i + 1} 页` }}</span>
                  </span>
                  <span class="thumb-title">{{ s.input.topic || `第 ${i + 1} 页` }}</span>
                </button>
              </div>
            </div>
          </div>
        </aside>

        <div
          v-if="splitLayoutHorizontal"
          class="pane-splitter"
          :class="{ dragging: isSplitDragging && activeSplitter === 'left', disabled: leftCollapsed }"
          role="separator"
          aria-orientation="vertical"
          aria-label="拖动调整页面控制和预览宽度"
          title="拖动调整页面控制和预览宽度"
          @pointerdown="startSplitDrag($event, 'left')"
        />
        <!-- 左：WPS 式真实页面预览 -->
        <section class="reader-column" aria-label="文档预览">
          <div class="reader-viewport reader-viewport--solo" @wheel="onReaderWheel">
            <div class="slide-stage" :style="{ transform: `scale(${zoomScale})` }">
              <img v-if="currentPreviewUrl" class="slide-preview-img" :src="currentPreviewUrl" :alt="currentPageTitle" />
              <article v-else class="slide-fallback">
                <h2>{{ currentSlide?.input.topic }}</h2>
                <p>{{ currentSlide?.input.body || "本页暂无可用预览。" }}</p>
              </article>
            </div>
          </div>
        </section>

        <div
          v-if="splitLayoutHorizontal"
          class="pane-splitter"
          :class="{ dragging: isSplitDragging && activeSplitter === 'right', disabled: rightCollapsed }"
          role="separator"
          aria-orientation="vertical"
          aria-label="拖动调节左右栏宽度"
          title="拖动调节左右栏宽度"
          @pointerdown="startSplitDrag($event, 'right')"
        />

        <!-- 右：导航、缩放与全部操作 -->
        <aside class="action-column" :class="{ collapsed: rightCollapsed }">
          <button
            type="button"
            class="collapse-toggle collapse-toggle--right"
            :title="rightCollapsed ? '展开功能面板' : '收起功能面板'"
            :aria-label="rightCollapsed ? '展开功能面板' : '收起功能面板'"
            @click="toggleRightCollapsed"
          >
            {{ rightCollapsed ? '‹' : '›' }}
          </button>
          <div v-if="rightCollapsed" class="collapsed-rail-label">功能</div>
          <template v-else>
          <div class="tools-fixed">
            <div class="tool-block">
              <p class="tool-block-title">页面控制</p>
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
            </div>

            <div class="tool-block">
              <p class="tool-block-title">页面导航</p>
              <div class="page-thumbs" aria-label="页面">
                <button
                  v-for="(s, i) in store.slides"
                  :key="s.id"
                  type="button"
                  class="page-thumb"
                  :class="{ active: i === store.currentIndex }"
                  @click="goToPage(i)"
                >
                  <span class="thumb-index">{{ i + 1 }}</span>
                  <span class="thumb-frame">
                    <img v-if="s.thumbnailUrl" :src="s.thumbnailUrl" :alt="s.input.topic" />
                    <span v-else class="thumb-fallback">{{ s.input.topic || `第 ${i + 1} 页` }}</span>
                  </span>
                  <span class="thumb-title">{{ s.input.topic || `第 ${i + 1} 页` }}</span>
                </button>
              </div>
            </div>
          </div>

          <div class="workflow-head">
            <div>
              <p class="sec-label">三步工作流</p>
              <h2>图表意图 → 数据图表 → 文生图插图</h2>
            </div>
            <button type="button" class="btn solid workflow-auto" :disabled="anyBusy || !currentSlide" @click="generateBoth">
              <span v-if="chartBusy && illusBusy" class="btn-spinner"></span>
              自动生成图表与插图策略
            </button>
          </div>

          <details class="workflow-input">
            <summary>当前页输入</summary>
            <div class="parsed-preview">{{ currentSlide?.input.body || "当前页面暂无解析文本。" }}</div>
            <div v-if="currentSlide?.input.data_description" class="parsed-data">
              <span>结构化数据</span>
              <pre>{{ currentSlide.input.data_description }}</pre>
            </div>
          </details>

          <div class="workflow-steps" aria-label="工作流步骤">
            <button type="button" class="workflow-step" :class="workflowStepClass('intent')" @click="selectWorkflowStep('intent')">
              <span class="step-no">1</span>
              <span class="step-main">
                <b>图表意图</b>
                <small>{{ workflowStepSummary("intent") }}</small>
              </span>
              <span class="step-status">{{ workflowStepStatus("intent") }}</span>
            </button>
            <button type="button" class="workflow-step" :class="workflowStepClass('chart')" @click="selectWorkflowStep('chart')">
              <span class="step-no">2</span>
              <span class="step-main">
                <b>数据图表</b>
                <small>{{ workflowStepSummary("chart") }}</small>
              </span>
              <span class="step-status">{{ workflowStepStatus("chart") }}</span>
            </button>
            <button
              type="button"
              class="workflow-step"
              :class="workflowStepClass('illustration')"
              @click="selectWorkflowStep('illustration')"
            >
              <span class="step-no">3</span>
              <span class="step-main">
                <b>文生图插图</b>
                <small>{{ workflowStepSummary("illustration") }}</small>
              </span>
              <span class="step-status">{{ workflowStepStatus("illustration") }}</span>
            </button>
          </div>

          <div class="tools-scroll workflow-scroll">
            <section v-if="activeWorkflowStep === 'intent'" class="tools-section workflow-panel">
              <div class="workflow-panel-head">
                <span class="fn-title">1. 图表意图</span>
                <button type="button" class="btn ghost compact" :disabled="chartBusy || !currentSlide" @click="generateChartOnly">
                  <span v-if="chartBusy" class="btn-spinner wine-spin"></span>
                  重新分析意图
                </button>
              </div>
              <ChartIntentPanel
                v-if="currentSlide"
                v-model:slide="currentSlide.input"
                :initial-semantic="currentSlide.analyze?.semantic || null"
                :initial-reason="currentSlide.analyze?.chart?.reason || null"
                :initial-chart-type="currentSlide.analyze?.chart?.chartType || null"
              />
            </section>

            <section v-if="activeWorkflowStep === 'chart'" class="tools-section workflow-panel">
              <div class="workflow-panel-head">
                <span class="fn-title">2. 数据图表</span>
                <button type="button" class="btn ghost compact" :disabled="chartBusy || !currentSlide" @click="generateChartOnly">
                  <span v-if="chartBusy" class="btn-spinner wine-spin"></span>
                  重新生成图表
                </button>
              </div>
              <ChartCodePanel
                v-if="currentSlide"
                v-model:slide="currentSlide.input"
                :initial-echarts-option="currentSlide.analyze?.chart?.echartsOption || null"
                :initial-intent="currentSlide.analyze?.chart?.intent || null"
                :initial-chart-type="currentSlide.analyze?.chart?.chartType || null"
                :initial-reason="currentSlide.analyze?.chart?.reason || null"
              />
            </section>

            <section v-if="activeWorkflowStep === 'illustration'" class="tools-section workflow-panel">
              <div class="workflow-panel-head">
                <span class="fn-title">3. 文生图插图</span>
                <button type="button" class="btn ghost compact" :disabled="illusBusy || !currentSlide" @click="generateIllusOnly">
                  <span v-if="illusBusy" class="btn-spinner wine-spin"></span>
                  重新生成插图策略
                </button>
              </div>
              <IllustrationPromptPanel
                v-if="currentSlide"
                v-model:slide="currentSlide.input"
                :initial-result="currentIllustrationResult"
              />
            </section>
          </div>
          </template>
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
  background: var(--color-bg);
  color: var(--color-text);
}

.upload-phase {
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: clamp(24px, 5vw, 56px);
  background: var(--color-bg);
}

.upload-card {
  background: var(--color-surface);
  padding: clamp(28px, 5vw, 48px);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  width: min(860px, 100%);
  text-align: center;
  box-shadow: var(--shadow-card);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
}

.upload-badge {
  display: inline-block;
  margin: 0 0 12px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #ffffff;
  background: var(--color-primary);
  padding: 6px 14px;
  border-radius: 4px;
}

.upload-card h2 {
  margin: 0 0 12px;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
}

.upload-lead {
  margin: 0 0 28px;
  font-size: 14px;
  line-height: 1.65;
  color: var(--color-muted);
}

.drop-zone {
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-card);
  min-height: 240px;
  padding: 40px 24px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color var(--motion-base), background var(--motion-base), transform var(--motion-base), box-shadow var(--motion-base);
}

.drop-zone:hover {
  background: var(--color-primary-soft);
  border-color: var(--color-primary);
  box-shadow: var(--shadow-card);
  transform: translateY(-2px);
}

.hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  color: var(--color-text-soft);
}

.icon {
  font-size: 48px;
}

.loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--color-muted);
  font-size: 14px;
}

.spinner {
  border: 3px solid #eee;
  border-top: 3px solid var(--color-primary);
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
  color: var(--color-primary);
  font-size: 14px;
}

.work-full {
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: row;
  direction: ltr;
  align-items: stretch;
  background: var(--color-bg);
}

/* 预览模式下宽度由 grid + 可拖拽分隔条控制 */
.reader-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: none;
  background: var(--color-bg-muted);
}

.page-control-column,
.action-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  max-height: 100%;
  background: var(--color-surface);
  position: relative;
  overflow: hidden;
}

.page-control-column {
  border-right: 1px solid var(--color-border);
}

.action-column {
  border-left: 1px solid var(--color-border);
}

.action-column > .tools-fixed {
  display: none;
}

.page-control-column:not(.collapsed) .tools-fixed {
  padding: 0 var(--space-3) var(--space-3);
}

.action-column:not(.collapsed) .tools-tabs {
  margin: 0 var(--space-3) var(--space-3);
}

.page-control-column.collapsed,
.action-column.collapsed {
  align-items: center;
  justify-content: flex-start;
  padding-top: 12px;
  background: var(--color-surface);
}

.collapse-toggle {
  position: relative;
  z-index: 5;
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  min-height: 38px;
  margin: 12px;
  border-radius: var(--radius-control);
  border: 1px solid var(--color-primary-border);
  background: var(--color-surface);
  color: var(--color-primary);
  font-size: 20px;
  font-weight: 800;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 20px rgba(139, 41, 66, 0.08);
  transition: background var(--motion-base), color var(--motion-base), transform var(--motion-base), border-color var(--motion-base);
}

.collapse-toggle:hover {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
  transform: translateY(-1px);
}

.collapse-toggle--left {
  align-self: flex-end;
}

.collapse-toggle--right {
  align-self: flex-start;
}

.collapsed .collapse-toggle {
  align-self: center;
  margin: 10px 0 12px;
}

.collapsed-rail-label {
  margin-top: 0;
  writing-mode: vertical-rl;
  letter-spacing: 0.14em;
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 800;
  line-height: 1.2;
}

.page-control-column.collapsed .collapsed-rail-label {
  font-size: 0;
}

.page-control-column.collapsed .collapsed-rail-label::after {
  content: "页面控制";
  font-size: 12px;
}

.action-column.collapsed .collapsed-rail-label {
  font-size: 0;
}

.action-column.collapsed .collapsed-rail-label::after {
  content: "功能区";
  font-size: 12px;
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
  transition: background var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease);
}

.pane-splitter:hover,
.pane-splitter.dragging {
  background: var(--color-primary);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2), 0 0 18px rgba(139, 41, 66, 0.25);
}

.pane-splitter.dragging {
  cursor: col-resize;
}

.pane-splitter.disabled {
  pointer-events: none;
  opacity: 0;
  margin: 0;
}

.pane-tabs {
  display: flex;
  gap: var(--space-2);
  padding: 4px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-muted);
  border-radius: var(--radius-card);
}

.pane-tab {
  min-height: var(--control-md);
  flex: 1;
  padding: 0 14px;
  border: none;
  border-radius: var(--radius-control);
  background: transparent;
  font-size: 13px;
  font-weight: 800;
  color: var(--color-muted-light);
  cursor: pointer;
  transition: color var(--motion-base), background var(--motion-base), box-shadow var(--motion-base), transform var(--motion-base);
}

.pane-tab:hover {
  color: var(--color-muted);
}

.pane-tab.active {
  background: var(--color-surface);
  color: var(--color-primary);
  box-shadow: var(--shadow-card);
}

.tools-tabs {
  background: var(--color-bg);
}

.doc-view-tabs {
  background: var(--color-bg-muted);
}

.tools-fixed {
  flex: 1 1 0;
  height: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--color-surface);
  overflow-y: hidden;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.tools-fixed::-webkit-scrollbar {
  width: 10px;
}

.tools-fixed::-webkit-scrollbar-track {
  background: var(--color-bg-muted);
  border-left: 1px solid var(--color-border);
}

.tools-fixed::-webkit-scrollbar-thumb {
  background: rgba(139, 41, 66, 0.38);
  border: 2px solid var(--color-bg-muted);
  border-radius: 999px;
}

.tools-fixed::-webkit-scrollbar-thumb:hover {
  background: rgba(139, 41, 66, 0.58);
}

.tool-block {
  flex: 0 0 auto;
  padding: var(--space-3);
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: 0 3px 14px rgba(139, 41, 66, 0.04);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
  overflow: hidden;
}

.page-control-block {
  overflow: visible;
}

.page-navigation-block {
  flex: 1 1 0;
  min-height: 180px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tool-block:nth-child(2) {
  animation-delay: 40ms;
}

.tool-block:nth-child(3) {
  animation-delay: 80ms;
}

.tool-block-title {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-muted);
}

.preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-3);
  min-width: 0;
}

.page-control-column .preview-toolbar {
  align-items: stretch;
}

.tb-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1 1 100%;
}

.tb-doc {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.tb-status {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-muted);
}

.tb-center {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 100%;
  min-width: 0;
}

.tb-page {
  flex: 1 1 auto;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-soft);
  min-width: 0;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.tb-icon {
  width: var(--control-sm);
  height: var(--control-sm);
  min-height: var(--control-sm);
  border-radius: var(--radius-control);
  border: 1px solid var(--color-primary-border);
  background: var(--color-surface);
  color: #2d2d2d;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

.tb-icon:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
  transform: translateY(-1px);
}

.tb-icon:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.tb-zoom {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1 1 auto;
  min-width: 0;
}

.tb-zoom-btn {
  width: var(--control-sm);
  height: var(--control-sm);
  min-height: var(--control-sm);
  border-radius: var(--radius-control);
  border: 1px solid var(--color-primary-border);
  background: var(--color-surface);
  font-size: 16px;
  font-weight: 600;
  color: #2d2d2d;
  cursor: pointer;
  line-height: 1;
}

.tb-zoom-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
  transform: translateY(-1px);
}

.tb-zoom-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.tb-zoom-val {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-muted);
  min-width: 44px;
  text-align: center;
}

.tb-replace {
  display: inline-flex;
  align-items: center;
  flex: 1 1 100%;
  min-height: var(--control-sm);
  padding: 0 12px;
  border-radius: var(--radius-control);
  border: 1px solid var(--color-primary-border);
  background: var(--color-surface);
  color: var(--color-text-soft);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  justify-content: center;
}

.tb-replace:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  transform: translateY(-1px);
}

.reader-viewport {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: clamp(20px, 4vw, 56px);
  background: var(--color-bg-muted);
  display: flex;
  justify-content: center;
  align-items: flex-start;
}

.reader-viewport--solo {
  flex: 1;
  min-height: 0;
}

.slide-stage {
  transform-origin: top center;
  transition: transform var(--motion-base) var(--motion-ease);
  margin-bottom: var(--space-6);
  width: min(1080px, 100%);
  min-height: 320px;
  display: flex;
  justify-content: center;
}

.slide-preview-img {
  display: block;
  max-width: 100%;
  height: auto;
  background: var(--color-surface);
  border: 1px solid #d8d1d4;
  border-radius: 4px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
}

.slide-fallback {
  width: min(960px, 100%);
  min-height: 540px;
  padding: clamp(32px, 5vw, 64px);
  background: var(--color-surface);
  border: 1px solid #d8d1d4;
  border-radius: 4px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
}

.slide-fallback h2 {
  margin: 0 0 var(--space-5);
  font-size: clamp(28px, 4vw, 48px);
  color: var(--color-text);
}

.slide-fallback p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.8;
  color: var(--color-text-soft);
}

.page-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: 0;
  border: none;
  background: transparent;
  max-height: 120px;
  overflow-y: auto;
}

.page-chip {
  min-width: var(--control-sm);
  min-height: var(--control-sm);
  padding: 0 10px;
  border-radius: var(--radius-control);
  border: 1px solid var(--color-primary-border);
  background: var(--color-surface);
  font-size: 12px;
  font-weight: 600;
  color: var(--color-muted);
  cursor: pointer;
}

.page-chip:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  transform: translateY(-1px);
}

.page-chip.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #ffffff;
}

.page-thumbs {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  overflow-y: scroll;
  overflow-x: hidden;
  padding-right: 4px;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.page-thumbs::-webkit-scrollbar {
  width: 10px;
}

.page-thumbs::-webkit-scrollbar-track {
  background: var(--color-bg-muted);
  border-left: 1px solid var(--color-border);
  border-radius: 999px;
}

.page-thumbs::-webkit-scrollbar-thumb {
  background: rgba(139, 41, 66, 0.38);
  border: 2px solid var(--color-bg-muted);
  border-radius: 999px;
}

.page-thumbs::-webkit-scrollbar-thumb:hover {
  background: rgba(139, 41, 66, 0.58);
}

.page-thumb {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 100%;
  min-height: 150px;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  color: var(--color-text-soft);
  cursor: pointer;
  text-align: left;
  transition: transform var(--motion-base), border-color var(--motion-base), box-shadow var(--motion-base), background var(--motion-base);
}

.page-thumb:hover {
  transform: translateY(-1px);
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-card);
}

.page-thumb.active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  box-shadow: 0 0 0 3px rgba(139, 41, 66, 0.12);
}

.thumb-index {
  position: absolute;
  left: var(--space-3);
  top: var(--space-3);
  z-index: 1;
  min-width: 28px;
  height: 28px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(255, 250, 251, 0.92);
  border: 1px solid rgba(139, 41, 66, 0.18);
  font-size: 14px;
  font-weight: 800;
  color: var(--color-primary);
  text-align: center;
  line-height: 26px;
}

.thumb-frame {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 112px;
  aspect-ratio: 16 / 10;
  overflow: hidden;
  border: 1px solid #d8d1d4;
  border-radius: 4px;
  background: var(--color-bg-muted);
}

.thumb-frame img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #fff;
}

.thumb-fallback {
  padding: 6px;
  font-size: 10px;
  line-height: 1.3;
  color: var(--color-muted);
}

.thumb-title {
  min-width: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.4;
  padding-left: 0;
}

.tools-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--space-4) var(--space-4) var(--space-6);
}

.tools-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
}

.workflow-head {
  flex: 0 0 auto;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 0 var(--space-4) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.workflow-head h2 {
  margin: 4px 0 0;
  font-size: 15px;
  font-weight: 900;
  color: var(--color-text);
  line-height: 1.35;
}

.workflow-auto {
  flex: 0 0 auto;
  max-width: 220px;
  justify-content: center;
}

.workflow-input {
  flex: 0 0 auto;
  margin: var(--space-3) var(--space-4) 0;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-bg);
}

.workflow-input summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
  color: var(--color-muted);
}

.workflow-input[open] summary {
  margin-bottom: var(--space-3);
}

.workflow-steps {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.workflow-step {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: auto auto;
  gap: 4px 8px;
  align-items: center;
  padding: 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  color: var(--color-text-soft);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--motion-base), background var(--motion-base), box-shadow var(--motion-base), transform var(--motion-base);
}

.workflow-step:hover {
  border-color: var(--color-primary-border);
  transform: translateY(-1px);
}

.workflow-step.active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  box-shadow: 0 0 0 3px rgba(139, 41, 66, 0.1);
}

.workflow-step.done .step-status {
  color: var(--color-primary);
}

.workflow-step.running .step-status {
  color: var(--color-warning);
}

.workflow-step.error .step-status {
  color: var(--color-danger);
}

.step-no {
  grid-row: 1 / span 2;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 900;
}

.step-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-main b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--color-text);
}

.step-main small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  color: var(--color-muted);
}

.step-status {
  grid-column: 2;
  font-size: 10px;
  font-weight: 800;
  color: var(--color-muted-light);
}

.workflow-scroll {
  padding-top: var(--space-4);
}

.workflow-panel {
  gap: var(--space-4);
}

.workflow-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.btn.compact {
  min-height: var(--control-sm);
  padding: 0 10px;
  white-space: nowrap;
}

.side-function {
  gap: var(--space-4);
}

.side-function-head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.side-back {
  flex-shrink: 0;
}

.sec-label {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-muted);
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
  padding: var(--space-3);
  border-radius: var(--radius-control);
  border: 1px solid #e0d8db;
  background: var(--color-bg);
  font-size: 13px;
  line-height: 1.45;
  color: #2d2d2d;
}

.btn-use {
  align-self: flex-start;
  min-height: var(--control-md);
  padding: 0 16px;
  border-radius: var(--radius-control);
  border: 1px solid var(--color-primary);
  background: var(--color-surface);
  color: var(--color-primary);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}

.btn-use:hover:not(:disabled) {
  background: var(--color-primary);
  color: #ffffff;
  transform: translateY(-2px);
  box-shadow: var(--shadow-card);
}

.parsed-preview {
  max-height: 150px;
  overflow: auto;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  color: var(--color-text-soft);
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.6;
}

.parsed-data {
  padding: var(--space-3);
  border: 1px dashed var(--color-primary-border);
  border-radius: var(--radius-card);
  background: var(--color-primary-soft);
}

.parsed-data span {
  display: block;
  margin-bottom: var(--space-2);
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 800;
}

.parsed-data pre {
  margin: 0;
  white-space: pre-wrap;
  font-size: 12px;
  color: var(--color-text-soft);
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
  min-height: var(--control-lg);
  padding: 0 14px;
  border-radius: var(--radius-control);
  border: 1px solid var(--color-primary);
  background: var(--color-surface);
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--motion-base), color var(--motion-base), transform var(--motion-base), box-shadow var(--motion-base);
}

.jump:hover {
  background: var(--color-primary);
  color: #ffffff;
  transform: translateY(-2px);
  box-shadow: var(--shadow-card);
}

.gen-section .pipeline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.btn {
  min-height: var(--control-md);
  padding: 0 12px;
  border-radius: var(--radius-control);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn.ghost {
  border: 1px solid var(--color-border-strong);
  background: var(--color-surface);
  color: #4a4a4a;
}

.btn.ghost:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
  transform: translateY(-1px);
}

.btn.solid {
  border: 1px solid var(--color-primary);
  background: var(--color-primary);
  color: #ffffff;
}

.btn.solid:hover:not(:disabled) {
  filter: brightness(1.05);
  transform: translateY(-1px);
  box-shadow: var(--shadow-card);
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
  color: var(--color-muted-light);
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
  border-top-color: var(--color-primary);
}

.function-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}

.fn-toolbar {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}

.fn-back {
  min-height: var(--control-md);
  padding: 0 14px;
  border-radius: var(--radius-control);
  border: 1px solid var(--color-primary-border);
  background: var(--color-surface);
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-soft);
  cursor: pointer;
}

.fn-back:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  transform: translateY(-1px);
}

.fn-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text);
}

.fn-meta {
  margin-left: auto;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-muted);
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
    order: 1;
    flex: 1 1 auto;
    border-right: none;
    border-bottom: 1px solid var(--color-border);
    min-height: 48vh;
    max-height: 56vh;
  }

  .page-control-column,
  .action-column {
    flex: 1 1 auto;
    min-width: 0;
    max-width: none;
    width: 100%;
    max-height: none;
  }

  .page-control-column.collapsed,
  .action-column.collapsed {
    min-height: 44px;
    width: 100%;
    padding: 8px 12px;
    align-items: flex-start;
  }

  .collapsed .collapse-toggle {
    position: static;
    transform: none;
  }

  .collapsed-rail-label {
    writing-mode: horizontal-tb;
    margin-top: 8px;
  }

  .page-control-column {
    order: 2;
    border-right: none;
    border-bottom: 1px solid var(--color-border);
  }

  .action-column {
    order: 3;
    border-left: none;
  }

  .pane-splitter {
    display: none;
  }

  .tools-fixed {
    max-height: 42vh;
  }

  .preview-toolbar {
    justify-content: flex-start;
  }

  .page-chips {
    max-height: 88px;
  }
}
</style>
