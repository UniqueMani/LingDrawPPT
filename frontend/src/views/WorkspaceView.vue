<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { store } from "../store";
import {
  analyzeDocumentConsistency,
  extractText,
  fluxGenerateImage,
  getFileDetail,
  ocrRegion,
  vizLabChartCode,
  vizLabIntent,
} from "../api/client";
import ChartIntentPanel from "../components/ChartIntentPanel.vue";
import ChartCodePanel from "../components/ChartCodePanel.vue";
import IllustrationPromptPanel from "../components/IllustrationPromptPanel.vue";
import {
  beginFluxJob,
  clearFluxRuntimeState,
  completeFluxJob,
  createFluxRequestKey,
  failFluxJob,
} from "../utils/fluxJobManager";
import type {
  FluxGenerateImagePayload,
  FileRecord,
  SlideRequest,
  TextBlock,
  VizLabChartCodeResponse,
} from "../types";

type FunctionMode = "preview" | "intent" | "code" | "illustration";
type WorkflowStep = "intent" | "chart" | "illustration";

const functionMode = ref<FunctionMode>("preview");
const router = useRouter();
const fileInput = ref<HTMLInputElement | null>(null);
const uploadLoading = ref(false);
const uploadMessage = ref("");
const openingRecentId = ref<number | null>(null);
const recentMessage = ref("");
const illustrationPanelRef = ref<{ runFluxGenerate: () => Promise<void> | void } | null>(null);
const workflowRunningStep = ref<WorkflowStep | null>(null);
const workflowErrorStep = ref<WorkflowStep | null>(null);
const fullWorkflowBusy = ref(false);

const zoomPercent = ref(100);
const zoomScale = computed(() => zoomPercent.value / 100);

function normalizeZoom(value: number) {
  if (!Number.isFinite(value)) return 100;
  return Math.min(200, Math.max(50, Math.round(value)));
}

function setZoom(value: number | string) {
  zoomPercent.value = normalizeZoom(Number(value));
}

function onZoomInput(event: Event) {
  setZoom((event.target as HTMLInputElement).value);
}

/** 右侧三步工作流状态 */
const activeWorkflowStep = ref<WorkflowStep>("intent");

const currentSlide = computed(() => store.slides[store.currentIndex] ?? null);
const currentPreviewUrl = computed(() => currentSlide.value?.previewUrl);
const hasDoc = computed(() => store.slides.length > 0);
const pageLabel = computed(() => `${store.currentIndex + 1} / ${store.slides.length}`);
const canPrev = computed(() => store.currentIndex > 0);
const canNext = computed(() => store.currentIndex < store.slides.length - 1);
const recentFiles = computed(() =>
  store.files
    .filter((file) => file.parse_status === "success")
    .slice()
    .sort((a, b) => new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime())
    .slice(0, 4)
);
const functionModeTitle = computed(() => {
  if (functionMode.value === "intent") return "图表意图";
  if (functionMode.value === "code") return "图表代码";
  if (functionMode.value === "illustration") return "文生图配图";
  return "文档预览";
});

function runIllustrationImage() {
  illustrationPanelRef.value?.runFluxGenerate();
}

function clearCurrentWorkspace() {
  clearFluxRuntimeState(store.fluxJobs, store.slides);
  store.slides = [];
  store.currentIndex = 0;
  store.docName = "";
  store.currentFileId = 0;
  store.docConsistency = null;
  functionMode.value = "preview";
  activeWorkflowStep.value = "intent";
  zoomPercent.value = 100;
  uploadMessage.value = "";
  leftHoverMode.value = false;
  leftHoverOpen.value = false;
  leftPinned.value = false;
}

function exitEditor() {
  const saved = store.saveCurrentWorkspaceDraft();
  store.addLog(saved ? "已保存当前工作台编辑草稿" : "当前工作台没有可保存的文件草稿");
  regionSelectionEnabled.value = false;
  clearRegionSelection();
  clearCurrentWorkspace();
  router.push("/home");
}

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
    store.currentFileId = resp.file_id || 0;
    clearFluxRuntimeState(store.fluxJobs, store.slides);
    store.slides = [];

    const pages =
      resp.pages_detail.length > 0
        ? resp.pages_detail
        : [{ page: 1, title: resp.title || "第 1 页", text: resp.text, text_blocks: [] }];

    for (const p of pages) {
      store.slides.push({
        id: `${newId()}_${p.page}`,
        page: p.page,
        previewUrl: resolveAssetUrl(p.preview_url),
        thumbnailUrl: resolveAssetUrl(p.thumbnail_url || p.preview_url),
        sourceTitle: p.title || `第 ${p.page} 页`,
        sourceText: p.text || "",
        textBlocks: p.text_blocks || [],
        sourceDataDescription: "",
        input: createInputFromPage(p.title || `第 ${p.page} 页`, p.text || ""),
        statusAnalyze: "idle",
        statusIllustration: "idle",
        statusFluxImage: "idle",
        history: [],
      });
    }
    store.currentIndex = 0;
    store.docConsistency = null;
    try {
      store.docConsistency = await analyzeDocumentConsistency(store.baseUrl, {
        doc_title: resp.title || resp.filename,
        pages: store.slides.map((s) => ({
          page: s.page,
          topic: s.input.topic,
          body: s.input.body || s.sourceText || "",
        })),
      });
      store.addLog(`文档级风格分析完成：${store.docConsistency.summary}`);
    } catch (e: any) {
      store.addLog(`文档风格分析跳过: ${e?.message || e}`);
    }
    functionMode.value = "preview";
    activeWorkflowStep.value = "intent";
    zoomPercent.value = 100;
    leftCollapsed.value = false;
    leftHoverMode.value = true;
    leftHoverOpen.value = false;
    leftPinned.value = false;
    uploadMessage.value = "";
    store.addLog(`成功上传并解析文件：${resp.filename}，共 ${store.slides.length} 页`);
    store.fetchFiles();
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

async function openRecentFile(file: FileRecord) {
  openingRecentId.value = file.id;
  recentMessage.value = "";
  try {
    const detail = await getFileDetail(store.baseUrl, file.id);
    const pages = detail.pages_detail.length
      ? detail.pages_detail
      : [{ page: 1, title: detail.original_filename, text: detail.extracted_text, text_blocks: [] }];
    store.docName = detail.original_filename;
    store.currentFileId = detail.id;
    store.docConsistency = null;
    store.slides = pages.map((page) => ({
      id: `${newId()}_${page.page}`,
      page: page.page,
      previewUrl: resolveAssetUrl(page.preview_url),
      thumbnailUrl: resolveAssetUrl(page.thumbnail_url || page.preview_url),
      sourceTitle: page.title || `第 ${page.page} 页`,
      sourceText: page.text || "",
      textBlocks: page.text_blocks || [],
      sourceDataDescription: "",
      input: createInputFromPage(page.title || `第 ${page.page} 页`, page.text || ""),
      statusAnalyze: "idle",
      statusIllustration: "idle",
      statusFluxImage: "idle",
      history: [],
    }));
    const restored = store.restoreWorkspaceDraft(detail.id);
    leftHoverMode.value = true;
    leftCollapsed.value = false;
    leftHoverOpen.value = false;
    leftPinned.value = false;
    functionMode.value = "preview";
    activeWorkflowStep.value = "intent";
    zoomPercent.value = 100;
    store.addLog(
      restored
        ? `从最近文件恢复编辑草稿: ${detail.original_filename}`
        : `从最近文件打开: ${detail.original_filename}`
    );
    nextTick(() => {
      ensureColumnWidths(true);
      setupFlowObserver();
      scrollCurrentThumbIntoView();
    });
  } catch (error: any) {
    recentMessage.value = error?.message || String(error);
  } finally {
    openingRecentId.value = null;
  }
}

function resetDocument() {
  if (!hasDoc.value) return;
  if (!window.confirm("确定要更换文件吗？当前所有已生成结果将被清除，此操作不可撤销。")) return;
  clearCurrentWorkspace();
  store.addLog("当前文档已清除，可重新上传");
}

function prevPage() {
  if (canPrev.value) {
    store.currentIndex -= 1;
    scrollToSlide(store.currentIndex);
  }
}

function nextPage() {
  if (canNext.value) {
    store.currentIndex += 1;
    scrollToSlide(store.currentIndex);
  }
}

function goToPage(i: number) {
  if (i < 0 || i >= store.slides.length) return;
  store.currentIndex = i;
  scrollToSlide(i);
}

/** 滚动到指定页面（连续阅读模式下平滑滚动） */
function scrollToSlide(i: number) {
  const el = slideRefs.value[i];
  if (el && slidesViewportRef.value) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function setPageThumbRef(el: any, i: number) {
  pageThumbRefs.value[i] = el as HTMLElement | null;
}

function scrollCurrentThumbIntoView() {
  pageThumbRefs.value[store.currentIndex]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

type RegionRect = { x: number; y: number; width: number; height: number };
type RegionPoint = { x: number; y: number };

function toggleRegionSelection() {
  regionSelectionEnabled.value = !regionSelectionEnabled.value;
  clearRegionSelection();
  textPickerValue.value = "";
}

function closeTextPicker() {
  textPickerOpen.value = false;
  regionLoading.value = false;
}

function clearRegionSelection(closeDialog = true) {
  regionDragging.value = false;
  regionStart.value = null;
  regionDraft.value = null;
  regionSlideIndex.value = null;
  regionError.value = "";
  if (closeDialog) closeTextPicker();
}

function pointInOverlay(e: PointerEvent): RegionPoint {
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
  return {
    x: clamp((e.clientX - rect.left) / rect.width, 0, 1),
    y: clamp((e.clientY - rect.top) / rect.height, 0, 1),
  };
}

function rectFromPoints(start: RegionPoint, end: RegionPoint): RegionRect {
  return {
    x: Math.min(start.x, end.x),
    y: Math.min(start.y, end.y),
    width: Math.abs(end.x - start.x),
    height: Math.abs(end.y - start.y),
  };
}

function startRegionSelection(e: PointerEvent, slideIndex: number) {
  if (!regionSelectionEnabled.value || slideIndex !== store.currentIndex) return;
  const overlay = e.currentTarget as HTMLElement;
  overlay.setPointerCapture(e.pointerId);
  regionStart.value = pointInOverlay(e);
  regionDraft.value = { x: regionStart.value.x, y: regionStart.value.y, width: 0, height: 0 };
  regionSlideIndex.value = slideIndex;
  regionDragging.value = true;
  textPickerOpen.value = false;
  textPickerValue.value = "";
  regionError.value = "";
}

function moveRegionSelection(e: PointerEvent) {
  if (!regionDragging.value || !regionStart.value) return;
  regionDraft.value = rectFromPoints(regionStart.value, pointInOverlay(e));
}

function blocksInRegion(blocks: TextBlock[], region: RegionRect) {
  return blocks
    .filter((block) => {
      const right = Math.min(block.x + block.width, region.x + region.width);
      const bottom = Math.min(block.y + block.height, region.y + region.height);
      return right > Math.max(block.x, region.x) && bottom > Math.max(block.y, region.y);
    })
    .sort((a, b) => (Math.abs(a.y - b.y) > 0.015 ? a.y - b.y : a.x - b.x))
    .map((block) => block.text.trim())
    .filter(Boolean)
    .join("\n");
}

async function runOcrForRegion() {
  const slide = currentSlide.value;
  const region = regionDraft.value;
  if (!slide?.previewUrl || !region) {
    regionError.value = "当前页没有可用于 OCR 的预览图片。";
    return;
  }
  regionLoading.value = true;
  regionError.value = "";
  textPickerValue.value = "";
  textPickerOpen.value = true;
  try {
    const result = await ocrRegion(store.baseUrl, {
      preview_url: new URL(slide.previewUrl, window.location.origin).pathname,
      ...region,
    });
    textPickerValue.value = result.text;
    if (!result.text.trim()) regionError.value = "未识别到文字，请调整框选区域后重试。";
  } catch (e: any) {
    regionError.value = e?.message || "OCR 识别失败";
  } finally {
    regionLoading.value = false;
    nextTick(() => textPickerRef.value?.focus());
  }
}

async function finishRegionSelection(e: PointerEvent) {
  if (!regionDragging.value || !regionDraft.value) return;
  regionDragging.value = false;
  (e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
  if (regionDraft.value.width < 0.01 || regionDraft.value.height < 0.01) {
    regionError.value = "框选区域过小，请重新拖拽。";
    return;
  }
  const nativeText = blocksInRegion(currentSlide.value?.textBlocks || [], regionDraft.value);
  if (nativeText) {
    textPickerValue.value = nativeText;
    textPickerOpen.value = true;
    nextTick(() => textPickerRef.value?.focus());
    return;
  }
  await runOcrForRegion();
}

function applySelectedText() {
  const slide = currentSlide.value;
  if (!slide) return;
  slide.input.body = textPickerValue.value.trim();
  regionSelectionEnabled.value = false;
  clearRegionSelection();
}

function restoreCurrentSlideSourceText() {
  const slide = currentSlide.value;
  if (!slide) return;
  slide.input.topic = slide.sourceTitle || slide.input.topic;
  slide.input.body = slide.sourceText || "";
  slide.input.data_description = slide.sourceDataDescription || "";
}

function selectModule(step: WorkflowStep) {
  rightCollapsed.value = false;
  restoreCurrentSlideSourceText();
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
    sl.statusAnalyze === "success" ? "chart-ok" : sl.statusAnalyze === "loading" ? "chart-loading" : "chart-idle";
  const i =
    sl.statusIllustration === "success"
      ? "image-ok"
      : sl.statusIllustration === "loading"
        ? "image-loading"
        : "image-idle";
  return c + " / " + i;
}

async function generateChartOnly() {
  await runChartCodeOnly();
}

async function runIntentOnly() {
  const slide = currentSlide.value;
  if (!slide) return;
  workflowRunningStep.value = "intent";
  workflowErrorStep.value = null;
  slide.statusAnalyze = "loading";
  slide.errorAnalyze = undefined;
  try {
    const result = await vizLabIntent(store.baseUrl, slide.input);
    slide.intentSemantic = result.semantic;
    slide.statusAnalyze = "success";
    store.addLog(`第 ${store.currentIndex + 1} 页：已完成意图分析`);
  } catch (e: any) {
    slide.statusAnalyze = "error";
    slide.errorAnalyze = e?.message || String(e);
    workflowErrorStep.value = "intent";
    store.addLog(`意图分析失败：${slide.errorAnalyze}`);
    throw e;
  } finally {
    workflowRunningStep.value = null;
  }
}

async function runChartCodeOnly() {
  const slide = currentSlide.value;
  if (!slide) return;
  workflowRunningStep.value = "chart";
  workflowErrorStep.value = null;
  slide.statusAnalyze = "loading";
  slide.errorAnalyze = undefined;
  try {
    const result = await vizLabChartCode(store.baseUrl, {
      slide: slide.input,
      targets: ["echarts", "chartjs", "mermaid"],
      instructions:
        "三套图表结果保持数据一致；柱状/折线需要坐标轴；饼图切片命名不重复；Mermaid 使用合法 pie / xychart-beta / flowchart 语法。",
    });
    slide.chartCode = result;
    slide.statusAnalyze = "success";
    store.addLog(`第 ${store.currentIndex + 1} 页：已生成图表代码`);
  } catch (e: any) {
    slide.statusAnalyze = "error";
    slide.errorAnalyze = e?.message || String(e);
    workflowErrorStep.value = "chart";
    store.addLog(`图表生成失败：${slide.errorAnalyze}`);
    throw e;
  } finally {
    workflowRunningStep.value = null;
  }
}

const chartBusy = computed(() => currentSlide.value?.statusAnalyze === "loading");
const workflowBusy = computed(() => chartBusy.value || currentSlide.value?.statusFluxImage === "loading" || fullWorkflowBusy.value);

function onIntentPanelResult(semantic: Record<string, any>) {
  const slide = currentSlide.value;
  if (!slide) return;
  slide.intentSemantic = semantic;
  slide.statusAnalyze = "success";
  slide.errorAnalyze = undefined;
}

function onChartCodeResult(result: VizLabChartCodeResponse) {
  const slide = currentSlide.value;
  if (!slide) return;
  slide.chartCode = result;
  slide.statusAnalyze = "success";
  slide.errorAnalyze = undefined;
}

function onFluxGenerateRequest(payload: FluxGenerateImagePayload) {
  const slide = currentSlide.value;
  if (!slide) return;
  void startFluxImageJob(slide.id, payload);
}

async function startFluxImageJob(slideId: string, payload: FluxGenerateImagePayload) {
  const targetSlide = store.slides.find((s) => s.id === slideId);
  if (!targetSlide) return;

  const requestKey = createFluxRequestKey(slideId);
  beginFluxJob(store.fluxJobs, targetSlide, requestKey);
  const modeLabel = payload.generation_mode === "fast" ? "极速模式" : "通用模式";
  store.addLog(`第 ${targetSlide.page} 页：文生图生成已开始（${modeLabel}）`);

  try {
    const result = await fluxGenerateImage(store.baseUrl, payload);
    const applied = completeFluxJob(store.fluxJobs, store.slides, slideId, requestKey, result);
    if (!applied) return;

    const score = result.evaluation?.totalScore;
    const pass = result.evaluation?.passed;
    const extra = score != null ? `（质量 ${score.toFixed(0)}，${pass ? "通过" : "未达标"}）` : "";
    const completedSlide = store.slides.find((s) => s.id === slideId);
    const page = completedSlide?.page ?? targetSlide.page;
    if (result.attemptsLog?.length && result.attempts && result.attempts > 1) {
      for (const entry of result.attemptsLog) {
        const textFidelity = entry.evaluation?.dimensions?.find((d) => d.key === "text_fidelity")?.score;
        store.addLog(
          `第 ${page} 页 · 候选 ${entry.attempt}：综合 ${entry.evaluation?.totalScore?.toFixed(0) ?? "-"} 分，文字真实性 ${textFidelity?.toFixed(0) ?? "-"} 分`
        );
      }
      if (result.selectedAttempt) {
        store.addLog(`第 ${page} 页 · 选用候选 ${result.selectedAttempt}${extra}`);
      }
    } else {
      store.addLog(`第 ${page} 页：文生图已生成${extra}`);
    }
  } catch (e: any) {
    const message = e?.message || String(e);
    const applied = failFluxJob(store.fluxJobs, store.slides, slideId, requestKey, message);
    if (!applied) return;
    const failedSlide = store.slides.find((s) => s.id === slideId);
    store.addLog(`第 ${failedSlide?.page ?? targetSlide.page} 页：文生图生成失败：${message}`);
  }
}

async function runFullWorkflow() {
  const slide = currentSlide.value;
  if (!slide || fullWorkflowBusy.value) return;
  fullWorkflowBusy.value = true;
  workflowErrorStep.value = null;
  try {
    await runIntentOnly();
    await runChartCodeOnly();
    activeWorkflowStep.value = "illustration";
    await nextTick();
    await nextTick();
    runIllustrationImage();
    store.addLog(`第 ${store.currentIndex + 1} 页：全流程已启动，正在等待文生图结果`);
  } catch {
    store.addLog(`第 ${store.currentIndex + 1} 页：全流程已停止，请先处理当前步骤错误`);
  } finally {
    fullWorkflowBusy.value = false;
  }
}

function workflowStepStatus(step: WorkflowStep) {
  const slide = currentSlide.value;
  if (!slide) return "未运行";
  if (step === "intent") {
    if (workflowRunningStep.value === "intent") return "运行中";
    if (workflowErrorStep.value === "intent") return "失败";
    return slide.intentSemantic || slide.analyze?.semantic ? "已完成" : "未运行";
  }
  if (step === "chart") {
    if (workflowRunningStep.value === "chart") return "运行中";
    if (workflowErrorStep.value === "chart") return "失败";
    return slide.chartCode || slide.analyze?.chart ? "已完成" : "未运行";
  }
  if (slide.statusFluxImage === "loading") return "生成评估中";
  if (slide.statusFluxImage === "error") return "失败";
  return slide.fluxImage ? "已完成" : "未运行";
}

function workflowStepClass(step: WorkflowStep) {
  const status = workflowStepStatus(step);
  return {
    active: activeWorkflowStep.value === step,
    done: status === "已完成",
    running: status === "运行中" || status === "生成评估中",
    error: status === "失败",
  };
}


/** 可拖拽调节左右栏比例（桌面横向分栏时显示分隔条） */
const SPLITTER_PX = 6;
/** 与下方 @media (max-width: 768px) 对齐：窄屏纵向堆叠，不显示拖拽条 */
const SPLIT_LAYOUT_MIN_PX = 769;
const COLLAPSED_WIDTH = 34;
const SIDE_LEFT_MIN = 300;
const SIDE_LEFT_MAX = 420;
const SIDE_RIGHT_MIN = 300;
const SIDE_RIGHT_MAX = 880;
const SIDE_RIGHT_MAX_RATIO = 0.52;
const CENTER_MIN = 360;

const workFullRef = ref<HTMLElement | null>(null);
const slidesViewportRef = ref<HTMLElement | null>(null);
const slideRefs = ref<(HTMLElement | null)[]>([]);
const pageThumbRefs = ref<(HTMLElement | null)[]>([]);
const textPickerOpen = ref(false);
const textPickerValue = ref("");
const textPickerRef = ref<HTMLTextAreaElement | null>(null);
const regionSelectionEnabled = ref(false);
const regionDragging = ref(false);
const regionStart = ref<RegionPoint | null>(null);
const regionDraft = ref<RegionRect | null>(null);
const regionSlideIndex = ref<number | null>(null);
const regionLoading = ref(false);
const regionError = ref("");
const windowWidth = ref(typeof window !== "undefined" ? window.innerWidth : 1024);
const leftColumnWidth = ref(0);
const rightColumnWidth = ref(0);
const leftCollapsed = ref(true);
const rightCollapsed = ref(false);
const isSplitDragging = ref(false);
const activeSplitter = ref<"left" | "right" | null>(null);
const currentInputHeight = ref(179);
const isCurrentInputResizing = ref(false);
const currentInputResizeStartY = ref(0);
const currentInputResizeStartHeight = ref(0);
/** 上传文件后启用左侧栏 hover 抽屉模式 */
const leftHoverMode = ref(false);
const leftHoverOpen = ref(false);
const leftPinned = ref(false);
let flowObserver: IntersectionObserver | null = null;
const flowIntersectionRatios = new Map<Element, number>();

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
  const defaultRight = clamp(width * 0.38, SIDE_RIGHT_MIN, Math.min(SIDE_RIGHT_MAX, width * SIDE_RIGHT_MAX_RATIO));
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
  /** hover 抽屉模式下左侧栏脱离 Grid 流：阅读区 | 分隔条 | 功能区 */
  if (leftHoverMode.value) {
    const rightWidth = rightCollapsed.value ? COLLAPSED_WIDTH : rightColumnWidth.value || SIDE_RIGHT_MIN;
    const rightSplit = rightCollapsed.value ? 0 : SPLITTER_PX;
    return {
      display: "grid",
      gridTemplateColumns: "minmax(" + CENTER_MIN + "px, 1fr) " + rightSplit + "px " + rightWidth + "px",
      alignItems: "stretch",
    };
  }
  const leftWidth = leftCollapsed.value ? COLLAPSED_WIDTH : leftColumnWidth.value || SIDE_LEFT_MIN;
  const rightWidth = rightCollapsed.value ? COLLAPSED_WIDTH : rightColumnWidth.value || SIDE_RIGHT_MIN;
  const leftSplit = leftCollapsed.value ? 0 : SPLITTER_PX;
  const rightSplit = rightCollapsed.value ? 0 : SPLITTER_PX;
  return {
    display: "grid",
    gridTemplateColumns:
      leftWidth +
      "px " +
      leftSplit +
      "px minmax(" +
      CENTER_MIN +
      "px, 1fr) " +
      rightSplit +
      "px " +
      rightWidth +
      "px",
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

function onCurrentInputResizeMove(e: PointerEvent) {
  if (!isCurrentInputResizing.value) return;
  currentInputHeight.value = clamp(
    currentInputResizeStartHeight.value + e.clientY - currentInputResizeStartY.value,
    150,
    Math.min(520, Math.max(220, window.innerHeight * 0.62)),
  );
}

function endCurrentInputResize() {
  if (!isCurrentInputResizing.value) return;
  isCurrentInputResizing.value = false;
  document.body.classList.remove("no-select");
  window.removeEventListener("pointermove", onCurrentInputResizeMove);
  window.removeEventListener("pointerup", endCurrentInputResize);
  window.removeEventListener("pointercancel", endCurrentInputResize);
}

function startCurrentInputResize(e: PointerEvent) {
  e.preventDefault();
  isCurrentInputResizing.value = true;
  currentInputResizeStartY.value = e.clientY;
  currentInputResizeStartHeight.value = currentInputHeight.value;
  document.body.classList.add("no-select");
  window.addEventListener("pointermove", onCurrentInputResizeMove);
  window.addEventListener("pointerup", endCurrentInputResize);
  window.addEventListener("pointercancel", endCurrentInputResize);
}

function toggleLeftCollapsed() {
  endSplitDrag();
  if (leftHoverMode.value) {
    if (!leftHoverOpen.value && !leftPinned.value) {
      leftHoverOpen.value = true;
    } else {
      leftPinned.value = !leftPinned.value;
      leftHoverOpen.value = leftPinned.value;
    }
    nextTick(() => scrollCurrentThumbIntoView());
    return;
  }
  leftCollapsed.value = !leftCollapsed.value;
  nextTick(() => {
    ensureColumnWidths();
    scrollCurrentThumbIntoView();
  });
}

function openLeftHoverPanel() {
  if (!leftHoverMode.value) return;
  leftHoverOpen.value = true;
  nextTick(() => scrollCurrentThumbIntoView());
}

function closeLeftHoverPanel() {
  if (leftHoverMode.value && !leftPinned.value) leftHoverOpen.value = false;
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
  if (isCurrentInputResizing.value && e.key === "Escape") {
    e.preventDefault();
    endCurrentInputResize();
    return;
  }
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

watch(
  () => store.currentIndex,
  () => {
    clearRegionSelection();
    nextTick(() => scrollCurrentThumbIntoView());
  },
);

watch(
  () => store.slides.length,
  () => nextTick(() => setupFlowObserver()),
);

/** 连续阅读模式：用 IntersectionObserver 跟踪当前可见页（hover 与固定模式均生效） */
function setupFlowObserver() {
  destroyFlowObserver();
  if (!slidesViewportRef.value) return;
  const observer = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        flowIntersectionRatios.set(e.target, e.intersectionRatio);
      }
      let bestTarget: Element | null = null;
      let bestRatio = 0;
      for (const [target, ratio] of flowIntersectionRatios) {
        if (ratio > bestRatio) {
          bestTarget = target;
          bestRatio = ratio;
        }
      }
      if (bestTarget && bestRatio > 0.2) {
        const idx = Number((bestTarget as HTMLElement).dataset.slideIndex);
        if (!isNaN(idx) && idx >= 0 && idx < store.slides.length && idx !== store.currentIndex) {
          store.currentIndex = idx;
        }
      }
    },
    { root: slidesViewportRef.value, threshold: [0, 0.25, 0.5, 0.75, 1] },
  );
  slideRefs.value.forEach((el) => el && observer.observe(el));
  flowObserver = observer;
}

function destroyFlowObserver() {
  if (flowObserver) {
    flowObserver.disconnect();
    flowObserver = null;
  }
  flowIntersectionRatios.clear();
}

function setSlideRef(el: any, i: number) {
  slideRefs.value[i] = el as HTMLElement | null;
}

onMounted(() => {
  if (store.token && store.files.length === 0) {
    void store.fetchFiles();
  }
  // 从其他页面返回时恢复 hover 侧栏，收起时仅保留窄触发轨道。
  if (store.slides.length > 0) {
    leftHoverMode.value = true;
    leftCollapsed.value = false;
    leftHoverOpen.value = false;
    leftPinned.value = false;
  }
  window.addEventListener("keydown", previewKeydownSplitAware);
  window.addEventListener("resize", onWindowResize);
  nextTick(() => ensureColumnWidths(true));
  nextTick(() => setupFlowObserver());
  nextTick(() => scrollCurrentThumbIntoView());
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", previewKeydownSplitAware);
  window.removeEventListener("resize", onWindowResize);
  endSplitDrag();
  endCurrentInputResize();
  destroyFlowObserver();
});

void ChartIntentPanel;
void ChartCodePanel;
void IllustrationPromptPanel;
void currentPreviewUrl;
void runIllustrationImage;
void selectModule;
void backToPreview;
void generateChartOnly;
void runIntentOnly;
void runChartCodeOnly;
void runFullWorkflow;
void chartBusy;
void workflowBusy;
void startCurrentInputResize;
void onIntentPanelResult;
void onChartCodeResult;
void onFluxGenerateRequest;
void workflowStepClass;
</script>

<template>
  <div class="workspace-root">
    <div v-if="!hasDoc" class="upload-phase">
      <div class="upload-stack">
        <div class="upload-card">
          <p class="upload-badge">第一步</p>
          <h2>上传 PDF 或 PPT</h2>
          <p class="upload-lead">
            支持 .pptx 和 .pdf。解析后可在工作台中预览、翻页、缩放、配图和生成内容。
          </p>

          <div class="drop-zone" @click="triggerFilePick">
            <div v-if="!uploadLoading" class="hint">
              <span class="file-glyph" aria-hidden="true"></span>
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

        <section class="recent-files-card" aria-label="最近文件">
          <div class="recent-files-head">
            <div>
              <p class="section-kicker">继续编辑</p>
              <h3>最近文件</h3>
            </div>
            <button type="button" class="recent-refresh" :disabled="store.filesLoading" @click="store.fetchFiles">
              {{ store.filesLoading ? "刷新中" : "刷新" }}
            </button>
          </div>

          <div v-if="recentFiles.length" class="recent-list">
            <button
              v-for="file in recentFiles"
              :key="file.id"
              type="button"
              class="recent-file-item"
              :disabled="openingRecentId === file.id"
              @click="openRecentFile(file)"
            >
              <span class="recent-file-main">
                <b>{{ file.original_filename }}</b>
                <small>{{ file.pages || 0 }} 页 · {{ new Date(file.updated_at || file.created_at).toLocaleString() }}</small>
              </span>
              <span class="recent-file-action">{{ openingRecentId === file.id ? "打开中" : "继续" }}</span>
            </button>
          </div>
          <p v-else class="recent-empty">
            暂无可继续编辑的文件。上传文档后会显示在这里。
          </p>
          <p v-if="recentMessage" class="msg">{{ recentMessage }}</p>
        </section>
      </div>
    </div>

    <div v-else ref="workFullRef" class="work-full" :style="workFullStyle">
      <template v-if="functionMode === 'preview'">
        <aside
          class="page-control-column"
          :class="{
            collapsed: !leftHoverMode && leftCollapsed,
            'page-control-column--hover': leftHoverMode,
            'page-control-column--open': leftHoverOpen || leftPinned,
            'page-control-column--pinned': leftPinned,
          }"
          @mouseenter="openLeftHoverPanel"
          @mouseleave="closeLeftHoverPanel"
          aria-label="页面控制"
        >
          <button
            type="button"
            class="collapse-toggle collapse-toggle--left"
            :title="leftHoverMode ? (leftPinned ? '取消固定页面控制' : '固定页面控制') : (leftCollapsed ? '展开页面控制' : '收起页面控制')"
            :aria-label="leftHoverMode ? (leftPinned ? '取消固定页面控制' : '固定页面控制') : (leftCollapsed ? '展开页面控制' : '收起页面控制')"
            @click.stop="toggleLeftCollapsed"
          >
            <template v-if="leftHoverMode && leftPinned">&times;</template>
            <template v-else-if="leftHoverMode && leftHoverOpen">&lsaquo;</template>
            <template v-else-if="leftHoverMode">&rsaquo;</template>
            <template v-else-if="leftCollapsed">&rsaquo;</template>
            <template v-else>&lsaquo;</template>
          </button>
          <div v-if="leftHoverMode" class="hover-rail-label">页面控制</div>
          <div v-else-if="leftCollapsed" class="collapsed-rail-label">页面</div>
          <div v-if="leftHoverMode || !leftCollapsed" class="tools-fixed">
            <div class="tool-block page-control-block">
              <p class="tool-block-title">页面控制</p>
              <header class="preview-toolbar">
                <div class="tb-left">
                  <span class="tb-doc">{{ store.docName }}</span>
                  <span v-if="currentSlide" class="tb-status">{{ slideStatusShort(currentSlide) }}</span>
                </div>
                <div class="tb-center">
                  <button type="button" class="tb-icon" :disabled="!canPrev" title="上一页" @click="prevPage">&lsaquo;</button>
                  <span class="tb-page">第 {{ pageLabel }} 页</span>
                  <button type="button" class="tb-icon" :disabled="!canNext" title="下一页" @click="nextPage">&rsaquo;</button>
                </div>
                <div class="tb-zoom" aria-label="缩放">
                  <input
                    class="tb-zoom-range"
                    type="range"
                    min="50"
                    max="200"
                    step="1"
                    :value="zoomPercent"
                    @input="onZoomInput"
                  />
                  <label class="tb-zoom-input-wrap">
                    <input
                      class="tb-zoom-input"
                      type="number"
                      min="50"
                      max="200"
                      step="1"
                      :value="zoomPercent"
                      @change="onZoomInput"
                    />
                    <span>%</span>
                  </label>
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
                  :ref="(el: any) => setPageThumbRef(el, i)"
                  type="button"
                  class="page-thumb"
                  :class="{ active: i === store.currentIndex }"
                  @click="goToPage(i)"
                >
                  <span class="thumb-index">{{ i + 1 }}</span>
                  <span class="thumb-frame">
                    <img v-if="s.thumbnailUrl" :src="s.thumbnailUrl" :alt="s.input.topic" />
                    <span v-else class="thumb-fallback">{{ s.input.topic || ("第 " + (i + 1) + " 页") }}</span>
                  </span>
                  <span class="thumb-title">{{ s.input.topic || ("第 " + (i + 1) + " 页") }}</span>
                </button>
              </div>
            </div>
          </div>
        </aside>

        <div
          v-if="splitLayoutHorizontal && !leftHoverMode"
          class="pane-splitter"
          :class="{ dragging: isSplitDragging && activeSplitter === 'left', disabled: leftCollapsed }"
          role="separator"
          aria-orientation="vertical"
          aria-label="拖动调整页面控制和预览宽度"
          title="拖动调整页面控制和预览宽度"
          @pointerdown="startSplitDrag($event, 'left')"
        />
        <!-- 中间：连续阅读模式（所有页面纵向排列） -->
        <section class="reader-column" aria-label="文档预览">
          <div class="reader-actions">
            <button
              type="button"
              class="reader-action-btn exit-editor-btn"
              title="保存当前生成结果并退出工作台"
              aria-label="保存当前生成结果并退出工作台"
              @click="exitEditor"
            >
              退出编辑
            </button>
            <button
              type="button"
              class="reader-action-btn selection-trigger"
              :class="{ active: regionSelectionEnabled }"
              title="框选幻灯片区域并提取文字"
              aria-label="框选幻灯片区域并提取文字"
              @click="toggleRegionSelection"
            >
              {{ regionSelectionEnabled ? "退出框选" : "框选文字" }}
            </button>
          </div>
          <div v-if="textPickerOpen" class="selection-popover" role="dialog" aria-label="确认提取文字">
            <div class="selection-popover-head">
              <strong>确认提取文字</strong>
              <button type="button" class="selection-close" title="关闭" aria-label="关闭" @click="closeTextPicker">×</button>
            </div>
            <p v-if="regionLoading">正在识别框选区域...</p>
            <p v-if="regionError" class="selection-error">{{ regionError }}</p>
            <textarea ref="textPickerRef" v-model="textPickerValue" rows="8" :disabled="regionLoading" />
            <div class="selection-actions">
              <button type="button" class="btn outline" :disabled="regionLoading || !regionDraft" @click="runOcrForRegion">重新 OCR</button>
              <button type="button" class="btn solid selection-apply" :disabled="regionLoading" @click="applySelectedText">写入正文框</button>
            </div>
          </div>
          <div ref="slidesViewportRef" class="reader-viewport reader-viewport--flow">
            <div class="slide-stage" :style="{ transform: 'scale(' + zoomScale + ')' }">
              <div
                v-for="(s, i) in store.slides"
                :key="s.id"
                :ref="(el: any) => setSlideRef(el, i)"
                class="flow-slide"
                :class="{ 'flow-slide--active': i === store.currentIndex }"
                :data-slide-index="i"
              >
                <div v-if="s.previewUrl" class="slide-image-shell">
                  <img class="slide-preview-img" :src="s.previewUrl" :alt="s.input.topic" loading="lazy" />
                  <div
                    v-if="regionSelectionEnabled && i === store.currentIndex"
                    class="region-selection-overlay"
                    @pointerdown="startRegionSelection($event, i)"
                    @pointermove="moveRegionSelection"
                    @pointerup="finishRegionSelection"
                    @pointercancel="clearRegionSelection(false)"
                  >
                    <div
                      v-if="regionDraft && regionSlideIndex === i"
                      class="region-selection-box"
                      :style="{
                        left: regionDraft.x * 100 + '%',
                        top: regionDraft.y * 100 + '%',
                        width: regionDraft.width * 100 + '%',
                        height: regionDraft.height * 100 + '%',
                      }"
                    />
                  </div>
                </div>
                <article v-else class="slide-fallback">
                  <h2>{{ s.input.topic }}</h2>
                  <p>{{ s.input.body || "本页暂无可用预览。" }}</p>
                </article>
                <span class="flow-slide-label">{{ i + 1 }} / {{ store.slides.length }}</span>
              </div>
            </div>
          </div>
          <section
            class="current-input-panel current-input-panel--reader reader-composer"
            :class="{ resizing: isCurrentInputResizing }"
            :style="{ height: currentInputHeight + 'px' }"
            aria-label="当前页输入"
          >
            <div class="current-input-head">
              <p class="tool-block-title">当前页输入</p>
              <span v-if="currentSlide" class="current-input-page">第 {{ store.currentIndex + 1 }} 页</span>
            </div>
            <div v-if="currentSlide" class="current-input-editor current-input-editor--reader">
              <textarea
                v-model="currentSlide.input.body"
                class="current-input-control current-input-textarea"
                rows="2"
                placeholder="编辑当前页正文，图表与插图会使用这段内容。"
              />
            </div>
            <div
              class="current-input-resizer"
              role="separator"
              aria-orientation="horizontal"
              aria-label="拖动调整当前页输入高度"
              title="拖动调整当前页输入高度"
              @pointerdown="startCurrentInputResize"
            />
          </section>
        </section>

        <div
          v-if="splitLayoutHorizontal"
          class="pane-splitter"
          :class="{ dragging: isSplitDragging && activeSplitter === 'right', disabled: rightCollapsed }"
          role="separator"
          aria-orientation="vertical"
          aria-label="拖动调整预览和功能区宽度"
          title="拖动调整预览和功能区宽度"
          @pointerdown="startSplitDrag($event, 'right')"
        />

        <!-- 右侧：功能选择与生成操作 -->
        <aside class="action-column" :class="{ collapsed: rightCollapsed }">
          <template v-if="rightCollapsed">
            <button
              type="button"
              class="collapse-toggle collapse-toggle--right collapse-toggle--compact"
              title="展开功能面板"
              aria-label="展开功能面板"
              @click="toggleRightCollapsed"
            >
              &lsaquo;
            </button>
            <div class="collapsed-rail-label">功能区</div>
          </template>

          <div v-else class="action-workspace">
            <header class="action-top-bar">
              <button
                type="button"
                class="collapse-toggle collapse-toggle--compact action-top-collapse"
                title="收起功能面板"
                aria-label="收起功能面板"
                @click="toggleRightCollapsed"
              >
                &lsaquo;
              </button>
            </header>

            <div class="workflow-runbar action-command-bar">
              <button
                type="button"
                class="collapse-toggle collapse-toggle--compact action-command-collapse"
                title="收起功能面板"
                aria-label="收起功能面板"
                @click="toggleRightCollapsed"
              >
                &lsaquo;
              </button>
              <button type="button" class="workflow-runbar-button" :disabled="workflowBusy || !currentSlide" @click="runFullWorkflow">
                <span v-if="fullWorkflowBusy" class="btn-spinner wine-spin"></span>
                一键跑通全流程
              </button>
            </div>

            <nav class="module-switcher module-switcher--compact" aria-label="功能模块">
              <button type="button" class="module-tab" :class="workflowStepClass('intent')" @click="selectModule('intent')">
                <span class="module-tab-mark" aria-hidden="true"></span>
                <span class="module-tab-body">
                  <span class="module-tab-title-row">
                    <b>图表意图</b>
                    <span class="module-status">{{ workflowStepStatus("intent") }}</span>
                  </span>
                </span>
              </button>
              <button type="button" class="module-tab" :class="workflowStepClass('chart')" @click="selectModule('chart')">
                <span class="module-tab-mark" aria-hidden="true"></span>
                <span class="module-tab-body">
                  <span class="module-tab-title-row">
                    <b>数据图表</b>
                    <span class="module-status">{{ workflowStepStatus("chart") }}</span>
                  </span>
                </span>
              </button>
              <button
                type="button"
                class="module-tab"
                :class="workflowStepClass('illustration')"
                @click="selectModule('illustration')"
              >
                <span class="module-tab-mark" aria-hidden="true"></span>
                <span class="module-tab-body">
                  <span class="module-tab-title-row">
                    <b>文生图插图</b>
                    <span class="module-status">{{ workflowStepStatus("illustration") }}</span>
                  </span>
                </span>
              </button>
            </nav>

            <div class="module-viewport">
              <section v-if="activeWorkflowStep === 'intent'" class="tools-section workflow-panel">
                <div class="workflow-panel-head">
                  <span class="fn-title">图表意图</span>
                  <button type="button" class="btn ghost compact" :disabled="workflowBusy || !currentSlide" @click="runIntentOnly">
                    <span v-if="workflowRunningStep === 'intent'" class="btn-spinner wine-spin"></span>
                    重新分析意图
                  </button>
                </div>
                <ChartIntentPanel
                  v-if="currentSlide"
                  v-model:slide="currentSlide.input"
                  hide-slide-input
                  :initial-semantic="currentSlide.intentSemantic || currentSlide.analyze?.semantic || null"
                  :initial-reason="currentSlide.analyze?.chart?.reason || null"
                  :initial-chart-type="currentSlide.analyze?.chart?.chartType || null"
                  @result="onIntentPanelResult"
                />
              </section>

              <section v-if="activeWorkflowStep === 'chart'" class="tools-section workflow-panel">
                <div class="workflow-panel-head">
                  <span class="fn-title">数据图表</span>
                  <button type="button" class="btn ghost compact" :disabled="workflowBusy || !currentSlide" @click="runChartCodeOnly">
                    <span v-if="workflowRunningStep === 'chart'" class="btn-spinner wine-spin"></span>
                    重新生成图表
                  </button>
                </div>
                <ChartCodePanel
                  v-if="currentSlide"
                  v-model:slide="currentSlide.input"
                  hide-slide-input
                  :initial-result="currentSlide.chartCode || null"
                  :initial-echarts-option="currentSlide.analyze?.chart?.echartsOption || null"
                  :initial-intent="currentSlide.analyze?.chart?.intent || null"
                  :initial-chart-type="currentSlide.analyze?.chart?.chartType || null"
                  :initial-reason="currentSlide.analyze?.chart?.reason || null"
                  @result="onChartCodeResult"
                />
              </section>

              <section v-if="activeWorkflowStep === 'illustration'" class="tools-section workflow-panel">
                <div class="workflow-panel-head">
                  <span class="fn-title">文生图插图</span>
                  <button
                    type="button"
                    class="btn ghost compact"
                    :disabled="workflowBusy || !currentSlide"
                    @click="runIllustrationImage"
                  >
                    <span v-if="currentSlide?.statusFluxImage === 'loading'" class="btn-spinner wine-spin"></span>
                    重新生成图片
                  </button>
                </div>
                <IllustrationPromptPanel
                  v-if="currentSlide"
                  ref="illustrationPanelRef"
                  v-model:slide="currentSlide.input"
                  :slide-page="currentSlide.page"
                  :doc-consistency="store.docConsistency"
                  :preview-url="currentPreviewUrl"
                  :initial-flux-image="currentSlide.fluxImage || null"
                  :flux-loading="currentSlide.statusFluxImage === 'loading'"
                  :flux-error="currentSlide.errorFluxImage || ''"
                  @flux-generate-request="onFluxGenerateRequest"
                />
              </section>
            </div>
          </div>
        </aside>
      </template>

      <div v-else class="function-shell">
        <header class="fn-toolbar">
          <button type="button" class="fn-back" @click="backToPreview">← 返回文档阅读</button>
          <span class="fn-title">{{ functionModeTitle }}</span>
          <span class="fn-meta">第 {{ pageLabel }} 页 · {{ currentSlide?.input.topic }}</span>
        </header>
        <div class="fn-scroll">
          <ChartIntentPanel
            v-if="functionMode === 'intent' && currentSlide"
            v-model:slide="currentSlide.input"
            :initial-semantic="currentSlide.intentSemantic || currentSlide.analyze?.semantic || null"
            @result="onIntentPanelResult"
          />
          <ChartCodePanel
            v-if="functionMode === 'code' && currentSlide"
            v-model:slide="currentSlide.input"
            :initial-result="currentSlide.chartCode || null"
            :initial-echarts-option="currentSlide.analyze?.chart?.echartsOption || null"
            @result="onChartCodeResult"
          />
          <IllustrationPromptPanel
            v-if="functionMode === 'illustration' && currentSlide"
            v-model:slide="currentSlide.input"
            :slide-page="currentSlide.page"
            :doc-consistency="store.docConsistency"
            :preview-url="currentPreviewUrl"
            :initial-flux-image="currentSlide.fluxImage || null"
            :flux-loading="currentSlide.statusFluxImage === 'loading'"
            :flux-error="currentSlide.errorFluxImage || ''"
            @flux-generate-request="onFluxGenerateRequest"
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
  align-items: flex-start;
  padding: clamp(24px, 5vw, 56px);
  background: var(--color-bg);
  overflow-y: auto;
}

.upload-stack {
  width: min(var(--panel-max-width), 100%);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.upload-card {
  background: var(--color-surface);
  padding: clamp(28px, 5vw, 48px);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  width: 100%;
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

.file-glyph {
  position: relative;
  width: 54px;
  height: 66px;
  border: 2px solid var(--color-primary-border);
  border-radius: 8px;
  background: linear-gradient(180deg, #fff 0%, var(--color-primary-soft) 100%);
  box-shadow: 0 10px 22px rgba(139, 41, 66, 0.08);
}

.file-glyph::before {
  content: "";
  position: absolute;
  top: -2px;
  right: -2px;
  width: 18px;
  height: 18px;
  border-left: 2px solid var(--color-primary-border);
  border-bottom: 2px solid var(--color-primary-border);
  border-radius: 0 8px 0 6px;
  background: var(--color-surface);
}

.file-glyph::after {
  content: "";
  position: absolute;
  left: 13px;
  right: 13px;
  top: 32px;
  height: 3px;
  border-radius: 999px;
  background: var(--color-primary);
  box-shadow: 0 10px 0 var(--color-primary-border);
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

.recent-files-card {
  width: 100%;
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.recent-files-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.section-kicker {
  margin: 0 0 4px;
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 800;
}

.recent-files-head h3 {
  margin: 0;
  font-size: 18px;
  color: var(--color-text);
}

.recent-refresh {
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-primary);
  font-weight: 800;
  cursor: pointer;
}

.recent-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.recent-list {
  display: grid;
  gap: 10px;
}

.recent-file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  width: 100%;
  min-height: 64px;
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--motion-base), background var(--motion-base), transform var(--motion-base);
}

.recent-file-item:hover:not(:disabled) {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  transform: translateY(-1px);
}

.recent-file-item:disabled {
  opacity: 0.6;
  cursor: progress;
}

.recent-file-main {
  min-width: 0;
}

.recent-file-main b {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}

.recent-file-main small {
  display: block;
  margin-top: 4px;
  color: var(--color-muted);
  font-size: 12px;
}

.recent-file-action {
  flex: 0 0 auto;
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 800;
}

.recent-empty {
  margin: 0;
  padding: var(--space-4);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-control);
  color: var(--color-muted);
  font-size: 13px;
  text-align: center;
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
  position: relative;
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

.action-column:not(.collapsed) > .action-workspace {
  flex: 1 1 0;
  min-height: 0;
  height: 100%;
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

/* ============ 左侧栏 hover 抽屉模式 ============ */
.page-control-column--hover {
  position: absolute !important;
  left: 0;
  top: 0;
  height: 100%;
  z-index: 30;
  width: 320px;
  transform: translateX(calc(-100% + 34px));
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.12);
  border-right: 1px solid var(--color-border);
  background: var(--color-surface);
}

.page-control-column--hover:hover,
.page-control-column--hover.page-control-column--open {
  transform: translateX(0);
}

.page-control-column--hover .tools-fixed {
  display: flex !important;
  padding: 0 10px 10px;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: opacity 0.14s ease;
}

.page-control-column--hover:hover .tools-fixed,
.page-control-column--hover.page-control-column--open .tools-fixed {
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
}

.page-control-column--hover .collapsed-rail-label {
  display: none;
}

.page-control-column--hover .hover-rail-label {
  position: absolute;
  right: 10px;
  top: 48px;
  writing-mode: vertical-rl;
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 2px;
  opacity: 1;
  transition: opacity 0.14s ease;
}

.page-control-column--hover:hover .hover-rail-label,
.page-control-column--hover.page-control-column--open .hover-rail-label {
  opacity: 0;
}

.page-control-column--hover .collapse-toggle {
  position: absolute;
  right: 4px;
  top: 18px;
  z-index: 31;
  width: 26px;
  height: 26px;
  min-height: 26px;
  margin: 0;
  border-radius: 8px;
  opacity: 1;
  font-size: 14px;
  box-shadow: 0 8px 20px rgba(139, 41, 66, 0.08);
  transition: background var(--motion-base), color var(--motion-base), border-color var(--motion-base);
}

.page-control-column--hover:hover .collapse-toggle,
.page-control-column--hover.page-control-column--open .collapse-toggle {
  top: 32px;
  right: 34px;
  border-radius: 8px;
}

.page-control-column--hover.page-control-column--pinned .collapse-toggle {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}

/* ============ 连续阅读模式 ============ */
.reader-viewport--flow {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: clamp(20px, 4vw, 56px);
  background: var(--color-bg-muted);
  display: flex;
  justify-content: center;
  align-items: flex-start;
}

.reader-actions {
  position: absolute;
  top: 14px;
  right: 48px;
  z-index: 12;
  display: flex;
  align-items: center;
  gap: 10px;
}

.reader-action-btn {
  width: auto;
  min-width: 78px;
  height: 38px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-primary);
  font-size: 15px;
  font-weight: 900;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: background var(--motion-base), color var(--motion-base), transform var(--motion-base);
}

.reader-action-btn:hover,
.selection-trigger.active {
  background: var(--color-primary);
  color: #fff;
  transform: translateY(-1px);
}

.exit-editor-btn {
  color: var(--color-text-soft);
}

.selection-popover {
  position: absolute;
  top: 60px;
  right: 16px;
  z-index: 20;
  width: min(420px, calc(100% - 32px));
  padding: var(--space-4);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  box-shadow: 0 18px 44px rgba(60, 35, 43, 0.18);
}

.selection-popover-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.selection-popover p {
  margin: var(--space-2) 0 var(--space-3);
  color: var(--color-muted);
  font-size: 12px;
  line-height: 1.5;
}

.selection-popover textarea {
  width: 100%;
  resize: vertical;
  box-sizing: border-box;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  color: var(--color-text);
  background: var(--color-bg);
  font: inherit;
  font-size: 13px;
  line-height: 1.55;
}

.selection-popover textarea:focus {
  border-color: var(--color-primary);
  outline: none;
  box-shadow: var(--shadow-focus);
}

.selection-close {
  width: 30px;
  height: 30px;
  border: none;
  background: transparent;
  color: var(--color-muted);
  font-size: 22px;
  cursor: pointer;
}

.selection-apply {
  margin-top: 0;
}

.selection-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

.selection-error {
  color: var(--color-danger) !important;
}

.reader-viewport--flow .slide-stage {
  width: min(1080px, 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}

.flow-slide {
  position: relative;
  width: 100%;
  display: flex;
  justify-content: center;
  padding: 32px 0;
  border-bottom: 1px dashed transparent;
  transition: border-color 0.3s;
}

.flow-slide--active {
  border-bottom-color: var(--color-primary-border);
}

.flow-slide-label {
  position: absolute;
  right: 8px;
  bottom: 8px;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(139, 41, 66, 0.08);
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  opacity: 0;
  transition: opacity 0.2s;
}

.flow-slide:hover .flow-slide-label {
  opacity: 1;
}

.flow-slide--active .flow-slide-label {
  opacity: 1;
  background: var(--color-primary);
  color: #fff;
}

.slide-image-shell {
  position: relative;
  display: inline-flex;
  max-width: 100%;
}

.flow-slide .slide-preview-img {
  display: block;
  max-width: 100%;
  height: auto;
  background: var(--color-surface);
  border: 1px solid #d8d1d4;
  border-radius: 4px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
}

.region-selection-overlay {
  position: absolute;
  inset: 0;
  z-index: 4;
  cursor: crosshair;
  touch-action: none;
  background: rgba(139, 41, 66, 0.025);
}

.region-selection-box {
  position: absolute;
  border: 2px solid var(--color-primary);
  background: rgba(139, 41, 66, 0.16);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.7) inset;
  pointer-events: none;
}

.flow-slide .slide-fallback {
  width: min(960px, 100%);
  min-height: 540px;
  padding: clamp(32px, 5vw, 64px);
  background: var(--color-surface);
  border: 1px solid #d8d1d4;
  border-radius: 4px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
}

.flow-slide .slide-fallback h2 {
  margin: 0 0 var(--space-5);
  font-size: clamp(28px, 4vw, 48px);
  color: var(--color-text);
}

.flow-slide .slide-fallback p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.8;
  color: var(--color-text-soft);
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

.collapse-toggle--compact {
  width: 26px;
  height: 26px;
  min-height: 26px;
  margin: 0;
  font-size: 14px;
  border-radius: 8px;
  box-shadow: 0 8px 20px rgba(139, 41, 66, 0.08);
}

.action-column.collapsed .collapse-toggle--compact {
  margin: 6px auto 4px;
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
  padding: 8px;
  margin-top: 24px;
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
  margin: 0 0 6px;
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
  gap: 7px;
}

.tb-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1 1 100%;
  padding-right: 0;
}

.tb-doc {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.tb-status {
  font-size: 10px;
  font-weight: 600;
  color: var(--color-muted);
}

.tb-center {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1 1 100%;
  min-width: 0;
}

.tb-page {
  flex: 1 1 auto;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-soft);
  min-width: 0;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.tb-icon {
  width: 30px;
  height: 30px;
  min-height: 30px;
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

.tb-zoom-range {
  flex: 1 1 auto;
  min-width: 76px;
  accent-color: var(--color-primary);
  cursor: pointer;
}

.tb-zoom-input-wrap {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 3px;
  height: 30px;
  min-width: 66px;
  padding: 0 7px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 700;
}

.tb-zoom-input {
  width: 34px;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--color-text);
  font: inherit;
  text-align: center;
  appearance: textfield;
  -moz-appearance: textfield;
}

.tb-zoom-input::-webkit-outer-spin-button,
.tb-zoom-input::-webkit-inner-spin-button {
  appearance: none;
  -webkit-appearance: none;
  margin: 0;
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
  min-height: 30px;
  padding: 0 10px;
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

.action-workspace {
  flex: 1 1 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  gap: 8px;
  padding: 8px 10px 10px;
  background: var(--color-surface);
}

.action-top-bar {
  display: none;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}

.action-top-bar .collapse-toggle--compact {
  margin-top: 6px;
}

.action-top-collapse {
  display: none;
}

.current-input-panel {
  flex: 1 1 auto;
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-card);
  background: linear-gradient(180deg, rgba(255, 250, 251, 0.96), rgba(255, 255, 255, 0.94));
  box-shadow: 0 8px 22px rgba(139, 41, 66, 0.08);
}

.current-input-panel--reader {
  position: relative;
  flex: 0 0 auto;
  width: calc(100% - 24px);
  max-width: none;
  min-height: 150px;
  max-height: min(520px, 62vh);
  margin: 0 0 0 24px;
  padding: 12px clamp(16px, 3vw, 32px) 18px;
  border: 0;
  border-top: 1px solid rgba(139, 41, 66, 0.14);
  border-bottom: 1px solid rgba(139, 41, 66, 0.14);
  border-radius: 0;
  background: linear-gradient(135deg, rgba(255, 250, 251, 0.96) 0%, rgba(247, 237, 240, 0.94) 100%);
  box-shadow: 0 6px 14px rgba(60, 35, 43, 0.045);
  overflow: visible;
  resize: none;
}

.current-input-editor--reader {
  display: block;
  min-width: 0;
  height: calc(100% - 34px);
  min-height: 104px;
}

.current-input-panel--reader .current-input-head {
  margin-bottom: 6px;
}

.current-input-panel--reader .current-input-head .tool-block-title {
  font-size: 12px;
}

.current-input-panel--reader .current-input-page {
  background: rgba(139, 41, 66, 0.06);
}

.current-input-panel--reader .current-field {
  gap: 3px;
}

.current-input-panel--reader .current-input-textarea {
  display: block;
  height: 100%;
  min-height: 104px;
  max-height: none;
  overflow: auto;
  resize: none;
}

.current-input-resizer {
  position: absolute;
  left: clamp(16px, 3vw, 32px);
  right: clamp(16px, 3vw, 32px);
  bottom: 6px;
  height: 10px;
  cursor: ns-resize;
}

.current-input-resizer::before {
  content: "";
  position: absolute;
  left: 50%;
  top: 4px;
  width: 72px;
  height: 3px;
  border-radius: 999px;
  background: rgba(139, 41, 66, 0.32);
  transform: translateX(-50%);
  transition: background var(--motion-fast), width var(--motion-fast);
}

.current-input-resizer:hover::before,
.current-input-panel--reader.resizing .current-input-resizer::before {
  width: 96px;
  background: var(--color-primary);
}

.current-input-panel--reader .current-input-control {
  background: rgba(255, 255, 255, 0.94);
  border-color: rgba(139, 41, 66, 0.1);
  box-shadow: none;
  font-size: 12px;
  padding: 8px 10px;
}

.current-input-panel--reader .current-input-control:focus {
  background: rgba(255, 255, 255, 0.5);
  border-color: rgba(139, 41, 66, 0.12);
  box-shadow: 0 0 0 3px rgba(139, 41, 66, 0.06);
}

.current-input-panel--reader .current-input-editor--reader .current-field:first-child .current-input-control {
  height: auto;
}

@media (max-width: 900px) {
  .current-input-panel--reader {
    width: 100%;
    max-width: none;
    margin: 0;
    padding: 10px 14px 12px;
  }

  .current-input-editor--reader {
    display: block;
  }
}

.current-input-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.current-input-head .tool-block-title {
  margin: 0;
  color: var(--color-primary);
}

.current-input-page {
  flex-shrink: 0;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--color-primary-soft);
  border: 1px solid var(--color-primary-border);
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 800;
}

.current-input-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.current-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.current-field span {
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 800;
}

.current-input-control {
  width: 100%;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  background: rgba(255, 255, 255, 0.86);
  color: var(--color-text);
  font: inherit;
  font-size: 13px;
  line-height: 1.55;
  padding: 9px 11px;
  outline: none;
  transition: border-color var(--motion-fast), box-shadow var(--motion-fast), background var(--motion-fast);
}

.current-input-control:focus {
  border-color: var(--color-primary);
  background: var(--color-surface);
  box-shadow: 0 0 0 3px rgba(139, 41, 66, 0.1);
}

.current-input-textarea {
  min-height: 132px;
  max-height: 260px;
  resize: vertical;
}

.module-switcher {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
  align-items: stretch;
}

.workflow-runbar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 44px;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}

.action-command-bar {
  min-height: 48px;
  padding: 7px;
  border-color: rgba(139, 41, 66, 0.12);
  background: linear-gradient(135deg, #fffafb 0%, #f8eef1 100%);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.6);
}

.action-command-collapse {
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  min-height: 34px;
  margin: 0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: none;
  font-size: 18px;
  line-height: 1;
}

.workflow-runbar-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: var(--control-md);
  padding: 0 14px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-control);
  background: var(--color-primary);
  color: #fff;
  font: inherit;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--motion-base), border-color var(--motion-base), box-shadow var(--motion-base), transform var(--motion-base);
}

.action-command-bar .workflow-runbar-button {
  min-height: 34px;
  border-radius: 8px;
}

.workflow-runbar-button:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  box-shadow: 0 4px 12px rgba(139, 41, 66, 0.14);
  transform: translateY(-1px);
}

.workflow-runbar-button:disabled {
  opacity: 0.48;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.workflow-runbar-hint {
  min-width: 0;
  flex: 1 1 auto;
  color: var(--color-muted);
  font-size: 12px;
  line-height: 1.4;
  order: 2;
}

.action-command-bar .workflow-runbar-button {
  order: 3;
}

.action-command-bar .action-command-collapse {
  order: 1;
}

.module-tab {
  min-width: 0;
  min-height: 44px;
  display: grid;
  grid-template-columns: 4px minmax(0, 1fr);
  gap: 0;
  padding: 0;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-card);
  background: rgba(255, 255, 255, 0.88);
  color: var(--color-text-soft);
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  transition:
    border-color var(--motion-base),
    background var(--motion-base),
    box-shadow var(--motion-base),
    transform var(--motion-base);
}

.module-tab:hover {
  border-color: var(--color-primary);
  box-shadow: 0 3px 10px rgba(139, 41, 66, 0.08);
}

.module-tab.active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  box-shadow: inset 0 0 0 1px rgba(139, 41, 66, 0.08);
}

.module-tab-mark {
  background: transparent;
  transition: background var(--motion-base);
}

.module-tab.active .module-tab-mark {
  background: var(--color-primary);
}

.module-switcher--compact .module-tab-body {
  padding: 8px 10px 8px 8px;
}

.module-tab-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
  width: 100%;
}

.module-tab b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--color-text);
}

.module-tab small {
  display: none;
}

.module-status {
  font-size: 10px;
  font-weight: 800;
}

.module-tab.done .module-status {
  color: var(--color-primary);
}

.module-tab.running .module-status {
  color: var(--color-warning);
}

.module-tab.error .module-status {
  color: var(--color-danger);
}

.module-viewport {
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-card);
  background: #fff;
  scrollbar-gutter: stable;
}

.module-viewport .workflow-panel {
  min-height: min(100%, 520px);
}

.module-viewport :deep(.flux-img) {
  max-height: min(56vh, 560px);
  width: 100%;
  object-fit: contain;
  cursor: zoom-in;
}

.module-viewport :deep(.ech) {
  min-height: 300px;
  height: min(42vh, 400px);
}

.module-viewport :deep(.cj) {
  min-height: 260px;
}

.module-viewport :deep(.mmd) {
  min-height: 200px;
}

.module-viewport::-webkit-scrollbar {
  width: 10px;
}

.module-viewport::-webkit-scrollbar-thumb {
  background: rgba(139, 41, 66, 0.38);
  border: 2px solid var(--color-primary-soft);
  border-radius: 999px;
}

.module-viewport::-webkit-scrollbar-thumb:hover {
  background: rgba(139, 41, 66, 0.58);
}

.workflow-panel {
  gap: var(--space-4);
}

.workflow-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--color-primary-border);
}

.workflow-panel-head .fn-title {
  color: var(--color-primary);
  font-weight: 900;
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

  /* 移动端禁用 hover 抽屉 */
  .page-control-column--hover {
    position: relative !important;
    transform: none;
    width: 100%;
    box-shadow: none;
  }
}
</style>
