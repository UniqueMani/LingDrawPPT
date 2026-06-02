<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { store } from '../store';
import { getFileDetail, deleteFile } from '../api/client';
import type { FileRecord } from '../types';

const router = useRouter();
const deleting = ref<number | null>(null);
const opening = ref<number | null>(null);

function newId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

onMounted(() => {
  store.fetchFiles();
});

/** 上传新文件：清空当前工作台状态后跳转 */
function goUpload() {
  store.slides = [];
  store.currentIndex = 0;
  store.docName = '';
  store.currentFileId = 0;
  router.push('/workspace');
}

/** 格式化文件大小 */
function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** 格式化时间 */
function fmtTime(iso: string) {
  return iso.replace('T', ' ').slice(0, 19);
}

/** 状态标签样式 */
function statusClass(status: string) {
  return status === 'success' ? 'status-ok' : status === 'error' ? 'status-err' : 'status-pending';
}
function statusLabel(status: string) {
  const m: Record<string, string> = { success: '已解析', error: '解析失败', pending: '待处理' };
  return m[status] || status;
}

/** 将相对路径转为完整 URL（与 WorkspaceView 中 resolveAssetUrl 逻辑一致） */
function resolveAssetUrl(url?: string) {
  if (!url) return '';
  if (/^(https?:)?\/\//.test(url) || url.startsWith('data:')) return url;
  const base = store.baseUrl.replace(/\/$/, '');
  return url.startsWith('/') ? `${base}${url}` : `${base}/${url}`;
}

/** 重新打开历史文件 */
async function reopen(file: FileRecord) {
  opening.value = file.id;
  try {
    const detail = await getFileDetail(store.baseUrl, file.id);
    store.docName = detail.original_filename;
    store.currentFileId = file.id;
    store.slides = [];

    const pages = detail.pages_data.length > 0
      ? detail.pages_data
      : [{ page: 1, title: detail.filename, text: detail.extracted_text }];

    for (const p of pages) {
      store.slides.push({
        id: `${newId()}_${p.page}`,
        input: {
          topic: (p as any).title || `第 ${(p as any).page} 页`,
          body: (p as any).text || '',
          data_description: '',
          slide_type: 'content',
          mode: 'auto',
        },
        statusAnalyze: 'idle',
        statusIllustration: 'idle',
        history: [],
        page: (p as any).page || 0,
        sourceTitle: (p as any).title || '',
        sourceText: (p as any).text || '',
        previewUrl: resolveAssetUrl((p as any).preview_url),
        thumbnailUrl: resolveAssetUrl((p as any).thumbnail_url || (p as any).preview_url),
      });
    }
    store.currentIndex = 0;
    store.addLog(`重新打开历史文件: ${detail.original_filename}，共 ${store.slides.length} 页`);
    router.push('/workspace');
  } catch (e: any) {
    store.addLog(`打开文件失败: ${e?.message || String(e)}`);
  } finally {
    opening.value = null;
  }
}

/** 删除文件 */
async function remove(fileId: number) {
  if (!confirm('确定删除此文件？此操作不可恢复。')) return;
  deleting.value = fileId;
  try {
    await deleteFile(store.baseUrl, fileId);
    store.files = store.files.filter(f => f.id !== fileId);
    // 如果删除的是当前工作台中打开的文件，同步清空工作台
    if (store.currentFileId === fileId) {
      store.slides = [];
      store.currentIndex = 0;
      store.docName = '';
      store.currentFileId = 0;
    }
    store.addLog(`已删除文件记录 #${fileId}`);
  } catch (e: any) {
    store.addLog(`删除失败: ${e?.message || String(e)}`);
  } finally {
    deleting.value = null;
  }
}
</script>

<template>
  <div class="files-container">
    <div class="page-head">
      <div>
        <span class="eyebrow">文件管理</span>
        <h1>我的文件</h1>
        <p>管理已上传的文档档案，可以重新打开历史文件继续编辑。</p>
      </div>
      <div class="head-actions">
        <button class="btn primary" @click="goUpload">📁 上传新文件</button>
        <button class="btn secondary" @click="store.fetchFiles" :disabled="store.filesLoading">
          {{ store.filesLoading ? '加载中...' : '🔄 刷新' }}
        </button>
      </div>
    </div>

    <div v-if="store.filesLoading && store.files.length === 0" class="loading">加载中...</div>

    <div v-else-if="store.files.length === 0" class="empty">
      <p>暂无已上传的文件</p>
      <button class="btn primary" @click="goUpload">上传第一个文件</button>
    </div>

    <table v-else class="files-table">
      <thead>
        <tr>
          <th>文件名</th>
          <th>页数</th>
          <th>大小</th>
          <th>状态</th>
          <th>上传时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in store.files" :key="f.id">
          <td class="name-cell" :title="f.original_filename">{{ f.original_filename }}</td>
          <td>{{ f.pages }} 页</td>
          <td>{{ fmtSize(f.file_size) }}</td>
          <td><span class="status-badge" :class="statusClass(f.parse_status)">{{ statusLabel(f.parse_status) }}</span></td>
          <td class="time-cell">{{ fmtTime(f.updated_at) }}</td>
          <td class="action-cell">
            <button
              class="btn small primary"
              @click="reopen(f)"
              :disabled="opening === f.id || f.parse_status !== 'success'"
            >
              {{ opening === f.id ? '打开中...' : '打开' }}
            </button>
            <button
              class="btn small danger"
              @click="remove(f.id)"
              :disabled="deleting === f.id"
            >
              {{ deleting === f.id ? '删除中...' : '删除' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.files-container { flex: 1; padding: var(--space-6); max-width: var(--panel-max-width); margin: 0 auto; animation: panel-in var(--motion-slow) var(--motion-ease) both; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-4); margin-bottom: var(--space-5); flex-wrap: wrap; }
.eyebrow { display: inline-flex; align-items: center; min-height: 28px; padding: 0 10px; border-radius: 999px; background: var(--color-primary-soft); border: 1px solid var(--color-primary-border); color: var(--color-primary); font-size: 12px; font-weight: 800; }
.page-head h1 { margin: 10px 0 8px; font-size: 28px; color: var(--color-text); }
.page-head p { margin: 0; color: var(--color-muted); font-size: 14px; }
.head-actions { display: flex; gap: 10px; align-items: center; flex-shrink: 0; }

.loading, .empty { text-align: center; padding: 60px 20px; color: var(--color-muted); }
.empty p { margin: 0 0 20px; font-size: 16px; }

.files-table { width: 100%; border-collapse: collapse; background: var(--color-surface); border-radius: var(--radius-card); border: 1px solid var(--color-border); overflow: hidden; box-shadow: var(--shadow-card); }
.files-table th, .files-table td { text-align: left; padding: 12px 16px; border-bottom: 1px solid var(--color-border); }
.files-table th { background: var(--color-bg-muted); color: var(--color-muted); font-size: 13px; font-weight: 800; }
.files-table td { font-size: 14px; color: var(--color-text); }
.name-cell { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.time-cell { white-space: nowrap; color: var(--color-muted); font-size: 13px; }
.action-cell { white-space: nowrap; display: flex; gap: 8px; }

.status-badge { display: inline-flex; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 800; }
.status-ok { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
.status-err { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
.status-pending { background: #f3f0e8; color: #786b3a; border: 1px solid #e8dca8; }

.btn { min-height: var(--control-lg); padding: 0 18px; border-radius: var(--radius-control); border: 1px solid transparent; cursor: pointer; font-weight: 800; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; text-align: center; transition: background var(--motion-base), border-color var(--motion-base), color var(--motion-base), transform var(--motion-base), box-shadow var(--motion-base); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.primary { background: var(--color-primary); color: white; }
.primary:hover:not(:disabled) { background: var(--color-primary-hover); transform: translateY(-2px); box-shadow: var(--shadow-card-hover); }
.secondary { background: var(--color-surface); border-color: var(--color-primary); color: var(--color-primary); }
.secondary:hover:not(:disabled) { background: var(--color-primary-soft); }
.danger { background: var(--color-surface); border-color: var(--color-danger); color: var(--color-danger); }
.danger:hover:not(:disabled) { background: var(--color-danger-soft); }
.small { min-height: 32px; padding: 0 12px; font-size: 13px; }

@media (max-width: 720px) {
  .files-container { padding: var(--space-4); }
  .page-head { flex-direction: column; }
  .files-table { font-size: 12px; }
  .files-table th, .files-table td { padding: 8px 10px; }
}
</style>
