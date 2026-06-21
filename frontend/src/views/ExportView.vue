<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { exportDocumentFile, getFileDetail } from "../api/client";
import { store } from "../store";

type ExportFormat = "pptx" | "pdf";

const router = useRouter();
const exportFormat = ref<ExportFormat>("pptx");
const exportFilenameInput = ref("");
const exportLoading = ref(false);
const exportMessage = ref("");
const zoomPercent = ref(100);

const pageThumbRefs = ref<(HTMLElement | null)[]>([]);
let wheelDelta = 0;
let wheelResetTimer: number | null = null;
let lastWheelSwitchAt = 0;

const hasDoc = computed(() => store.slides.length > 0);
const isPptx = computed(() => (store.docName || "").toLowerCase().endsWith(".pptx"));
const currentSlide = computed(() => store.slides[store.currentIndex] || null);
const pageLabel = computed(() => `${store.currentIndex + 1} / ${store.slides.length}`);
const canPrev = computed(() => store.currentIndex > 0);
const canNext = computed(() => store.currentIndex < store.slides.length - 1);
const previewWidth = computed(() => `${zoomPercent.value}%`);

function defaultStem() {
  return (store.docName || "document").replace(/\.(pptx|pdf)$/i, "").trim() || "document";
}

function withExportExtension(name: string, format: ExportFormat) {
  const stem = name.replace(/\.(pptx|pdf)$/i, "").trim() || defaultStem();
  return format === "pdf" ? `${stem}.pdf` : `${stem}.pptx`;
}

function normalizeExportFilename() {
  exportFilenameInput.value = withExportExtension(exportFilenameInput.value, exportFormat.value);
}

function resolveExportFilename() {
  return withExportExtension(exportFilenameInput.value, exportFormat.value);
}

function resolveAssetUrl(url?: string) {
  if (!url) return "";
  if (/^(https?:)?\/\//.test(url) || url.startsWith("data:") || url.startsWith("blob:")) return url;
  const base = store.baseUrl.replace(/\/$/, "");
  return url.startsWith("/") ? `${base}${url}` : `${base}/${url}`;
}

function appendCacheBust(url: string) {
  if (!url) return url;
  const base = url.split("?")[0];
  return `${base}?t=${Date.now()}`;
}

async function refreshPreviewFromServer() {
  if (!store.currentFileId) return;
  try {
    const detail = await getFileDetail(store.baseUrl, store.currentFileId);
    const pageMap = new Map(detail.pages_detail.map((page) => [page.page, page]));
    for (const slide of store.slides) {
      const page = pageMap.get(slide.page);
      if (!page?.preview_url) continue;
      slide.previewUrl = appendCacheBust(resolveAssetUrl(page.preview_url));
      slide.thumbnailUrl = appendCacheBust(
        resolveAssetUrl(page.thumbnail_url || page.preview_url).replace("/page-", "/thumb-")
      );
    }
  } catch (e: any) {
    exportMessage.value = e?.message || "预览刷新失败";
  }
}

function setPageThumbRef(el: unknown, i: number) {
  pageThumbRefs.value[i] = (el as HTMLElement | null) ?? null;
}

function scrollCurrentThumbIntoView() {
  const thumb = pageThumbRefs.value[store.currentIndex];
  if (!thumb) return;
  thumb.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
}

function goToPage(index: number) {
  if (index < 0 || index >= store.slides.length) return;
  store.currentIndex = index;
  nextTick(() => scrollCurrentThumbIntoView());
}

function prevPage() {
  goToPage(store.currentIndex - 1);
}

function nextPage() {
  goToPage(store.currentIndex + 1);
}

function onPreviewWheel(event: WheelEvent) {
  if (event.ctrlKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
  event.preventDefault();

  const delta = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? event.deltaY * 16 : event.deltaY;
  wheelDelta += delta;
  if (wheelResetTimer) window.clearTimeout(wheelResetTimer);
  wheelResetTimer = window.setTimeout(() => {
    wheelDelta = 0;
    wheelResetTimer = null;
  }, 180);

  const now = Date.now();
  if (Math.abs(wheelDelta) < 70 || now - lastWheelSwitchAt < 420) return;

  if (wheelDelta > 0 && canNext.value) nextPage();
  if (wheelDelta < 0 && canPrev.value) prevPage();
  wheelDelta = 0;
  lastWheelSwitchAt = now;
}

function backToWorkspace() {
  void router.push("/workspace");
}

async function runExport() {
  if (!store.currentFileId || exportLoading.value) return;
  if (exportFormat.value === "pptx" && !isPptx.value) {
    exportMessage.value = "当前文档不是 PPTX，无法导出为 PPT";
    return;
  }

  normalizeExportFilename();
  const filename = resolveExportFilename();
  exportLoading.value = true;
  exportMessage.value = exportFormat.value === "pdf" ? "正在生成 PDF..." : "正在准备 PPT...";
  try {
    await exportDocumentFile(store.baseUrl, store.currentFileId, filename, exportFormat.value);
    exportMessage.value =
      exportFormat.value === "pdf" ? "PDF 已下载" : "PPT 已下载，插入配图为可独立移动的图片元素";
    store.addLog(exportMessage.value);
  } catch (e: any) {
    exportMessage.value = e?.message || "导出失败";
    store.addLog(`导出失败：${exportMessage.value}`);
  } finally {
    exportLoading.value = false;
  }
}

watch(exportFormat, (format) => {
  exportFilenameInput.value = withExportExtension(exportFilenameInput.value, format);
});

watch(
  () => store.currentIndex,
  () => nextTick(() => scrollCurrentThumbIntoView())
);

onMounted(async () => {
  if (!hasDoc.value || !store.currentFileId) {
    await router.replace("/workspace");
    return;
  }
  if (!isPptx.value) exportFormat.value = "pdf";
  exportFilenameInput.value = withExportExtension(defaultStem(), exportFormat.value);
  await refreshPreviewFromServer();
  await nextTick();
  scrollCurrentThumbIntoView();
});

onBeforeUnmount(() => {
  if (wheelResetTimer) window.clearTimeout(wheelResetTimer);
});
</script>

<template>
  <div class="export-root">
    <header class="export-topbar">
      <div class="export-topbar-main">
        <button type="button" class="export-back-btn" @click="backToWorkspace">
          <span class="export-back-icon" aria-hidden="true">←</span>
          <span>返回工作台</span>
        </button>
        <div class="export-topbar-divider" aria-hidden="true"></div>
        <div class="export-topbar-title">
          <strong>导出文档</strong>
          <span class="export-topbar-sub">预览当前页面，确认格式与文件名后下载</span>
        </div>
      </div>
      <span v-if="store.docName" class="export-source-name" :title="store.docName">{{ store.docName }}</span>
    </header>

    <div class="export-layout">
      <aside class="export-sidebar" aria-label="页面导航">
        <div class="export-sidebar-head">
          <p class="section-kicker">页面导航</p>
          <div class="export-nav-row">
            <button type="button" class="tb-icon" :disabled="!canPrev" @click="prevPage">&lsaquo;</button>
            <span class="tb-page">第 {{ pageLabel }} 页</span>
            <button type="button" class="tb-icon" :disabled="!canNext" @click="nextPage">&rsaquo;</button>
          </div>
        </div>
        <div class="page-thumbs-scroll">
          <div class="page-thumbs">
            <button
              v-for="(s, i) in store.slides"
              :key="s.id"
              :ref="(el) => setPageThumbRef(el, i)"
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
      </aside>

      <section class="export-preview" aria-label="文档预览">
        <div class="export-preview-toolbar">
          <span>单页预览 · 第 {{ pageLabel }} 页</span>
          <label class="zoom-control">
            <span>缩放</span>
            <input v-model.number="zoomPercent" type="range" min="50" max="200" step="1" />
            <span>{{ zoomPercent }}%</span>
          </label>
        </div>
        <div class="export-preview-viewport" title="向上或向下滚动切换页面" @wheel="onPreviewWheel">
          <Transition name="export-page" mode="out-in">
            <div v-if="currentSlide" :key="currentSlide.id" class="export-slide-stage" :style="{ width: previewWidth }">
              <img
                v-if="currentSlide.previewUrl"
                class="export-slide-img"
                :src="currentSlide.previewUrl"
                :alt="currentSlide.input.topic"
              />
              <article v-else class="export-slide-fallback">
                <h2>{{ currentSlide.input.topic || ("第 " + (store.currentIndex + 1) + " 页") }}</h2>
                <p>{{ currentSlide.input.body || "本页暂无可用预览。" }}</p>
              </article>
              <span class="export-slide-label">{{ pageLabel }}</span>
            </div>
          </Transition>
        </div>
      </section>

      <aside class="export-panel" aria-label="导出选项">
        <div class="export-panel-body">
        <p class="section-kicker">导出格式</p>
        <h2>选择文件类型</h2>
        <p class="export-lead">PPT 会保留可编辑的配图元素；PDF 适合分享与打印。下载前可修改文件名。</p>

        <div class="format-options">
          <label class="format-option" :class="{ active: exportFormat === 'pptx', disabled: !isPptx }">
            <input v-model="exportFormat" type="radio" value="pptx" :disabled="!isPptx" />
            <span>
              <strong>PPT (.pptx)</strong>
              <small>保留可编辑配图，适合继续修改</small>
            </span>
          </label>
          <label class="format-option" :class="{ active: exportFormat === 'pdf' }">
            <input v-model="exportFormat" type="radio" value="pdf" />
            <span>
              <strong>PDF (.pdf)</strong>
              <small>适合分享、审阅与打印</small>
            </span>
          </label>
        </div>

        <label class="export-filename-field">
          <span>文件名</span>
          <input
            v-model="exportFilenameInput"
            type="text"
            class="export-filename-input"
            placeholder="输入下载文件名"
            @blur="normalizeExportFilename"
            @keydown.enter.prevent="normalizeExportFilename"
          />
          <small>切换格式时会自动更新扩展名</small>
        </label>

        <button type="button" class="btn solid export-btn" :disabled="exportLoading" @click="runExport">
          <span v-if="exportLoading" class="btn-spinner wine-spin"></span>
          {{ exportLoading ? "导出中..." : "下载文件" }}
        </button>
        <p v-if="exportMessage" class="export-message">{{ exportMessage }}</p>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.export-root {
  flex: 1;
  min-height: 0;
  height: calc(100dvh - 70px);
  max-height: calc(100dvh - 70px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-bg);
}

.export-topbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: 14px var(--space-5);
  border-bottom: 1px solid var(--color-border);
  background: linear-gradient(180deg, rgba(255, 250, 251, 0.98), rgba(255, 255, 255, 0.96));
  box-shadow: 0 1px 0 rgba(139, 41, 66, 0.04);
}

.export-topbar-main {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.export-back-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 0 14px 0 12px;
  border: 1px solid var(--color-primary-border);
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: background var(--motion-base), transform var(--motion-base), box-shadow var(--motion-base);
}

.export-back-btn:hover,
.export-back-btn:focus-visible {
  background: var(--color-primary-soft);
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(139, 41, 66, 0.12);
}

.export-back-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: rgba(139, 41, 66, 0.08);
  font-size: 14px;
  line-height: 1;
}

.export-topbar-divider {
  width: 1px;
  height: 28px;
  background: var(--color-border);
}

.export-topbar-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.export-topbar-title strong {
  font-size: 16px;
  color: var(--color-text);
}

.export-topbar-sub {
  color: var(--color-muted);
  font-size: 12px;
}

.export-source-name {
  max-width: min(320px, 34vw);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 6px 12px;
  border-radius: 999px;
  background: var(--color-bg-muted);
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 600;
}

.export-layout {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 320px;
}

.export-sidebar,
.export-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  padding: var(--space-4);
}

.export-panel {
  border-right: none;
  border-left: 1px solid var(--color-border);
}

.export-sidebar-head,
.export-preview-toolbar {
  flex-shrink: 0;
  margin-bottom: var(--space-4);
}

.page-thumbs-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(139, 41, 66, 0.42) rgba(139, 41, 66, 0.08);
}

.page-thumbs-scroll::-webkit-scrollbar {
  width: 8px;
}

.page-thumbs-scroll::-webkit-scrollbar-track {
  border-radius: 999px;
  background: rgba(139, 41, 66, 0.08);
}

.page-thumbs-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(139, 41, 66, 0.42);
}

.export-panel-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.export-nav-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
}

.tb-icon {
  width: 32px;
  height: 32px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}

.tb-icon:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.tb-page {
  font-size: 13px;
  font-weight: 700;
}

.page-thumbs {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.page-thumb {
  display: grid;
  grid-template-columns: 28px 1fr;
  grid-template-rows: auto auto;
  gap: 4px 8px;
  align-items: start;
  padding: 8px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  text-align: left;
}

.page-thumb.active {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px rgba(139, 41, 66, 0.15);
}

.thumb-index {
  grid-row: span 2;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-muted);
}

.thumb-frame {
  display: block;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: 6px;
  background: var(--color-bg-muted);
}

.thumb-frame img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.thumb-fallback,
.thumb-title {
  font-size: 12px;
}

.thumb-title {
  color: var(--color-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.export-preview {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-muted);
}

.export-preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
}

.zoom-control {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.export-preview-viewport {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: clamp(20px, 4vw, 56px);
  background: #f4f2f3;
}

.export-slide-stage {
  position: relative;
  min-width: 360px;
  max-width: none;
  margin: 0 auto;
}

.export-slide-label {
  position: absolute;
  right: 12px;
  bottom: 12px;
  padding: 4px 11px;
  border-radius: 999px;
  background: var(--color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  box-shadow: 0 4px 12px rgba(139, 41, 66, 0.18);
}

.export-slide-img {
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  border: 1px solid #d8d1d4;
  border-radius: 4px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
  background: #fff;
}

.export-slide-fallback {
  width: 100%;
  padding: 48px 32px;
  border: 1px solid #d8d1d4;
  border-radius: 4px;
  background: #fff;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
}

.export-slide-fallback h2 {
  margin: 0 0 12px;
  font-size: 22px;
}

.export-slide-fallback p {
  margin: 0;
  color: var(--color-muted);
  line-height: 1.6;
}

.export-page-enter-active,
.export-page-leave-active {
  transition: opacity var(--motion-base), transform var(--motion-base);
}

.export-page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.export-page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.section-kicker {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.export-panel h2 {
  margin: 0 0 var(--space-3);
  font-size: 24px;
}

.export-lead {
  margin: 0 0 var(--space-5);
  color: var(--color-muted);
  line-height: 1.6;
  font-size: 14px;
}

.format-options {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.format-option {
  display: flex;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  cursor: pointer;
  background: #fff;
}

.format-option.active {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px rgba(139, 41, 66, 0.12);
}

.format-option.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.format-option strong {
  display: block;
  margin-bottom: 2px;
}

.format-option small {
  color: var(--color-muted);
}

.export-filename-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: var(--space-4);
}

.export-filename-field > span {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text);
}

.export-filename-input {
  width: 100%;
  box-sizing: border-box;
  min-height: 42px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: #fff;
  color: var(--color-text);
  font: inherit;
  font-size: 14px;
}

.export-filename-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.export-filename-field small {
  color: var(--color-muted);
  font-size: 12px;
}

.export-btn {
  width: 100%;
  min-height: 44px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-control);
  background: var(--color-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(139, 41, 66, 0.16);
  transition: background var(--motion-base), border-color var(--motion-base), transform var(--motion-base), box-shadow var(--motion-base);
}

.export-btn:hover:not(:disabled),
.export-btn:focus-visible:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(139, 41, 66, 0.22);
}

.export-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.export-message {
  margin: var(--space-3) 0 0;
  font-size: 13px;
  color: var(--color-muted);
}

@media (max-width: 1100px) {
  .export-layout {
    grid-template-columns: 240px minmax(0, 1fr);
  }

  .export-panel {
    grid-column: 1 / -1;
    border-left: none;
    border-top: 1px solid var(--color-border);
  }

  .export-source-name {
    display: none;
  }
}
</style>
