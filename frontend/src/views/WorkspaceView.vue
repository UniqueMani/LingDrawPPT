<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { store } from "../store";
import {
  analyzeDocumentConsistency,
  extractText,
  fetchAuthedAssetBlobUrl,
  fluxGenerateImage,
  getFileDetail,
  insertPptImage,
  listPageImages,
  ocrRegion,
  recommendPptPlacement,
  removeLastPptImage,
  removePptImage,
  stagePptImage,
  updatePptImagePlacement,
  fetchPptShapeImageBlobUrl,
  vizLabChartCode,
  vizLabIntent,
} from "../api/client";
import ChartIntentPanel from "../components/ChartIntentPanel.vue";
import ChartCodePanel from "../components/ChartCodePanel.vue";
import IllustrationPromptPanel from "../components/IllustrationPromptPanel.vue";
import SlidePptInsertOverlay from "../components/SlidePptInsertOverlay.vue";
import {
  beginFluxJob,
  clearFluxRuntimeState,
  completeFluxJob,
  createFluxRequestKey,
  failFluxJob,
} from "../utils/fluxJobManager";
import { clampPlacementRect, INSERT_PATCH_KEY } from "../utils/pptInsert";
import { exportEchartsOptionToPng } from "../utils/chartExport";
import type {
  FluxGenerateImagePayload,
  FileRecord,
  InsertImageResponse,
  NormalizedRect,
  PptPagePicture,
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
const chartCodePanelRef = ref<{ exportChartPngDataUrl: () => Promise<{ dataUrl: string; aspectRatio: string } | null> } | null>(null);
const workflowRunningStep = ref<WorkflowStep | null>(null);
const workflowErrorStep = ref<WorkflowStep | null>(null);
const fullWorkflowBusy = ref(false);

type PptInsertActive = {
  slideIndex: number;
  page: number;
  imageUrl: string;
  displayImageUrl: string;
  aspectRatio: string;
  slideAspect: number;
  placement: NormalizedRect;
  source: "flux" | "chart";
};

type InsertedPictureEdit = {
  shapeIndex: number;
  displayImageUrl: string;
  aspectRatio: string;
  slideAspect: number;
  placement: NormalizedRect;
};

const pptInsertActive = ref<PptInsertActive | null>(null);
const pptInsertLoading = ref(false);
const pptInsertSaving = ref(false);
const insertWriteInFlight = ref(false);
const insertFeedback = ref("");
const pptUndoLoading = ref(false);
const pagePictures = ref<PptPagePicture[]>([]);
const slideAspectForPictures = ref(16 / 9);
const pagePictureBlobUrls = ref<Record<number, string>>({});
let pagePicturesRequestId = 0;
let pagePicturesInflight: Promise<void> | null = null;
let pagePicturesInflightPage = 0;
type PagePicturesCacheEntry = {
  pictures: PptPagePicture[];
  aspect: number;
  blobUrls: Record<number, string>;
  mutationAt: number;
  previewAt: number;
  orphanCovers: NormalizedRect[];
  previewDisplayUrl?: string;
};
const pagePicturesCache = new Map<number, PagePicturesCacheEntry>();
let pictureSelectRequestId = 0;
const selectedShapeIndex = ref<number | null>(null);
const insertedEditDraft = ref<InsertedPictureEdit | null>(null);
const insertedEditSavedPlacement = ref<NormalizedRect | null>(null);
const orphanStalePreviewCovers = ref<NormalizedRect[]>([]);
const lastPictureMutationAt = ref(0);
const lastPreviewPatchAt = ref(0);
const pendingPreviewRefreshPage = ref<number | null>(null);
const previewRefreshInflight = new Map<number, Promise<boolean>>();
const insertedEditSaving = ref(false);
const pendingInsertPlacementSave = ref<NormalizedRect | null>(null);
let insertedImageBlobUrl: string | null = null;

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
const currentSlideAspect = computed(() => {
  const slide = currentSlide.value;
  if (slide?.pageWidth && slide.pageHeight) return slide.pageWidth / slide.pageHeight;
  return slideAspectForPictures.value;
});
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
  clearPagePicturesCache();
  pagePictures.value = [];
  releasePagePictureBlobs();
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
  if (/^(https?:)?\/\//.test(url) || url.startsWith("data:") || url.startsWith("blob:")) return url;
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
        pageWidth: p.page_width ?? undefined,
        pageHeight: p.page_height ?? undefined,
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
      pageWidth: page.page_width ?? undefined,
      pageHeight: page.page_height ?? undefined,
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
    scrollToSlide(store.currentIndex, "auto");
  }
}

function nextPage() {
  if (canNext.value) {
    store.currentIndex += 1;
    scrollToSlide(store.currentIndex, "auto");
  }
}

function goToPage(i: number) {
  if (i < 0 || i >= store.slides.length) return;
  store.currentIndex = i;
  scrollToSlide(i, "auto");
}

function goToPageNumber(value: number | string) {
  const page = Math.round(Number(value));
  if (!Number.isFinite(page) || !store.slides.length) return;
  const nextIndex = Math.min(store.slides.length - 1, Math.max(0, page - 1));
  goToPage(nextIndex);
}

function onPageNumberInput(event: Event) {
  goToPageNumber((event.target as HTMLInputElement).value);
}

/** 滚动到指定页面（连续阅读模式下平滑滚动） */
function scrollToSlide(i: number, behavior: ScrollBehavior = "smooth") {
  const el = slideRefs.value[i];
  if (el && slidesViewportRef.value) {
    el.scrollIntoView({ behavior, block: "start" });
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

const canInsertPpt = computed(() => {
  const name = (store.docName || "").toLowerCase();
  return Boolean(store.currentFileId && name.endsWith(".pptx"));
});

const showPassivePictureLayer = computed(() => {
  if (!canInsertPpt.value) return false;
  if (pptInsertActive.value) return false;
  const draft = insertedEditDraft.value;
  if (draft) {
    if (insertWriteInFlight.value || draft.shapeIndex < 0 || !previewLooksSynced()) {
      return false;
    }
  }
  return true;
});

/** Overlay 是否叠浮动图：仅 PNG 尚未烘焙该配图时 */
const overlayShowsFloatImage = computed(() => {
  const draft = insertedEditDraft.value;
  if (!draft) return false;
  if (insertWriteInFlight.value) return true;
  if (draft.shapeIndex < 0) return true;
  return !previewLooksSynced();
});

/** 被动层是否显示浮动图：临时 shape 或有旧位置遮罩时（PNG 未同步前） */
const passivePictureShowsImage = computed(() => {
  if (!pagePictures.value.length) return false;
  const draft = insertedEditDraft.value;
  if (draft && (insertWriteInFlight.value || draft.shapeIndex < 0 || !previewLooksSynced())) {
    return false;
  }
  if (pagePictures.value.some((pic) => pic.shape_index < 0)) return true;
  return orphanStalePreviewCovers.value.length > 0;
});

function previewLooksSynced() {
  return lastPreviewPatchAt.value > 0 && lastPreviewPatchAt.value >= lastPictureMutationAt.value;
}

/** 被动层点击区：始终列出本页全部配图 */
const passivePicturesForLayer = computed(() => {
  const fromMemory = stripStaleOptimisticPictures(pagePictures.value);
  if (fromMemory.length) return fromMemory;
  const slide = currentSlide.value;
  if (!slide) return [];
  const cached = pagePicturesCache.get(slide.page);
  return stripStaleOptimisticPictures(cached?.pictures.map((item) => ({ ...item })) ?? []);
});

/** 被动层浮动图：只渲染需要覆盖 PNG 旧烘焙的那一张 */
function shouldShowPassiveFloat(pic: PptPagePicture): boolean {
  if (!passivePictureShowsImage.value) return false;
  if (pic.shape_index < 0) return true;
  if (!orphanStalePreviewCovers.value.length) return false;
  if (selectedShapeIndex.value != null) {
    return pic.shape_index === selectedShapeIndex.value;
  }
  return true;
}

/** 遮住 PNG 里已烘焙的旧位置（仅 orphan 列表，编辑中由 Overlay 负责新位置） */
const pngBakedMaskRects = computed(() => {
  return orphanStalePreviewCovers.value.map((rect) => ({ ...rect }));
});

function rememberOrphanStalePreviewRegion(rect: NormalizedRect) {
  orphanStalePreviewCovers.value = [...orphanStalePreviewCovers.value, { ...rect }];
  markPictureLayoutDirty();
}

const hasChartResult = computed(() => {
  const slide = currentSlide.value;
  if (!slide) return false;
  return Boolean(
    slide.chartCode?.echartsOption ||
      slide.analyze?.chart?.echartsOption ||
      slide.chartCode?.chartJsConfig ||
      slide.chartCode?.mermaidSource
  );
});

const globalInsertTarget = computed<"chart" | "flux" | null>(() => {
  const slide = currentSlide.value;
  if (!canInsertPpt.value || !slide) return null;
  if (activeWorkflowStep.value === "illustration" && slide.fluxImage?.resultImageUrl) return "flux";
  if (activeWorkflowStep.value === "chart" && hasChartResult.value) return "chart";
  if (hasChartResult.value) return "chart";
  if (slide.fluxImage?.resultImageUrl) return "flux";
  return null;
});

const globalInsertHint = computed(() => {
  if (globalInsertTarget.value === "chart") return "将当前页数据图表插入 PPT";
  if (globalInsertTarget.value === "flux") return "将当前页 AI 配图插入 PPT";
  return "请先在右侧生成数据图表或文生图配图";
});

function appendCacheBust(url: string) {
  if (!url) return url;
  const base = url.split("?")[0];
  return `${base}?t=${Date.now()}`;
}

function rememberPagePicturesCache(page: number) {
  const slide = store.slides.find((item) => item.page === page);
  pagePicturesCache.set(page, {
    pictures: stripStaleOptimisticPictures(pagePictures.value).map((item) => ({ ...item })),
    aspect: slideAspectForPictures.value,
    blobUrls: Object.fromEntries(
      Object.entries(pagePictureBlobUrls.value).filter(([idx]) => {
        const shapeIndex = Number(idx);
        return shapeIndex >= 0 || shapeIndex === activeOptimisticShapeIndex();
      })
    ),
    mutationAt: lastPictureMutationAt.value,
    previewAt: lastPreviewPatchAt.value,
    orphanCovers: orphanStalePreviewCovers.value.map((rect) => ({ ...rect })),
    previewDisplayUrl: slide?.previewUrl?.split("?")[0] || "",
  });
}

function touchPagePreviewSyncInCache(page: number, previewAt: number, mutationAt = lastPictureMutationAt.value) {
  const slide = store.slides.find((item) => item.page === page);
  const cached = pagePicturesCache.get(page);
  if (cached) {
    pagePicturesCache.set(page, {
      ...cached,
      previewAt,
      mutationAt,
      orphanCovers: [],
      previewDisplayUrl: slide?.previewUrl?.split("?")[0] || cached.previewDisplayUrl || "",
    });
    return;
  }
  pagePicturesCache.set(page, {
    pictures: pagePictures.value.map((item) => ({ ...item })),
    aspect: slideAspectForPictures.value,
    blobUrls: { ...pagePictureBlobUrls.value },
    mutationAt,
    previewAt,
    orphanCovers: [],
    previewDisplayUrl: slide?.previewUrl?.split("?")[0] || "",
  });
}

function bumpSlidePreviewDisplay(page: number) {
  const slide = store.slides.find((item) => item.page === page);
  if (!slide?.previewUrl) return;
  const base = slide.previewUrl.split("?")[0];
  const resolvedBase = resolveAssetUrl(base);
  slide.previewUrl = appendCacheBust(resolvedBase);
  slide.thumbnailUrl = appendCacheBust(resolvedBase.replace("/page-", "/thumb-"));
  const cached = pagePicturesCache.get(page);
  if (cached) {
    pagePicturesCache.set(page, { ...cached, previewDisplayUrl: base });
  }
}

function applyPagePicturesCache(page: number) {
  const cached = pagePicturesCache.get(page);
  if (!cached) {
    pagePictures.value = [];
    pagePictureBlobUrls.value = {};
    lastPictureMutationAt.value = 0;
    lastPreviewPatchAt.value = 0;
    orphanStalePreviewCovers.value = [];
    return false;
  }
  pagePictures.value = cached.pictures.map((item) => ({ ...item }));
  pagePictures.value = stripStaleOptimisticPictures(pagePictures.value);
  slideAspectForPictures.value = cached.aspect;
  pagePictureBlobUrls.value = { ...cached.blobUrls };
  lastPictureMutationAt.value = cached.mutationAt;
  lastPreviewPatchAt.value = cached.previewAt;

  const previewSynced = lastPreviewPatchAt.value > 0 && lastPreviewPatchAt.value >= lastPictureMutationAt.value;
  orphanStalePreviewCovers.value = previewSynced
    ? []
    : (cached.orphanCovers || []).map((rect) => ({ ...rect }));

  const slide = store.slides.find((item) => item.page === page);
  if (slide && cached.previewDisplayUrl) {
    slide.previewUrl = appendCacheBust(resolveAssetUrl(cached.previewDisplayUrl));
    slide.thumbnailUrl = appendCacheBust(
      resolveAssetUrl(cached.previewDisplayUrl).replace("/page-", "/thumb-")
    );
  } else if (previewSynced) {
    bumpSlidePreviewDisplay(page);
  }

  return true;
}

function clearPagePicturesCache() {
  pagePicturesCache.clear();
}

function isShapeIndexOnPage(shapeIndex: number) {
  return pagePictures.value.some((item) => item.shape_index === shapeIndex);
}

function invalidateInflightPagePicturesLoad() {
  pagePicturesRequestId += 1;
}

function activeOptimisticShapeIndex(): number | null {
  if (!insertWriteInFlight.value || !insertedEditDraft.value) return null;
  const idx = insertedEditDraft.value.shapeIndex;
  return idx < 0 ? idx : null;
}

function stripStaleOptimisticPictures(pictures: PptPagePicture[]): PptPagePicture[] {
  const activeTemp = activeOptimisticShapeIndex();
  return pictures.filter(
    (item) => item.shape_index >= 0 || (activeTemp != null && item.shape_index === activeTemp)
  );
}

function purgeStaleOptimisticFromState() {
  const activeTemp = activeOptimisticShapeIndex();
  const removed = pagePictures.value.filter(
    (item) => item.shape_index < 0 && item.shape_index !== activeTemp
  );
  if (!removed.length) return;
  pagePictures.value = pagePictures.value.filter(
    (item) => item.shape_index >= 0 || item.shape_index === activeTemp
  );
  for (const item of removed) {
    revokePagePictureBlob(item.shape_index);
  }
}

function mergeServerPagePictures(serverPictures: PptPagePicture[] | undefined) {
  const server = stripStaleOptimisticPictures(
    (serverPictures || []).map((item) => ({ ...item }))
  );

  if (insertWriteInFlight.value) {
    const activeTemp = activeOptimisticShapeIndex();
    if (activeTemp != null && !server.length) {
      const temp = pagePictures.value.find((item) => item.shape_index === activeTemp);
      if (temp) return [temp];
    }
  }

  return server;
}

async function resolveInsertedPictureFromResult(
  slidePage: number,
  optimisticPicture: PptPagePicture,
  result: InsertImageResponse
): Promise<PptPagePicture> {
  const direct = result.picture;
  if (direct && direct.shape_index >= 0) {
    return direct;
  }

  store.addLog("插入响应缺少有效 picture，正在从服务端列表补全…");
  if (!store.currentFileId) {
    throw new Error("插入成功但无法确认配图索引");
  }

  const resp = await listPageImages(store.baseUrl, {
    file_id: store.currentFileId,
    page: slidePage,
  });
  const candidates = stripStaleOptimisticPictures(resp.pictures || []);
  if (!candidates.length) {
    throw new Error("插入成功但当前页未找到配图");
  }

  const samePlacement = candidates.find(
    (item) =>
      Math.abs(item.x - optimisticPicture.x) < 0.02 &&
      Math.abs(item.y - optimisticPicture.y) < 0.02
  );
  if (samePlacement) return samePlacement;

  return candidates.reduce((best, item) => (item.shape_index > best.shape_index ? item : best));
}

function ensureOptimisticPictureOnPage(editing: InsertedPictureEdit) {
  if (editing.shapeIndex >= 0) return;
  if (pagePictures.value.some((item) => item.shape_index === editing.shapeIndex)) return;
  pagePictures.value = [
    ...pagePictures.value,
    {
      shape_index: editing.shapeIndex,
      x: editing.placement.x,
      y: editing.placement.y,
      width: editing.placement.width,
      height: editing.placement.height,
      aspect_ratio: editing.aspectRatio,
    },
  ];
}

async function ensurePagePicturesLoaded() {
  if (pagePictures.value.length) return;
  if (pagePicturesInflight && pagePicturesInflightPage === currentSlide.value?.page) {
    await pagePicturesInflight;
    return;
  }
  await loadPagePictures();
}

function enterPictureEditMode(pic: PptPagePicture, shapeIndex: number, displayImageUrl = "") {
  const placement = {
    x: pic.x,
    y: pic.y,
    width: pic.width,
    height: pic.height,
  };
  selectedShapeIndex.value = shapeIndex;
  insertedEditSavedPlacement.value = { ...placement };
  insertedEditDraft.value = {
    shapeIndex,
    displayImageUrl: displayImageUrl || pagePictureBlobUrls.value[shapeIndex] || "",
    aspectRatio: pic.aspect_ratio || "16:9",
    slideAspect: currentSlideAspect.value,
    placement: { ...placement },
  };
}

function reconcilePictureSelection() {
  if (selectedShapeIndex.value == null) return;
  if (selectedShapeIndex.value < 0 || insertWriteInFlight.value) return;
  if (!isShapeIndexOnPage(selectedShapeIndex.value)) {
    deselectInsertedPicture();
  }
}

async function exportCurrentPpt() {
  if (!store.currentFileId || !canInsertPpt.value) return;
  store.saveCurrentWorkspaceDraft();
  await router.push("/workspace/export");
}

async function resolveInsertImageUrl(url: string) {
  if (url.includes("/api/ppt/staged/")) {
    return fetchAuthedAssetBlobUrl(store.baseUrl, url);
  }
  return resolveAssetUrl(url);
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("读取图片失败"));
    reader.readAsDataURL(blob);
  });
}

async function stageRemoteImageForInsert(imageUrl: string): Promise<string> {
  if (!store.currentFileId) throw new Error("未选择 PPT 文件");
  if (imageUrl.includes("/api/ppt/staged/")) return imageUrl;
  if (imageUrl.startsWith("data:")) {
    const staged = await stagePptImage(store.baseUrl, {
      file_id: store.currentFileId,
      image_data: imageUrl,
    });
    return staged.image_url;
  }
  const res = await fetch(resolveAssetUrl(imageUrl));
  if (!res.ok) throw new Error(`下载配图失败：HTTP ${res.status}`);
  const staged = await stagePptImage(store.baseUrl, {
    file_id: store.currentFileId,
    image_data: await blobToDataUrl(await res.blob()),
  });
  return staged.image_url;
}

function releasePagePictureBlobs() {
  for (const url of Object.values(pagePictureBlobUrls.value)) {
    if (url.startsWith("blob:")) {
      URL.revokeObjectURL(url);
    }
  }
  pagePictureBlobUrls.value = {};
}

function revokePagePictureBlob(shapeIndex: number) {
  const url = pagePictureBlobUrls.value[shapeIndex];
  if (!url) return;
  if (url.startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
  const next = { ...pagePictureBlobUrls.value };
  delete next[shapeIndex];
  pagePictureBlobUrls.value = next;
}

async function hydratePagePictureBlobs(page: number, pictures: PptPagePicture[], requestId: number) {
  if (!store.currentFileId || !pictures.length) {
    releasePagePictureBlobs();
    return;
  }

  const previous = pagePictureBlobUrls.value;
  const next: Record<number, string> = {};
  const toRevoke: string[] = [];

  for (const pic of pictures) {
    const cached = previous[pic.shape_index];
    if (cached) next[pic.shape_index] = cached;
  }

  for (const [idx, url] of Object.entries(previous)) {
    const shapeIndex = Number(idx);
    if (!pictures.some((pic) => pic.shape_index === shapeIndex) && url.startsWith("blob:")) {
      toRevoke.push(url);
    }
  }

  const missing = pictures.filter((pic) => !next[pic.shape_index]);
  const entries = await Promise.all(
    missing.map(async (pic) => {
      try {
        const url = await fetchPptShapeImageBlobUrl(store.baseUrl, {
          file_id: store.currentFileId!,
          page,
          shape_index: pic.shape_index,
        });
        return [pic.shape_index, url] as const;
      } catch {
        return null;
      }
    })
  );
  if (requestId !== pagePicturesRequestId) {
    for (const entry of entries) {
      if (entry && !previous[entry[0]]) URL.revokeObjectURL(entry[1]);
    }
    return;
  }

  for (const entry of entries) {
    if (entry) next[entry[0]] = entry[1];
  }
  pagePictureBlobUrls.value = next;
  for (const url of toRevoke) URL.revokeObjectURL(url);

  const editing = insertedEditDraft.value;
  if (editing && editing.shapeIndex >= 0) {
    const liveUrl = next[editing.shapeIndex];
    if (liveUrl && liveUrl !== editing.displayImageUrl) {
      editing.displayImageUrl = liveUrl;
    }
  }
}

function releaseInsertedImageBlob() {
  if (insertedImageBlobUrl) {
    URL.revokeObjectURL(insertedImageBlobUrl);
    insertedImageBlobUrl = null;
  }
}

function markPictureLayoutDirty() {
  lastPictureMutationAt.value = Date.now();
}

function applySlidePreviewPatch(
  slide: { previewUrl?: string; thumbnailUrl?: string; page?: number },
  previewUrl?: string,
  confirmSync = false,
  previewUpdatedAt = 0,
  trustPending = false
): boolean {
  if (!previewUrl || !confirmSync) return false;
  const mutationAt = lastPictureMutationAt.value;
  const previewIsFresh =
    trustPending ||
    (previewUpdatedAt <= 0
      ? mutationAt <= 0
      : previewUpdatedAt >= mutationAt - 1500);
  if (!previewIsFresh) return false;

  const nextUrl = appendCacheBust(resolveAssetUrl(previewUrl));
  slide.previewUrl = nextUrl;
  slide.thumbnailUrl = appendCacheBust(nextUrl.replace("/page-", "/thumb-"));
  lastPreviewPatchAt.value = Date.now();
  if (slide.page != null && currentSlide.value?.page === slide.page) {
    orphanStalePreviewCovers.value = [];
  }
  if (slide.page != null) {
    touchPagePreviewSyncInCache(slide.page, lastPreviewPatchAt.value);
  }
  return true;
}

async function fetchPagePreviewMeta(page: number) {
  if (!store.currentFileId) {
    return { previewUrl: "", previewUpdatedAt: 0 };
  }
  try {
    const detail = await getFileDetail(store.baseUrl, store.currentFileId);
    const pageDetail = detail.pages_detail.find((item) => item.page === page);
    return {
      previewUrl: pageDetail?.preview_url || "",
      previewUpdatedAt: Number(pageDetail?.preview_updated_at || 0),
    };
  } catch {
    return { previewUrl: "", previewUpdatedAt: 0 };
  }
}

function previewMetaLooksFresh(meta: { previewUrl: string; previewUpdatedAt: number }, sawPending: boolean) {
  if (!meta.previewUrl) return false;
  const mutationAt = lastPictureMutationAt.value;
  if (sawPending) return true;
  if (meta.previewUpdatedAt > 0) return meta.previewUpdatedAt >= mutationAt;
  return mutationAt <= 0;
}

async function refreshSlidePreviewFromServer(page: number, confirmSync = false, trustPending = false) {
  if (!store.currentFileId) return false;
  const slide = store.slides.find((item) => item.page === page);
  if (!slide) return false;
  try {
    const detail = await getFileDetail(store.baseUrl, store.currentFileId);
    const pageDetail = detail.pages_detail.find((item) => item.page === page);
    if (!pageDetail?.preview_url) return false;
    const previewUpdatedAt = Number(pageDetail.preview_updated_at || 0);
    if (confirmSync) {
      return applySlidePreviewPatch(
        slide,
        pageDetail.preview_url,
        true,
        previewUpdatedAt,
        trustPending
      );
    }
    return true;
  } catch {
    return false;
  }
}

function enqueueSlidePreviewRefresh(page: number): Promise<boolean> {
  const existing = previewRefreshInflight.get(page);
  if (existing) return existing;
  const job = waitForSlidePreviewRefresh(page).finally(() => {
    previewRefreshInflight.delete(page);
  });
  previewRefreshInflight.set(page, job);
  return job;
}

async function waitForSlidePreviewRefresh(page: number, maxAttempts = 60) {
  if (!store.currentFileId) return false;
  const slide = store.slides.find((item) => item.page === page);
  if (!slide) return false;

  let sawPending = false;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, attempt === 0 ? 800 : 1000));
    const meta = await fetchPagePreviewMeta(page);
    if (!meta.previewUrl) {
      sawPending = true;
      continue;
    }
    if (!previewMetaLooksFresh(meta, sawPending)) continue;

    const patched = await refreshSlidePreviewFromServer(page, true, sawPending);
    if (patched) {
      rememberPagePicturesCache(page);
      return true;
    }
  }

  return previewLooksSynced();
}

function scheduleSlidePreviewRefresh(page: number) {
  if (insertedEditDraft.value && currentSlide.value?.page === page) {
    pendingPreviewRefreshPage.value = page;
    return;
  }
  void enqueueSlidePreviewRefresh(page);
}

function runSlidePreviewRefresh(page: number) {
  void enqueueSlidePreviewRefresh(page);
}

function flushPendingPreviewRefresh() {
  const page = pendingPreviewRefreshPage.value;
  if (page == null) return;
  pendingPreviewRefreshPage.value = null;
  void enqueueSlidePreviewRefresh(page);
}

function pictureAtNormalizedPoint(
  x: number,
  y: number,
  pictures: PptPagePicture[] = pagePictures.value
) {
  let hit: PptPagePicture | null = null;
  for (const pic of pictures) {
    const pad = 0.03;
    const left = pic.x - pad;
    const top = pic.y - pad;
    const right = pic.x + pic.width + pad;
    const bottom = pic.y + pic.height + pad;
    if (x < left || x > right || y < top || y > bottom) continue;
    if (!hit || pic.shape_index > hit.shape_index) hit = pic;
  }
  return hit;
}

function shellPointFromEvent(event: PointerEvent, shell: HTMLElement) {
  const rect = shell.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  return {
    x: (event.clientX - rect.left) / rect.width,
    y: (event.clientY - rect.top) / rect.height,
  };
}

async function trySelectPictureAtShellPoint(event: PointerEvent, shell: HTMLElement) {
  if (!canInsertPpt.value || pptInsertActive.value || insertedEditDraft.value) return;
  const target = event.target as HTMLElement | null;
  if (target?.closest(".ppt-insert-overlay, .ppt-insert-box, .ppt-passive-picture-btn")) return;

  const point = shellPointFromEvent(event, shell);
  if (!point) return;

  await ensurePagePicturesLoaded();

  const pictures = pagePictures.value.length ? pagePictures.value : passivePicturesForLayer.value;
  const hit = pictureAtNormalizedPoint(point.x, point.y, pictures);
  if (!hit) return;

  event.preventDefault();
  event.stopPropagation();
  void selectInsertedPicture(hit.shape_index);
}

function onSlideShellPointerDown(event: PointerEvent) {
  const shell = event.currentTarget as HTMLElement;
  const slideEl = shell.closest(".flow-slide") as HTMLElement | null;
  const idx = Number(slideEl?.dataset.slideIndex);
  if (!Number.isFinite(idx) || idx !== store.currentIndex) return;
  void trySelectPictureAtShellPoint(event, shell);
}

function onPassiveLayerPointerDown(event: PointerEvent) {
  const shell = (event.currentTarget as HTMLElement).parentElement;
  if (!shell) return;
  void trySelectPictureAtShellPoint(event, shell);
}

async function loadPagePictures() {
  const slide = currentSlide.value;
  if (!canInsertPpt.value || !store.currentFileId || !slide) {
    pagePictures.value = [];
    releasePagePictureBlobs();
    return;
  }

  const targetPage = slide.page;
  if (pagePicturesInflight && pagePicturesInflightPage === targetPage) {
    await pagePicturesInflight;
    return;
  }

  const requestId = ++pagePicturesRequestId;
  pagePicturesInflightPage = targetPage;
  pagePicturesInflight = (async () => {
    try {
      const resp = await listPageImages(store.baseUrl, {
        file_id: store.currentFileId!,
        page: targetPage,
      });
      if (requestId !== pagePicturesRequestId) return;
      if (currentSlide.value?.page !== targetPage) return;

      pagePictures.value = mergeServerPagePictures(resp.pictures);
      purgeStaleOptimisticFromState();
      slideAspectForPictures.value =
        resp.page_width && resp.page_height
          ? resp.page_width / resp.page_height
          : currentSlideAspect.value;
      if (insertedEditDraft.value) {
        const editing = insertedEditDraft.value;
        if (editing.shapeIndex < 0) {
          ensureOptimisticPictureOnPage(editing);
        } else {
          const pic = pagePictures.value.find((item) => item.shape_index === editing.shapeIndex);
          if (!pic && !insertWriteInFlight.value) {
            deselectInsertedPicture();
          }
        }
      }
      reconcilePictureSelection();
      rememberPagePicturesCache(targetPage);
      void hydratePagePictureBlobs(targetPage, pagePictures.value, requestId).then(() => {
        if (requestId === pagePicturesRequestId && currentSlide.value?.page === targetPage) {
          rememberPagePicturesCache(targetPage);
        }
      });
    } catch {
      if (requestId !== pagePicturesRequestId) return;
      if (
        !insertedEditDraft.value &&
        !insertWriteInFlight.value &&
        currentSlide.value?.page === targetPage
      ) {
        pagePictures.value = [];
        releasePagePictureBlobs();
        deselectInsertedPicture();
      }
    } finally {
      if (pagePicturesInflightPage === targetPage) {
        pagePicturesInflight = null;
      }
    }
  })();

  await pagePicturesInflight;
}

function reconcileInsertPicture(tempShapeIndex: number, picture: PptPagePicture) {
  invalidateInflightPagePicturesLoad();
  const cachedUrl = pagePictureBlobUrls.value[tempShapeIndex];
  pagePictures.value = [
    ...pagePictures.value.filter(
      (item) => item.shape_index !== tempShapeIndex && item.shape_index !== picture.shape_index
    ),
    picture,
  ];
  pagePictures.value = stripStaleOptimisticPictures(pagePictures.value);
  if (cachedUrl) {
    const next = { ...pagePictureBlobUrls.value };
    delete next[tempShapeIndex];
    next[picture.shape_index] = cachedUrl;
    pagePictureBlobUrls.value = next;
  } else {
    revokePagePictureBlob(tempShapeIndex);
  }
  if (insertedEditDraft.value?.shapeIndex === tempShapeIndex) {
    insertedEditDraft.value.shapeIndex = picture.shape_index;
    selectedShapeIndex.value = picture.shape_index;
    const liveUrl = pagePictureBlobUrls.value[picture.shape_index];
    if (liveUrl) {
      insertedEditDraft.value.displayImageUrl = liveUrl;
    }
    const livePlacement =
      pendingInsertPlacementSave.value ||
      (insertedEditDraft.value.placement ? { ...insertedEditDraft.value.placement } : null);
    if (livePlacement) {
      insertedEditDraft.value.placement = { ...livePlacement };
      insertedEditSavedPlacement.value = { ...livePlacement };
      syncPagePicturePlacement(picture.shape_index, livePlacement);
      const synced = pagePictures.value.find((item) => item.shape_index === picture.shape_index);
      if (synced) {
        synced.x = livePlacement.x;
        synced.y = livePlacement.y;
        synced.width = livePlacement.width;
        synced.height = livePlacement.height;
      }
    } else {
      insertedEditDraft.value.placement = {
        x: picture.x,
        y: picture.y,
        width: picture.width,
        height: picture.height,
      };
      insertedEditSavedPlacement.value = { ...insertedEditDraft.value.placement };
    }
  }
  const slide = currentSlide.value;
  if (slide) rememberPagePicturesCache(slide.page);
  void flushPendingInsertPlacementSave(picture);
}

async function flushPendingInsertPlacementSave(picture: PptPagePicture) {
  const pending = pendingInsertPlacementSave.value;
  if (!pending) return;
  pendingInsertPlacementSave.value = null;

  const baseline = {
    x: picture.x,
    y: picture.y,
    width: picture.width,
    height: picture.height,
  };
  const moved =
    Math.abs(baseline.x - pending.x) > 0.001 ||
    Math.abs(baseline.y - pending.y) > 0.001 ||
    Math.abs(baseline.width - pending.width) > 0.001 ||
    Math.abs(baseline.height - pending.height) > 0.001;
  if (!moved) return;

  const slide = currentSlide.value;
  if (!slide || !store.currentFileId) return;

  try {
    const result = await updatePptImagePlacement(store.baseUrl, {
      file_id: store.currentFileId,
      page: slide.page,
      shape_index: picture.shape_index,
      placement: pending,
    });
    markPictureLayoutDirty();
    scheduleSlidePreviewRefresh(slide.page);
    syncPagePicturePlacement(picture.shape_index, pending);
    if (insertedEditDraft.value?.shapeIndex === picture.shape_index) {
      insertedEditDraft.value.placement = { ...pending };
      insertedEditSavedPlacement.value = { ...pending };
    }
    rememberPagePicturesCache(slide.page);
  } catch (e: any) {
    store.addLog(`写入后同步配图位置失败：${e?.message || String(e)}`);
  }
}

function registerPagePictureAfterInsert(
  picture: PptPagePicture,
  displayImageUrl: string,
  slideAspect: number
) {
  invalidateInflightPagePicturesLoad();
  pagePictures.value = [
    ...pagePictures.value.filter((item) => item.shape_index !== picture.shape_index),
    picture,
  ];
  pagePictureBlobUrls.value = {
    ...pagePictureBlobUrls.value,
    [picture.shape_index]: displayImageUrl,
  };
  slideAspectForPictures.value = slideAspect;
  const slide = currentSlide.value;
  if (slide) rememberPagePicturesCache(slide.page);
}

async function selectInsertedPicture(shapeIndex: number) {
  const slide = currentSlide.value;
  if (!slide || !store.currentFileId || pptInsertActive.value) return;
  if (selectedShapeIndex.value === shapeIndex && insertedEditDraft.value) return;

  if (insertedEditDraft.value && selectedShapeIndex.value !== shapeIndex) {
    await saveInsertedPictureEdit();
  }

  if (!isShapeIndexOnPage(shapeIndex)) {
    await loadPagePictures();
  }

  const pic = pagePictures.value.find((item) => item.shape_index === shapeIndex);
  if (!pic) return;

  clearRegionSelection(false);
  const cachedUrl = pagePictureBlobUrls.value[shapeIndex] || "";
  enterPictureEditMode(pic, shapeIndex, cachedUrl);

  if (cachedUrl) return;

  const selectId = ++pictureSelectRequestId;
  releaseInsertedImageBlob();
  try {
    const displayImageUrl = await fetchPptShapeImageBlobUrl(store.baseUrl, {
      file_id: store.currentFileId,
      page: slide.page,
      shape_index: shapeIndex,
    });
    if (selectId !== pictureSelectRequestId) return;
    if (insertedEditDraft.value?.shapeIndex !== shapeIndex) return;
    insertedImageBlobUrl = displayImageUrl;
    insertedEditDraft.value.displayImageUrl = displayImageUrl;
    pagePictureBlobUrls.value = {
      ...pagePictureBlobUrls.value,
      [shapeIndex]: displayImageUrl,
    };
    rememberPagePicturesCache(slide.page);
  } catch (e: any) {
    if (selectId !== pictureSelectRequestId) return;
    store.addLog(`加载配图失败：${e?.message || String(e)}`);
  }
}

function deselectInsertedPicture() {
  pictureSelectRequestId += 1;
  releaseInsertedImageBlob();
  insertedEditDraft.value = null;
  insertedEditSavedPlacement.value = null;
  selectedShapeIndex.value = null;
  flushPendingPreviewRefresh();
}

async function finishPictureEdit() {
  if (pptInsertSaving.value || insertedEditSaving.value) return;
  const slide = currentSlide.value;
  if (insertedEditDraft.value) {
    await saveInsertedPictureEdit();
  }
  deselectInsertedPicture();
  if (slide) {
    rememberPagePicturesCache(slide.page);
    if (!previewLooksSynced()) {
      insertFeedback.value = "正在后台刷新幻灯片预览...";
      void enqueueSlidePreviewRefresh(slide.page).then(() => {
        if (currentSlide.value?.page !== slide.page) return;
        void loadPagePictures().then(() => rememberPagePicturesCache(slide.page));
        insertFeedback.value = "";
      });
    } else {
      orphanStalePreviewCovers.value = [];
      rememberPagePicturesCache(slide.page);
    }
  }
}

async function saveInsertedPictureEdit() {
  const draft = insertedEditDraft.value;
  const slide = currentSlide.value;
  if (!draft || !slide || !store.currentFileId || insertedEditSaving.value || pptInsertActive.value) return;

  insertedEditSaving.value = true;
  try {
    const placement = clampPlacementRect(draft.placement, draft.aspectRatio, draft.slideAspect);
    if (draft.shapeIndex < 0) {
      pendingInsertPlacementSave.value = { ...placement };
      syncPagePicturePlacement(draft.shapeIndex, placement);
      if (insertedEditDraft.value) {
        insertedEditDraft.value.placement = { ...placement };
        insertedEditSavedPlacement.value = { ...placement };
      }
      rememberPagePicturesCache(slide.page);
      return;
    }

    const previousPlacement = insertedEditSavedPlacement.value
      ? { ...insertedEditSavedPlacement.value }
      : { ...placement };
    const moved =
      Math.abs(previousPlacement.x - placement.x) > 0.001 ||
      Math.abs(previousPlacement.y - placement.y) > 0.001 ||
      Math.abs(previousPlacement.width - placement.width) > 0.001 ||
      Math.abs(previousPlacement.height - placement.height) > 0.001;

    const result = await updatePptImagePlacement(store.baseUrl, {
      file_id: store.currentFileId,
      page: slide.page,
      shape_index: draft.shapeIndex,
      placement,
    });
    if (moved) {
      markPictureLayoutDirty();
      rememberOrphanStalePreviewRegion(previousPlacement);
    }
    scheduleSlidePreviewRefresh(slide.page);
    syncPagePicturePlacement(draft.shapeIndex, placement);
    if (insertedEditDraft.value) {
      insertedEditDraft.value.placement = { ...placement };
      insertedEditSavedPlacement.value = { ...placement };
    }
    rememberPagePicturesCache(slide.page);
    store.addLog(`第 ${slide.page} 页配图位置已保存`);
  } catch (e: any) {
    const message = e?.message || String(e);
    insertFeedback.value = `保存配图位置失败：${message}`;
    store.addLog(`更新配图失败：${message}`);
  } finally {
    insertedEditSaving.value = false;
  }
}

function syncPagePicturePlacement(shapeIndex: number, placement: NormalizedRect) {
  const pic = pagePictures.value.find((item) => item.shape_index === shapeIndex);
  if (!pic) return;
  pic.x = placement.x;
  pic.y = placement.y;
  pic.width = placement.width;
  pic.height = placement.height;
}

async function deleteInsertedPicture() {
  const draft = insertedEditDraft.value;
  const slide = currentSlide.value;
  if (!draft || !slide || !store.currentFileId) return;

  const shapeIndex = draft.shapeIndex;
  const deletedPlacement = { ...draft.placement };

  deselectInsertedPicture();
  rememberOrphanStalePreviewRegion(deletedPlacement);
  markPictureLayoutDirty();
  pagePictures.value = pagePictures.value.filter((item) => item.shape_index !== shapeIndex);
  revokePagePictureBlob(shapeIndex);
  rememberPagePicturesCache(slide.page);

  insertedEditSaving.value = true;
  try {
    const result = await removePptImage(store.baseUrl, {
      file_id: store.currentFileId,
      page: slide.page,
      shape_index: shapeIndex,
    });
    if (!result.removed) {
      orphanStalePreviewCovers.value = [];
      rememberPagePicturesCache(slide.page);
      store.addLog(result.message || `第 ${slide.page} 页未找到指定配图，已刷新列表`);
      await loadPagePictures();
      return;
    }
    rememberPagePicturesCache(slide.page);
    store.addLog(result.message || `第 ${slide.page} 页配图已删除`);
    insertFeedback.value = "正在刷新幻灯片预览...";
    void enqueueSlidePreviewRefresh(slide.page).then((synced) => {
      if (currentSlide.value?.page !== slide.page) return;
      void loadPagePictures().then(() => rememberPagePicturesCache(slide.page));
      insertFeedback.value = synced ? "" : "预览刷新较慢，已保留遮罩直至同步完成";
    });
  } catch (e: any) {
    store.addLog(`删除配图失败：${e?.message || String(e)}`);
    orphanStalePreviewCovers.value = [];
    rememberPagePicturesCache(slide.page);
    await loadPagePictures();
  } finally {
    insertedEditSaving.value = false;
  }
}

async function beginInlineInsert(input: {
  imageUrl: string;
  aspectRatio: string;
  source: "flux" | "chart";
}) {
  const slide = currentSlide.value;
  if (!slide || !store.currentFileId) return;
  if (!canInsertPpt.value) {
    store.addLog("仅支持 .pptx 文件插入配图/图表");
    return;
  }

  pptInsertLoading.value = true;
  insertFeedback.value = "";
  clearRegionSelection(false);
  deselectInsertedPicture();
  try {
    const displayImageUrl = await resolveInsertImageUrl(input.imageUrl);
    const resp = await recommendPptPlacement(store.baseUrl, {
      file_id: store.currentFileId,
      page: slide.page,
      image_url: input.imageUrl,
      aspect_ratio: input.aspectRatio,
    });
    const slideAspect =
      resp.page_width && resp.page_height ? resp.page_width / resp.page_height : 16 / 9;
    pptInsertActive.value = {
      slideIndex: store.currentIndex,
      page: slide.page,
      imageUrl: input.imageUrl,
      displayImageUrl,
      aspectRatio: input.aspectRatio,
      slideAspect,
      placement: clampPlacementRect(resp.recommended, input.aspectRatio, slideAspect),
      source: input.source,
    };
    destroyFlowObserver();
    await nextTick();
    scrollToSlide(store.currentIndex);
    store.addLog(`第 ${slide.page} 页：拖动移动 · 拖四角等比缩放 · 点 × 或按 Delete 删除 · 右侧确认插入（${input.aspectRatio}）`);
  } catch (e: any) {
    store.addLog(`插入预览失败：${e?.message || String(e)}`);
  } finally {
    pptInsertLoading.value = false;
  }
}

function cancelPptInsert() {
  pptInsertActive.value = null;
  insertFeedback.value = "";
  nextTick(() => setupFlowObserver());
  store.addLog("已取消插入，配图未写入 PPT");
}

async function undoLastPptInsert() {
  const slide = currentSlide.value;
  if (!slide || !store.currentFileId || pptUndoLoading.value || pptInsertActive.value) return;

  pptUndoLoading.value = true;
  try {
    const positivePictures = pagePictures.value.filter((item) => item.shape_index >= 0);
    const lastPic =
      positivePictures.length > 0
        ? positivePictures.reduce((best, item) => (item.shape_index > best.shape_index ? item : best))
        : null;

    const result = await removeLastPptImage(store.baseUrl, {
      file_id: store.currentFileId,
      page: slide.page,
    });
    deselectInsertedPicture();
    if (result.removed && lastPic) {
      rememberOrphanStalePreviewRegion({
        x: lastPic.x,
        y: lastPic.y,
        width: lastPic.width,
        height: lastPic.height,
      });
      pagePictures.value = pagePictures.value
        .filter((item) => item.shape_index >= 0 && item.shape_index !== lastPic.shape_index);
      revokePagePictureBlob(lastPic.shape_index);
    } else {
      orphanStalePreviewCovers.value = [];
      pagePictures.value = pagePictures.value.filter((item) => item.shape_index >= 0);
    }
    rememberPagePicturesCache(slide.page);
    if (result.removed) {
      markPictureLayoutDirty();
      void enqueueSlidePreviewRefresh(slide.page).then(() => {
        if (currentSlide.value?.page !== slide.page) return;
        void loadPagePictures().then(() => rememberPagePicturesCache(slide.page));
      });
    } else {
      await loadPagePictures();
    }
    store.addLog(result.message || (result.removed ? `第 ${slide.page} 页配图已撤销` : `第 ${slide.page} 页没有可撤销的配图`));
  } catch (e: any) {
    store.addLog(`撤销配图失败：${e?.message || String(e)}`);
  } finally {
    pptUndoLoading.value = false;
  }
}

async function confirmPptInsert() {
  const draft = pptInsertActive.value;
  const slide = currentSlide.value;
  if (!draft || !slide || !store.currentFileId) {
    insertFeedback.value = "无法确认插入，请重新点击「插入到 PPT」";
    return;
  }
  if (draft.slideIndex !== store.currentIndex) {
    insertFeedback.value = "当前页已切换，请重新点击「插入到 PPT」";
    pptInsertActive.value = null;
    nextTick(() => setupFlowObserver());
    return;
  }
  if (pptInsertSaving.value || insertWriteInFlight.value) return;

  const placement = clampPlacementRect(draft.placement, draft.aspectRatio, draft.slideAspect);
  const tempShapeIndex = -Date.now();
  const optimisticPicture: PptPagePicture = {
    shape_index: tempShapeIndex,
    x: placement.x,
    y: placement.y,
    width: placement.width,
    height: placement.height,
    aspect_ratio: draft.aspectRatio,
  };

  insertFeedback.value = "正在写入 PPT...";
  pptInsertSaving.value = true;
  insertWriteInFlight.value = true;
  registerPagePictureAfterInsert(optimisticPicture, draft.displayImageUrl, draft.slideAspect);
  enterPictureEditMode(optimisticPicture, tempShapeIndex, draft.displayImageUrl);
  pptInsertActive.value = null;
  pptInsertSaving.value = false;
  insertFeedback.value = "正在后台写入 PPT…";
  nextTick(() => setupFlowObserver());

  try {
    const result = await insertPptImage(store.baseUrl, {
      file_id: store.currentFileId,
      page: slide.page,
      image_url: draft.imageUrl,
      placement,
    });

    insertWriteInFlight.value = false;

    markPictureLayoutDirty();
    const savedPicture = await resolveInsertedPictureFromResult(slide.page, optimisticPicture, result);
    reconcileInsertPicture(tempShapeIndex, savedPicture);
    purgeStaleOptimisticFromState();
    rememberPagePicturesCache(slide.page);
    insertFeedback.value = "配图已写入 PPT，点击配图可删除";
    store.addLog(result.message || `第 ${slide.page} 页配图已写入 PPT，点击配图可删除`);
    window.setTimeout(() => {
      if (insertFeedback.value === "配图已写入 PPT，点击配图可删除") insertFeedback.value = "";
    }, 4000);
    void enqueueSlidePreviewRefresh(slide.page).then(() => {
      if (currentSlide.value?.page !== slide.page) return;
      void loadPagePictures().then(() => rememberPagePicturesCache(slide.page));
    });
  } catch (e: any) {
    pendingInsertPlacementSave.value = null;
    if (insertedEditDraft.value?.shapeIndex === tempShapeIndex) {
      deselectInsertedPicture();
    }
    pagePictures.value = pagePictures.value.filter((item) => item.shape_index !== tempShapeIndex);
    revokePagePictureBlob(tempShapeIndex);
    const slideNow = currentSlide.value;
    if (slideNow) rememberPagePicturesCache(slideNow.page);
    const message = e?.message || String(e);
    insertFeedback.value = `插入失败：${message}`;
    store.addLog(`插入失败：${message}`);
  } finally {
    insertWriteInFlight.value = false;
  }
}

function startInsertSession(input: {
  imageUrl: string;
  aspectRatio: string;
  source: "flux" | "chart";
}) {
  void beginInlineInsert(input);
}

async function onInsertToPpt(payload: { aspectRatio: string }) {
  const slide = currentSlide.value;
  if (!slide?.fluxImage?.resultImageUrl || !store.currentFileId) return;
  try {
    const imageUrl = await stageRemoteImageForInsert(slide.fluxImage.resultImageUrl);
    startInsertSession({
      imageUrl,
      aspectRatio: payload.aspectRatio || "16:9",
      source: "flux",
    });
  } catch (e: any) {
    store.addLog(`配图暂存失败：${e?.message || String(e)}`);
  }
}

async function onInsertChartToPpt(payload: { dataUrl: string; aspectRatio: string }) {
  if (!store.currentFileId) return;
  try {
    const staged = await stagePptImage(store.baseUrl, {
      file_id: store.currentFileId,
      image_data: payload.dataUrl,
    });
    startInsertSession({
      imageUrl: staged.image_url,
      aspectRatio: payload.aspectRatio || "4:3",
      source: "chart",
    });
  } catch (e: any) {
    store.addLog(`图表暂存失败：${e?.message || String(e)}`);
  }
}

async function onGlobalInsertToPpt() {
  if (globalInsertTarget.value === "chart") {
    await triggerChartInsertFromHead();
    return;
  }
  if (globalInsertTarget.value === "flux") {
    triggerFluxInsertFromHead();
  }
}

async function triggerChartInsertFromHead() {
  let exported = await chartCodePanelRef.value?.exportChartPngDataUrl?.();
  if (!exported) {
    const slide = currentSlide.value;
    const option = slide?.chartCode?.echartsOption || slide?.analyze?.chart?.echartsOption;
    if (option) {
      exported = await exportEchartsOptionToPng(option);
    }
  }
  if (!exported) {
    store.addLog("请先在「数据图表」中生成可预览的图表");
    return;
  }
  await onInsertChartToPpt(exported);
}

function triggerFluxInsertFromHead() {
  const slide = currentSlide.value;
  if (!slide?.fluxImage?.resultImageUrl) {
    store.addLog("请先在「文生图插图」中生成配图");
    return;
  }
  const aspectRatio = slide.fluxAspectRatio ||
    (illustrationPanelRef.value as { getAspectRatio?: () => string } | null)?.getAspectRatio?.() ||
    "16:9";
  onInsertToPpt({ aspectRatio });
}

function applyInsertPatch() {
  const raw = sessionStorage.getItem(INSERT_PATCH_KEY);
  if (!raw) return;
  sessionStorage.removeItem(INSERT_PATCH_KEY);
  try {
    const patch = JSON.parse(raw) as {
      fileId: number;
      page: number;
      previewUrl?: string;
      thumbnailUrl?: string;
    };
    if (!patch.fileId || patch.fileId !== store.currentFileId) return;
    const slide = store.slides.find((item) => item.page === patch.page);
    if (!slide) return;
    if (patch.previewUrl) slide.previewUrl = patch.previewUrl;
    if (patch.thumbnailUrl) slide.thumbnailUrl = patch.thumbnailUrl;
    store.addLog(`第 ${patch.page} 页预览已更新（配图已写入 PPT）`);
  } catch {
    /* ignore invalid patch */
  }
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
    if (targetSlide) {
      targetSlide.fluxAspectRatio = payload.aspect_ratio || "16:9";
    }

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
  (_newIdx, oldIdx) => {
    if (oldIdx >= 0 && oldIdx < store.slides.length) {
      const outgoing = store.slides[oldIdx];
      if (outgoing) rememberPagePicturesCache(outgoing.page);
    }
    if (pptInsertActive.value && pptInsertActive.value.slideIndex !== store.currentIndex) {
      pptInsertActive.value = null;
      insertFeedback.value = "";
      nextTick(() => setupFlowObserver());
    }
    deselectInsertedPicture();
    clearRegionSelection();
    const slide = currentSlide.value;
    if (slide) {
      applyPagePicturesCache(slide.page);
    } else {
      pagePictures.value = [];
      releasePagePictureBlobs();
      orphanStalePreviewCovers.value = [];
    }
    void loadPagePictures();
    nextTick(() => scrollCurrentThumbIntoView());
  },
);

watch(
  () => store.currentFileId,
  () => {
    pendingPreviewRefreshPage.value = null;
    clearPagePicturesCache();
    deselectInsertedPicture();
    orphanStalePreviewCovers.value = [];
    void loadPagePictures();
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
  applyInsertPatch();
  const slide = currentSlide.value;
  if (slide) applyPagePicturesCache(slide.page);
  void loadPagePictures();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", previewKeydownSplitAware);
  window.removeEventListener("resize", onWindowResize);
  endSplitDrag();
  endCurrentInputResize();
  destroyFlowObserver();
  deselectInsertedPicture();
  releasePagePictureBlobs();
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
                  <label class="tb-page-jump" title="输入页码后按回车跳转">
                    <span>第</span>
                    <input
                      class="tb-page-input"
                      type="number"
                      min="1"
                      :max="store.slides.length"
                      :value="store.currentIndex + 1"
                      @change="onPageNumberInput"
                      @keydown.enter.prevent="onPageNumberInput"
                    />
                    <span>/ {{ store.slides.length }} 页</span>
                  </label>
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
            <button
              v-if="canInsertPpt"
              type="button"
              class="reader-action-btn export-ppt-trigger"
              title="预览并导出 PPT / PDF"
              aria-label="导出文档"
              @click="exportCurrentPpt"
            >
              导出
            </button>
            <p
              v-if="canInsertPpt && insertFeedback"
              class="reader-insert-feedback"
              :class="{ error: insertFeedback.startsWith('插入失败') || insertFeedback.startsWith('无法') || insertFeedback.startsWith('当前页') || insertFeedback.startsWith('加载配图') }"
            >
              {{ insertFeedback }}
            </p>
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
                <div
                  v-if="s.previewUrl"
                  class="slide-image-shell"
                  :class="{
                    'slide-image-shell--has-pictures':
                      canInsertPpt && i === store.currentIndex,
                  }"
                  :style="i === store.currentIndex && currentSlideAspect ? { aspectRatio: `${currentSlideAspect}` } : undefined"
                  @pointerdown="onSlideShellPointerDown"
                >
                  <img
                    class="slide-preview-img"
                    :key="`preview-${s.page}`"
                    :src="s.previewUrl"
                    :alt="s.input.topic"
                    :loading="i === store.currentIndex ? 'eager' : 'lazy'"
                  />
                  <div
                    v-if="canInsertPpt && i === store.currentIndex && pngBakedMaskRects.length"
                    class="ppt-picture-mask-layer"
                  >
                    <div
                      v-for="(rect, coverIndex) in pngBakedMaskRects"
                      :key="`baked-mask-${coverIndex}`"
                      class="ppt-stale-preview-cover"
                      :style="{
                        left: `${rect.x * 100}%`,
                        top: `${rect.y * 100}%`,
                        width: `${rect.width * 100}%`,
                        height: `${rect.height * 100}%`,
                      }"
                    />
                  </div>
                  <div
                    v-if="canInsertPpt && !pptInsertActive && i === store.currentIndex && showPassivePictureLayer"
                    class="ppt-passive-picture-layer"
                    @pointerdown="onPassiveLayerPointerDown"
                  >
                    <!-- passivePictureShowsImage 仅控制浮动图，不控制本层 v-if -->
                    <button
                      v-for="(pic, picIndex) in passivePicturesForLayer"
                      :key="`passive-${pic.shape_index}`"
                      type="button"
                      class="ppt-passive-picture-btn"
                      :class="{
                        'ppt-passive-picture-btn--synced-hit':
                          previewLooksSynced() &&
                          !insertedEditDraft &&
                          orphanStalePreviewCovers.length === 0,
                      }"
                      :style="{
                        left: `${pic.x * 100}%`,
                        top: `${pic.y * 100}%`,
                        width: `${pic.width * 100}%`,
                        height: `${pic.height * 100}%`,
                        zIndex: 10 + picIndex,
                      }"
                      :title="`点击编辑配图 ${pic.shape_index + 1}`"
                      @pointerdown.stop.prevent="selectInsertedPicture(pic.shape_index)"
                      @click.stop.prevent="selectInsertedPicture(pic.shape_index)"
                    >
                      <img
                        v-if="shouldShowPassiveFloat(pic) && pagePictureBlobUrls[pic.shape_index]"
                        class="ppt-passive-picture-img"
                        :src="pagePictureBlobUrls[pic.shape_index]"
                        :alt="`配图 ${pic.shape_index + 1}`"
                        draggable="false"
                      />
                    </button>
                  </div>
                  <SlidePptInsertOverlay
                    v-if="insertedEditDraft && !pptInsertActive && i === store.currentIndex"
                    v-model:placement="insertedEditDraft.placement"
                    :image-url="insertedEditDraft.displayImageUrl"
                    :aspect-ratio="insertedEditDraft.aspectRatio"
                    :slide-aspect="insertedEditDraft.slideAspect"
                    label="已插入配图"
                    :movable="false"
                    :show-image="overlayShowsFloatImage"
                    :saving="insertWriteInFlight"
                    @remove="deleteInsertedPicture"
                  />
                  <SlidePptInsertOverlay
                    v-if="pptInsertActive && i === store.currentIndex"
                    v-model:placement="pptInsertActive.placement"
                    :image-url="pptInsertActive.displayImageUrl"
                    :aspect-ratio="pptInsertActive.aspectRatio"
                    :slide-aspect="pptInsertActive.slideAspect"
                    :label="pptInsertActive.source === 'flux' ? 'AI 配图' : '数据图表'"
                    :saving="pptInsertSaving"
                    @remove="cancelPptInsert"
                  />
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
              <div v-if="canInsertPpt" class="action-top-insert">
                <p v-if="insertFeedback" class="action-insert-feedback" :class="{ error: insertFeedback.startsWith('插入失败') || insertFeedback.startsWith('无法') || insertFeedback.startsWith('当前页') }">
                  {{ insertFeedback }}
                </p>
                <template v-if="pptInsertActive">
                  <span class="action-insert-hint">拖动移动 · 拖角缩放 · × 删除</span>
                  <button type="button" class="action-insert-btn outline" :disabled="pptInsertSaving" @click.stop="cancelPptInsert">
                    取消
                  </button>
                  <button
                    type="button"
                    class="action-insert-btn solid"
                    :disabled="pptInsertSaving"
                    @click.stop="confirmPptInsert"
                  >
                    <span v-if="pptInsertSaving" class="btn-spinner wine-spin"></span>
                    {{ pptInsertSaving ? "写入中..." : "确认插入" }}
                  </button>
                </template>
                <template v-else-if="insertedEditDraft">
                  <span class="action-insert-hint">
                    {{ insertWriteInFlight ? "正在后台写入 PPT…" : "已选中配图 · 点击 × 删除" }}
                  </span>
                  <button
                    type="button"
                    class="action-insert-btn outline"
                    :disabled="pptInsertSaving || insertedEditSaving"
                    @click.stop="finishPictureEdit"
                  >
                    <span v-if="insertedEditSaving" class="btn-spinner wine-spin"></span>
                    完成
                  </button>
                </template>
                <template v-else>
                  <span v-if="pagePictures.length" class="action-insert-hint">点击幻灯片中的配图可删除</span>
                  <button
                    type="button"
                    class="action-insert-btn outline"
                    :disabled="pptUndoLoading"
                    title="删除本页最后插入的一张配图"
                    aria-label="撤销本页配图"
                    @click="undoLastPptInsert"
                  >
                    <span v-if="pptUndoLoading" class="btn-spinner wine-spin"></span>
                    撤销配图
                  </button>
                  <button
                    type="button"
                    class="action-insert-btn outline"
                    :disabled="pptUndoLoading"
                    title="预览并导出 PPT / PDF"
                    aria-label="导出文档"
                    @click="exportCurrentPpt"
                  >
                    导出
                  </button>
                  <button
                    type="button"
                    class="action-insert-btn solid"
                    :class="{ ready: Boolean(globalInsertTarget) }"
                    :disabled="!globalInsertTarget || pptInsertLoading"
                    :title="globalInsertHint"
                    aria-label="插入到 PPT"
                    @click="onGlobalInsertToPpt"
                  >
                    <span v-if="pptInsertLoading" class="btn-spinner wine-spin"></span>
                    插入到 PPT
                  </button>
                </template>
              </div>
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
                  ref="chartCodePanelRef"
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
            ref="chartCodePanelRef"
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
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  max-width: min(560px, calc(100% - 96px));
}

.reader-insert-feedback {
  flex: 1 1 100%;
  margin: 0;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(74, 144, 255, 0.35);
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.4;
  box-shadow: var(--shadow-card);
}

.reader-insert-feedback.error {
  border-color: rgba(185, 28, 28, 0.35);
  color: #b91c1c;
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
.reader-action-btn:focus-visible {
  background: var(--color-primary-soft);
}

.reader-action-btn.insert-ppt-trigger.ready {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
}

.reader-action-btn.insert-ppt-trigger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  background: var(--color-surface);
  color: var(--color-muted);
  border-color: var(--color-border);
}

.reader-action-btn.export-ppt-trigger {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
}

.reader-action-btn.export-ppt-trigger:disabled {
  opacity: 0.55;
}
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
  width: 100%;
  max-width: 100%;
}

.ppt-passive-picture-layer {
  position: absolute;
  inset: 0;
  z-index: 7;
  pointer-events: auto;
  cursor: default;
  touch-action: manipulation;
}

.slide-image-shell--has-pictures .slide-preview-img {
  pointer-events: none;
  user-select: none;
}

.slide-image-shell--hide-stale-preview .slide-preview-img {
  visibility: hidden;
}

.slide-image-shell--hide-stale-preview {
  background: #fff;
}

.ppt-picture-mask-layer {
  position: absolute;
  inset: 0;
  z-index: 6;
  pointer-events: none;
}

.ppt-stale-preview-cover {
  position: absolute;
  box-sizing: border-box;
  z-index: 1;
  background: #fff;
  pointer-events: none;
}

.ppt-stale-preview-cover--edit {
  z-index: 2;
  box-shadow: inset 0 0 0 1px rgba(74, 144, 255, 0.08);
}

.ppt-passive-picture-btn {
  position: absolute;
  box-sizing: border-box;
  border: 1px dashed rgba(74, 144, 255, 0.35);
  background: transparent;
  padding: 0;
  margin: 0;
  cursor: pointer;
  touch-action: manipulation;
  overflow: hidden;
  pointer-events: auto;
}

.ppt-passive-picture-btn:hover,
.ppt-passive-picture-btn:focus-visible {
  border-color: rgba(74, 144, 255, 0.95);
  box-shadow: 0 0 0 1px rgba(74, 144, 255, 0.35), 0 8px 20px rgba(74, 144, 255, 0.18);
}

.ppt-passive-picture-btn--synced-hint {
  border-color: rgba(74, 144, 255, 0.72);
  border-width: 2px;
  background: rgba(74, 144, 255, 0.06);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.65);
  cursor: pointer;
  min-width: 28px;
  min-height: 28px;
}

.ppt-passive-picture-btn--synced-hit {
  border-color: transparent;
  background: transparent;
  box-shadow: none;
  cursor: pointer;
}

.ppt-passive-picture-btn--synced-hit:hover,
.ppt-passive-picture-btn--synced-hit:focus-visible {
  border-color: rgba(74, 144, 255, 0.72);
  border-width: 2px;
  background: rgba(74, 144, 255, 0.06);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.65);
}

.ppt-passive-picture-btn--synced-hint::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.ppt-passive-picture-img {
  width: 100%;
  height: 100%;
  object-fit: fill;
  display: block;
  pointer-events: none;
  background: #fff;
}

.flow-slide .slide-preview-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: var(--color-surface);
  border: 1px solid #d8d1d4;
  border-radius: 4px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
}

.flow-slide .slide-image-shell--has-pictures .slide-preview-img {
  object-fit: fill;
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

.tb-page,
.tb-page-jump {
  flex: 1 1 auto;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-soft);
  min-width: 0;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.tb-page-jump {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  white-space: nowrap;
}

.tb-page-input {
  width: 38px;
  height: 30px;
  padding: 0 4px;
  border: 1px solid var(--color-primary-border);
  border-radius: 8px;
  background: #fff;
  color: var(--color-text);
  font: inherit;
  font-weight: 800;
  text-align: center;
}

.tb-page-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(139, 41, 66, 0.1);
}

.tb-page-input::-webkit-outer-spin-button,
.tb-page-input::-webkit-inner-spin-button {
  margin: 0;
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  padding: 2px 0 4px;
}

.action-top-insert {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: auto;
  min-width: 0;
}

.action-insert-feedback {
  flex: 1 1 100%;
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary);
  line-height: 1.4;
}

.action-insert-feedback.error {
  color: #b91c1c;
}

.action-insert-hint {
  font-size: 11px;
  color: var(--color-muted);
  white-space: nowrap;
}

.action-insert-btn {
  min-width: 88px;
  height: 34px;
  padding: 0 12px;
  border-radius: var(--radius-control);
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
  border: 1px solid var(--color-primary-border);
  background: var(--color-surface);
  color: var(--color-primary);
  box-shadow: var(--shadow-card);
}

.action-insert-btn.solid {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
}

.action-insert-btn.outline:hover,
.action-insert-btn.outline:focus-visible {
  background: var(--color-primary-soft);
}

.action-insert-btn.solid.ready,
.action-insert-btn.solid:not(:disabled):hover,
.action-insert-btn.solid:not(:disabled):focus-visible {
  filter: brightness(1.03);
}

.action-insert-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  filter: none;
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
  margin-left: auto;
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

.workflow-panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.btn.primary.compact {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
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
