<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { deleteFile, downloadFile, getFileDetail } from "../api/client";
import { store } from "../store";
import type { FileRecord, SlideRequest } from "../types";

const router = useRouter();
const opening = ref<number | null>(null);
const deleting = ref<number | null>(null);
const message = ref("");
const parsedCount = computed(() => store.files.filter((file) => file.parse_status === "success").length);
const issueCount = computed(() => store.files.filter((file) => ["failed", "error"].includes(file.parse_status)).length);

onMounted(() => store.fetchFiles());

function newId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function fileExtension(filename: string) {
  const suffix = filename.split(".").pop();
  return suffix && suffix !== filename ? suffix.toUpperCase() : "DOC";
}

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtTime(iso: string) {
  return iso ? iso.replace("T", " ").slice(0, 19) : "-";
}

function statusClass(status: string) {
  if (status === "success") return "status-ok";
  if (status === "failed" || status === "error") return "status-err";
  return "status-pending";
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    success: "解析完成",
    processing: "解析中",
    parsing: "解析中",
    pending: "待处理",
    failed: "解析失败",
    error: "解析失败",
  };
  return labels[status] || status;
}

function resolveAssetUrl(url?: string) {
  if (!url) return "";
  if (/^(https?:)?\/\//.test(url) || url.startsWith("data:")) return url;
  const base = store.baseUrl.replace(/\/$/, "");
  return url.startsWith("/") ? `${base}${url}` : `${base}/${url}`;
}

function createInputFromPage(title: string, text: string): SlideRequest {
  return { topic: title || "未命名页面", body: text || "", data_description: "", slide_type: "content", mode: "auto" };
}

function goUpload() {
  store.slides = [];
  store.currentIndex = 0;
  store.docName = "";
  store.currentFileId = 0;
  store.docConsistency = null;
  router.push("/workspace");
}

async function reopen(file: FileRecord) {
  opening.value = file.id;
  message.value = "";
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
    store.addLog(
      restored
        ? `重新打开历史文件并恢复编辑草稿: ${detail.original_filename}，共 ${store.slides.length} 页`
        : `重新打开历史文件: ${detail.original_filename}，共 ${store.slides.length} 页`
    );
    router.push("/workspace");
  } catch (error: any) {
    message.value = error?.message || String(error);
  } finally {
    opening.value = null;
  }
}

async function download(file: FileRecord) {
  message.value = "";
  try {
    await downloadFile(store.baseUrl, file.id, file.original_filename);
  } catch (error: any) {
    message.value = error?.message || String(error);
  }
}

async function remove(file: FileRecord) {
  if (!window.confirm(`确定删除“${file.original_filename}”吗？此操作不可恢复。`)) return;
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
      store.docConsistency = null;
    }
    store.addLog(`已删除文件记录: ${file.original_filename}`);
  } catch (error: any) {
    message.value = error?.message || String(error);
  } finally {
    deleting.value = null;
  }
}
</script>

<template>
  <div class="files-container">
    <header class="page-head">
      <div>
        <span class="eyebrow">文档归档</span>
        <h1>我的文件</h1>
        <p>管理已解析的演示文稿和 PDF 文档，重新打开历史文件后可以继续处理页面内容。</p>
      </div>
      <div class="head-actions">
        <button class="btn primary" @click="goUpload">上传新文件</button>
        <button class="btn secondary" :disabled="store.filesLoading" @click="store.fetchFiles">
          {{ store.filesLoading ? "加载中..." : "刷新列表" }}
        </button>
      </div>
    </header>

    <section class="summary-grid">
      <article><span>归档文件</span><strong>{{ store.files.length }}</strong></article>
      <article><span>解析完成</span><strong>{{ parsedCount }}</strong></article>
      <article><span>需要处理</span><strong>{{ issueCount }}</strong></article>
    </section>

    <p v-if="message" class="message">{{ message }}</p>

    <section class="files-panel surface-panel">
      <header class="panel-head">
        <div>
          <h2>文档列表</h2>
          <p>共 {{ store.files.length }} 个文件</p>
        </div>
        <span v-if="store.filesLoading" class="loading-note">正在更新列表...</span>
      </header>

      <div v-if="store.filesLoading && store.files.length === 0" class="loading">正在加载文件...</div>
      <div v-else-if="store.files.length === 0" class="empty">
        <h3>尚未上传文件</h3>
        <p>上传 PPTX 或 PDF 后，文档会出现在这里。</p>
        <button class="btn primary" @click="goUpload">上传第一个文件</button>
      </div>

      <div v-else class="table-wrap">
        <table class="files-table">
          <thead>
            <tr>
              <th>文件</th>
              <th>页数</th>
              <th>大小</th>
              <th>状态</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="file in store.files" :key="file.id">
              <td>
                <div class="file-identity">
                  <span class="file-type">{{ fileExtension(file.original_filename) }}</span>
                  <span class="name-cell" :title="file.original_filename">{{ file.original_filename }}</span>
                </div>
              </td>
              <td>{{ file.pages }} 页</td>
              <td>{{ fmtSize(file.file_size) }}</td>
              <td><span class="status-badge" :class="statusClass(file.parse_status)">{{ statusLabel(file.parse_status) }}</span></td>
              <td class="time-cell">{{ fmtTime(file.updated_at || file.created_at) }}</td>
              <td>
                <div class="action-cell">
                  <button class="link-btn" :disabled="opening === file.id || file.parse_status !== 'success'" @click="reopen(file)">
                    {{ opening === file.id ? "打开中..." : "打开" }}
                  </button>
                  <button class="link-btn" @click="download(file)">下载</button>
                  <button class="link-btn danger-link" :disabled="deleting === file.id" @click="remove(file)">
                    {{ deleting === file.id ? "删除中..." : "删除" }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.files-container { flex: 1; width: 100%; max-width: var(--panel-max-width); margin: 0 auto; padding: var(--space-6); animation: panel-in var(--motion-slow) var(--motion-ease) both; }
.page-head, .panel-head, .head-actions, .file-identity, .action-cell { display: flex; align-items: center; }
.page-head { align-items: flex-start; justify-content: space-between; gap: var(--space-4); margin-bottom: var(--space-5); }
.eyebrow { display: inline-flex; min-height: 28px; align-items: center; padding: 0 10px; border: 1px solid var(--color-primary-border); border-radius: 999px; background: var(--color-primary-soft); color: var(--color-primary); font-size: 12px; font-weight: 800; }
.page-head h1 { margin: 10px 0 8px; color: var(--color-text); font-size: 28px; line-height: 1.2; }
.page-head p, .panel-head p { margin: 0; color: var(--color-muted); font-size: 13px; line-height: 1.7; }
.head-actions, .action-cell { gap: 8px; flex-wrap: wrap; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-grid article, .files-panel { border: 1px solid var(--color-border); border-radius: var(--radius-card); background: var(--color-surface); box-shadow: var(--shadow-card); }
.summary-grid article { min-height: 96px; padding: var(--space-5); }
.summary-grid span { display: block; color: var(--color-muted); font-size: 12px; font-weight: 700; }
.summary-grid strong { display: block; margin-top: 8px; color: var(--color-primary); font-size: 26px; line-height: 1.1; }
.files-panel { overflow: hidden; }
.panel-head { justify-content: space-between; gap: var(--space-3); padding: var(--space-5); border-bottom: 1px solid var(--color-border); }
.panel-head h2 { margin: 0 0 4px; color: var(--color-text); font-size: 17px; }
.loading-note { color: var(--color-primary); font-size: 12px; font-weight: 800; }
.loading, .empty { padding: 64px 20px; color: var(--color-muted); text-align: center; }
.empty h3 { margin: 0 0 8px; color: var(--color-text); font-size: 18px; }
.empty p { margin: 0 0 20px; font-size: 13px; }
.table-wrap { width: 100%; overflow-x: auto; }
.files-table { width: 100%; min-width: 780px; border-collapse: collapse; background: var(--color-surface); }
.files-table th, .files-table td { padding: 13px 16px; border-bottom: 1px solid var(--color-border); text-align: left; vertical-align: middle; }
.files-table tr:last-child td { border-bottom: 0; }
.files-table th { background: var(--color-bg-muted); color: var(--color-muted); font-size: 12px; font-weight: 800; }
.files-table td { color: var(--color-text); font-size: 13px; }
.files-table tbody tr { transition: background var(--motion-base); }
.files-table tbody tr:hover { background: var(--color-primary-soft); }
.file-identity { gap: 10px; min-width: 0; }
.file-type { display: inline-flex; min-width: 42px; height: 28px; align-items: center; justify-content: center; padding: 0 6px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-control); background: var(--color-primary-soft); color: var(--color-primary); font-size: 10px; font-weight: 900; }
.name-cell { max-width: 300px; overflow: hidden; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.time-cell { color: var(--color-muted) !important; font-size: 12px !important; white-space: nowrap; }
.status-badge { display: inline-flex; min-height: 24px; align-items: center; padding: 0 8px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-control); font-size: 11px; font-weight: 800; }
.status-ok { background: var(--color-primary-soft); color: var(--color-primary); }
.status-err { border-color: #fecdd3; background: var(--color-danger-soft); color: var(--color-danger); }
.status-pending { border-color: var(--color-border); background: var(--color-bg-muted); color: var(--color-muted); }
.btn { display: inline-flex; min-height: var(--control-lg); align-items: center; justify-content: center; padding: 0 18px; border: 1px solid transparent; border-radius: var(--radius-control); cursor: pointer; font-weight: 800; text-align: center; text-decoration: none; transition: background var(--motion-base), border-color var(--motion-base), color var(--motion-base), transform var(--motion-base), box-shadow var(--motion-base); }
.btn:disabled, .link-btn:disabled { cursor: not-allowed; opacity: 0.5; }
.primary { background: var(--color-primary); color: white; }
.primary:hover:not(:disabled) { background: var(--color-primary-hover); box-shadow: var(--shadow-card-hover); transform: translateY(-2px); }
.secondary { border-color: var(--color-primary); background: var(--color-surface); color: var(--color-primary); }
.secondary:hover:not(:disabled) { background: var(--color-primary-soft); }
.link-btn { min-height: 30px; padding: 0 8px; border: 0; border-radius: var(--radius-control); background: transparent; color: var(--color-primary); cursor: pointer; font-size: 12px; font-weight: 800; transition: background var(--motion-base), color var(--motion-base); }
.link-btn:hover:not(:disabled) { background: var(--color-primary-tint); }
.danger-link { color: var(--color-danger); }
.danger-link:hover:not(:disabled) { background: var(--color-danger-soft); }
.message { margin-bottom: var(--space-3); padding: 10px 12px; border-radius: var(--radius-control); background: var(--color-danger-soft); color: var(--color-danger); font-size: 13px; }
@media (max-width: 720px) { .files-container { padding: var(--space-4); } .page-head { flex-direction: column; } .summary-grid { grid-template-columns: 1fr; } }
</style>
