<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { deleteFile, downloadFile, getFileDetail } from "../api/client";
import { store } from "../store";
import type { FileRecordDTO } from "../types";

const router = useRouter();
const opening = ref(0);
const deleting = ref(0);
const message = ref("");
const parsedCount = computed(() => store.files.filter((file) => file.parse_status === "success").length);
const issueCount = computed(() => store.files.filter((file) => file.parse_status === "failed").length);

onMounted(() => store.fetchFiles());

function newId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function goUpload() {
  store.slides = [];
  store.currentIndex = 0;
  store.docName = "";
  store.currentFileId = 0;
  router.push("/workspace");
}

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtTime(iso: string) {
  return iso.replace("T", " ").slice(0, 19);
}

function statusLabel(status: string) {
  return { success: "解析完成", processing: "解析中", failed: "解析失败" }[status] || status;
}

function resolveAssetUrl(url?: string) {
  if (!url) return "";
  if (/^(https?:)?\/\//.test(url) || url.startsWith("data:")) return url;
  const base = store.baseUrl.replace(/\/$/, "");
  return url.startsWith("/") ? `${base}${url}` : `${base}/${url}`;
}

async function reopen(file: FileRecordDTO) {
  opening.value = file.id;
  message.value = "";
  try {
    const detail = await getFileDetail(store.baseUrl, file.id);
    const pages = detail.pages_detail.length
      ? detail.pages_detail
      : [{ page: 1, title: detail.original_filename, text: detail.extracted_text, text_blocks: [] }];
    store.docName = detail.original_filename;
    store.currentFileId = file.id;
    store.slides = pages.map((page) => ({
      id: `${newId()}_${page.page}`,
      page: page.page,
      sourceTitle: page.title || `第 ${page.page} 页`,
      sourceText: page.text || "",
      textBlocks: page.text_blocks || [],
      previewUrl: resolveAssetUrl(page.preview_url),
      thumbnailUrl: resolveAssetUrl(page.thumbnail_url || page.preview_url),
      input: {
        topic: page.title || `第 ${page.page} 页`,
        body: page.text || "",
        data_description: "",
        slide_type: "content",
        mode: "auto",
      },
      statusAnalyze: "idle",
      statusIllustration: "idle",
      history: [],
    }));
    store.currentIndex = 0;
    store.addLog(`重新打开历史文件: ${detail.original_filename}`);
    router.push("/workspace");
  } catch (error: any) {
    message.value = error?.message || String(error);
  } finally {
    opening.value = 0;
  }
}

async function remove(file: FileRecordDTO) {
  if (!window.confirm(`确定从列表移除“${file.original_filename}”吗？`)) return;
  deleting.value = file.id;
  message.value = "";
  try {
    await deleteFile(store.baseUrl, file.id);
    store.files = store.files.filter((item) => item.id !== file.id);
    if (store.currentFileId === file.id) {
      store.slides = [];
      store.currentIndex = 0;
      store.docName = "";
      store.currentFileId = 0;
    }
  } catch (error: any) {
    message.value = error?.message || String(error);
  } finally {
    deleting.value = 0;
  }
}

async function download(file: FileRecordDTO) {
  message.value = "";
  try {
    await downloadFile(store.baseUrl, file.id, file.original_filename);
  } catch (error: any) {
    message.value = error?.message || String(error);
  }
}
</script>

<template>
  <div class="files-container">
    <header class="page-head">
      <div>
        <span class="eyebrow">文档归档</span>
        <h1>我的文件</h1>
        <p>保留原始文件和解析结果，随时重新打开继续处理。</p>
      </div>
      <div class="actions">
        <button class="btn secondary" :disabled="store.filesLoading" @click="store.fetchFiles">刷新</button>
        <button class="btn primary" @click="goUpload">上传新文件</button>
      </div>
    </header>

    <section class="summary-grid">
      <article><span>归档文件</span><strong>{{ store.files.length }}</strong></article>
      <article><span>解析完成</span><strong>{{ parsedCount }}</strong></article>
      <article><span>需要处理</span><strong>{{ issueCount }}</strong></article>
    </section>

    <p v-if="message" class="message">{{ message }}</p>
    <section class="files-panel">
      <header class="panel-head">
        <div><h2>文档列表</h2><p>共 {{ store.files.length }} 个文件</p></div>
        <span v-if="store.filesLoading">正在更新...</span>
      </header>
      <div v-if="!store.filesLoading && store.files.length === 0" class="empty">
        <h3>尚未上传文件</h3>
        <p>上传 PPTX 或 PDF 后，文档会出现在这里。</p>
        <button class="btn primary" @click="goUpload">上传第一个文件</button>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>文件</th><th>页数</th><th>大小</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="file in store.files" :key="file.id">
              <td class="filename">{{ file.original_filename }}</td>
              <td>{{ file.pages }} 页</td>
              <td>{{ fmtSize(file.file_size) }}</td>
              <td><span class="status" :class="file.parse_status">{{ statusLabel(file.parse_status) }}</span></td>
              <td>{{ fmtTime(file.updated_at) }}</td>
              <td class="row-actions">
                <button :disabled="file.parse_status !== 'success' || opening === file.id" @click="reopen(file)">打开</button>
                <button @click="download(file)">下载</button>
                <button class="danger" :disabled="deleting === file.id" @click="remove(file)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.files-container { width: 100%; max-width: var(--panel-max-width); margin: 0 auto; padding: var(--space-6); animation: panel-in var(--motion-slow) var(--motion-ease) both; }
.page-head, .actions, .panel-head, .row-actions { display: flex; align-items: center; gap: var(--space-3); }
.page-head, .panel-head { justify-content: space-between; }
.page-head { align-items: flex-start; margin-bottom: var(--space-5); }
.eyebrow { display: inline-flex; min-height: 28px; align-items: center; padding: 0 10px; border: 1px solid var(--color-primary-border); border-radius: 999px; background: var(--color-primary-soft); color: var(--color-primary); font-size: 12px; font-weight: 800; }
h1 { margin: 10px 0 8px; font-size: 28px; } p { margin: 0; color: var(--color-muted); font-size: 13px; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-3); margin-bottom: var(--space-4); }
.summary-grid article, .files-panel { border: 1px solid var(--color-border); border-radius: var(--radius-card); background: var(--color-surface); box-shadow: var(--shadow-card); }
.summary-grid article { min-height: 96px; padding: var(--space-5); }.summary-grid span { color: var(--color-muted); font-size: 12px; font-weight: 700; }.summary-grid strong { display: block; margin-top: 8px; color: var(--color-primary); font-size: 26px; }
.files-panel { overflow: hidden; }.panel-head { padding: var(--space-5); border-bottom: 1px solid var(--color-border); }.panel-head h2 { margin: 0 0 4px; font-size: 17px; }.panel-head span { color: var(--color-primary); font-size: 12px; font-weight: 800; }
.table-wrap { overflow-x: auto; } table { width: 100%; min-width: 780px; border-collapse: collapse; } th, td { padding: 13px 16px; border-bottom: 1px solid var(--color-border); text-align: left; font-size: 13px; } th { background: var(--color-bg-muted); color: var(--color-muted); font-size: 12px; }.filename { max-width: 280px; overflow: hidden; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.btn { min-height: var(--control-lg); padding: 0 18px; border: 1px solid transparent; border-radius: var(--radius-control); cursor: pointer; font-weight: 800; }.primary { background: var(--color-primary); color: white; }.secondary { border-color: var(--color-primary); background: var(--color-surface); color: var(--color-primary); }
.row-actions button { border: 0; background: transparent; color: var(--color-primary); cursor: pointer; font-weight: 800; }.row-actions .danger { color: var(--color-danger); } button:disabled { cursor: not-allowed; opacity: .5; }
.status { padding: 4px 8px; border-radius: var(--radius-control); background: var(--color-bg-muted); color: var(--color-muted); font-size: 11px; font-weight: 800; }.status.success { background: var(--color-primary-soft); color: var(--color-primary); }.status.failed, .message { color: var(--color-danger); background: var(--color-danger-soft); }
.message { margin-bottom: var(--space-3); padding: 10px 12px; border-radius: var(--radius-control); }.empty { padding: 64px 20px; text-align: center; }.empty h3 { margin: 0 0 8px; }.empty p { margin-bottom: 20px; }
@media (max-width: 720px) { .files-container { padding: var(--space-4); }.page-head { flex-direction: column; }.summary-grid { grid-template-columns: 1fr; } }
</style>
