<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { store } from '../store';
import { login, register, setAuthToken, getStats, getFileDetail } from '../api/client';
import ChartPreview from '../components/ChartPreview.vue';
import type { FileRecord, SlideRequest } from '../types';

const authTab = ref<'login' | 'register'>('login');
const router = useRouter();
const authName = ref("");
const authPwd = ref("");
const regConfirmPwd = ref("");
const authLoading = ref(false);
const authMessage = ref("");
const openingRecentId = ref<number | null>(null);
const recentMessage = ref("");

function switchTab(tab: 'login' | 'register') {
  authTab.value = tab;
  authMessage.value = "";
}

async function doAuth() {
  authLoading.value = true;
  authMessage.value = "";
  try {
    if (authTab.value === 'register' && authPwd.value !== regConfirmPwd.value) {
      throw new Error("两次输入的密码不一致");
    }
    const resp = authTab.value === 'login'
      ? await login(store.baseUrl, authName.value, authPwd.value)
      : await register(store.baseUrl, {
          username: authName.value,
          password: authPwd.value,
          full_name: authName.value,
          email: `${authName.value}@example.com`,
          organization: '个人',
        });
    store.setToken(resp.token);
    store.currentUser = resp.user;
    setAuthToken(resp.token);
    store.addLog(`用户 ${resp.user.username} 登录成功`);
    await loadStats();
    await store.fetchFiles();
    if (resp.user.is_admin) router.push('/admin');
  } catch (e: any) {
    authMessage.value = e?.message || String(e);
  } finally {
    authLoading.value = false;
  }
}

// 加载统计数据
const statsLoading = ref(false);
async function loadStats() {
  if (!store.token) return;
  statsLoading.value = true;
  try {
    const data = await getStats(store.baseUrl, 30);
    store.usageStats = data.events;
  } catch {
    // 静默失败，使用默认空数据
  } finally {
    statsLoading.value = false;
  }
}

// 首页图表数据（使用真实统计数据）
const EVENT_ORDER = ['upload', 'analyze', 'generate', 'adopt'];
const EVENT_LABELS: Record<string, string> = {
  upload: '上传', analyze: '解析', generate: '生成', adopt: '采用',
};

const usageTrendOption = computed(() => {
  const stats = store.usageStats || {};
  const data = EVENT_ORDER.map(k => stats[k] || 0);
  return {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 24, right: 16, top: 24, bottom: 24 },
    xAxis: { type: 'category' as const, data: EVENT_ORDER.map(k => EVENT_LABELS[k]), axisLine: { lineStyle: { color: '#d9cdd1' } } },
    yAxis: { type: 'value' as const, splitLine: { lineStyle: { color: '#f0e8eb' } } },
    color: ['#8b2942'],
    series: [{ type: 'line' as const, smooth: true, data, areaStyle: { color: 'rgba(139, 41, 66, 0.08)' } }],
  };
});

const recentFiles = computed(() =>
  [...store.files]
    .sort((a, b) => new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime())
    .slice(0, 3)
);
const parsedFileCount = computed(() => store.files.filter(file => file.parse_status === "success").length);
const totalPageCount = computed(() => store.files.reduce((total, file) => total + (file.pages || 0), 0));
const generateEventCount = computed(() => store.usageStats?.generate || 0);
const hasRecentFiles = computed(() => recentFiles.value.length > 0);

function newId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
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

function fmtTime(iso: string) {
  return iso ? iso.replace("T", " ").slice(0, 16) : "-";
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

function statusClass(status: string) {
  if (status === "success") return "status-ok";
  if (status === "failed" || status === "error") return "status-err";
  return "status-pending";
}

async function openRecentFile(file: FileRecord) {
  if (file.parse_status !== "success") return;
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
    store.addLog(
      restored
        ? `从总览恢复编辑草稿: ${detail.original_filename}`
        : `从总览打开最近文件: ${detail.original_filename}`
    );
    router.push("/workspace");
  } catch (error: any) {
    recentMessage.value = error?.message || String(error);
  } finally {
    openingRecentId.value = null;
  }
}

onMounted(() => {
  if (store.token) {
    loadStats();
    store.fetchFiles();
  }
});
</script>

<template>
  <div class="home-container">
    <!-- 未登录状态：显示登录/注册 -->
    <section v-if="!store.token" class="auth-section">
      <div class="auth-intro">
        <span class="eyebrow">PPT 智能可视化工作台</span>
        <h1>LingDraw PPT Studio</h1>
        <p>上传文档、识别页面语义，并把图表和配图策略组织成稳定的创作流程。</p>
        <div class="intro-steps">
          <span>文档解析</span>
          <span>图表生成</span>
          <span>配图策略</span>
        </div>
      </div>

      <div class="auth-card motion-card">
        <h2>{{ authTab === 'login' ? '欢迎回来' : '创建账号' }}</h2>
        <p>{{ authTab === 'login' ? '继续处理你的演示文稿内容。' : '填写基本信息后进入工作台。' }}</p>
        <div class="auth-tabs">
          <button :class="{ active: authTab === 'login' }" @click="switchTab('login')">登录</button>
          <button :class="{ active: authTab === 'register' }" @click="switchTab('register')">注册</button>
        </div>
        <div class="auth-form">
          <input v-model="authName" placeholder="用户名" class="input auth-field" />
          <input v-model="authPwd" type="password" placeholder="密码" class="input auth-field" />
          <Transition name="auth-fields">
            <input
              v-if="authTab === 'register'"
              v-model="regConfirmPwd"
              type="password"
              placeholder="确认密码"
              class="input auth-field"
            />
          </Transition>
          <button @click="doAuth" class="btn primary" :disabled="authLoading">
            {{ authLoading ? '处理中...' : (authTab === 'login' ? '登录' : '注册') }}
          </button>
          <p v-if="authMessage" class="error">{{ authMessage }}</p>
        </div>
      </div>
    </section>

    <!-- 已登录状态：显示总览看板 -->
    <section v-else class="dashboard-section">
      <div class="dashboard-head">
        <div>
          <span class="eyebrow">总览</span>
          <h1>工作总览</h1>
          <p>继续编辑最近文档，或进入工作台处理新的 PPT 与 PDF。</p>
        </div>
        <router-link to="/workspace" class="btn primary">进入工作台</router-link>
      </div>

      <div class="overview-layout">
        <section class="recent-panel motion-card">
          <header class="panel-title-row">
            <div>
              <h2>最近文件</h2>
              <p>{{ hasRecentFiles ? `共 ${store.files.length} 个文件，${parsedFileCount} 个可继续编辑` : '上传或打开文件后会显示在这里。' }}</p>
            </div>
            <router-link to="/files" class="text-link">查看全部</router-link>
          </header>

          <div v-if="store.filesLoading && !hasRecentFiles" class="recent-empty">正在加载最近文件...</div>
          <div v-else-if="!hasRecentFiles" class="recent-empty">
            <h3>暂无最近文件</h3>
            <p>进入工作台上传 PPTX 或 PDF 后，可以从这里快速继续编辑。</p>
            <router-link to="/workspace" class="btn secondary">打开工作台</router-link>
          </div>
          <div v-else class="recent-list">
            <article v-for="file in recentFiles" :key="file.id" class="recent-item">
              <div class="recent-main">
                <b :title="file.original_filename">{{ file.original_filename }}</b>
                <span>{{ file.pages || 0 }} 页 · {{ fmtTime(file.updated_at || file.created_at) }}</span>
              </div>
              <span class="status-badge" :class="statusClass(file.parse_status)">{{ statusLabel(file.parse_status) }}</span>
              <button
                type="button"
                class="mini-action"
                :disabled="openingRecentId === file.id || file.parse_status !== 'success'"
                @click="openRecentFile(file)"
              >
                {{ openingRecentId === file.id ? "打开中" : "继续编辑" }}
              </button>
            </article>
          </div>
          <p v-if="recentMessage" class="error recent-error">{{ recentMessage }}</p>
        </section>

        <section class="metric-panel motion-card">
          <header>
            <h2>数据看板</h2>
            <p>当前账号的文档与生成概况。</p>
          </header>
          <div class="metric-grid">
            <article>
              <span>归档文件</span>
              <strong>{{ store.files.length }}</strong>
            </article>
            <article>
              <span>可继续编辑</span>
              <strong>{{ parsedFileCount }}</strong>
            </article>
            <article>
              <span>累计页数</span>
              <strong>{{ totalPageCount }}</strong>
            </article>
            <article>
              <span>近 30 天生成</span>
              <strong>{{ generateEventCount }}</strong>
            </article>
          </div>
        </section>
      </div>

      <div class="chart-panel motion-card">
        <div class="panel-title-row">
          <div>
            <h3>使用趋势分析</h3>
            <p>近 30 天上传、解析、生成、采用行为。</p>
          </div>
          <span v-if="statsLoading" class="loading-note">更新中</span>
        </div>
        <ChartPreview :option="usageTrendOption" :height="320" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-container { flex: 1; padding: var(--space-6); background: radial-gradient(circle at 16% 8%, rgba(139, 41, 66, 0.08), transparent 28%), var(--color-bg); }
.auth-section { min-height: calc(100vh - 118px); display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 420px); align-items: center; gap: clamp(32px, 8vw, 96px); max-width: var(--panel-max-width); margin: 0 auto; }
.auth-intro { animation: panel-in var(--motion-slow) var(--motion-ease) both; }
.eyebrow { display: inline-flex; align-items: center; min-height: 28px; padding: 0 10px; border-radius: 999px; background: var(--color-primary-soft); border: 1px solid var(--color-primary-border); color: var(--color-primary); font-size: 12px; font-weight: 800; }
.auth-intro h1 { margin: 18px 0 14px; color: var(--color-primary); font-size: clamp(34px, 5vw, 56px); line-height: 1.05; letter-spacing: 0; }
.auth-intro p { max-width: 560px; margin: 0; color: var(--color-text-soft); font-size: 16px; line-height: 1.8; }
.intro-steps { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-top: var(--space-6); color: var(--color-muted); }
.intro-steps span { display: inline-flex; align-items: center; gap: 8px; padding: 0; border: none; background: transparent; box-shadow: none; font-size: 13px; font-weight: 800; color: var(--color-text-soft); }
.intro-steps span::before { content: ""; width: 6px; height: 6px; border-radius: 999px; background: var(--color-primary); opacity: 0.72; }
.auth-card { background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(12px); padding: var(--space-8); border-radius: var(--radius-card); border: 1px solid var(--color-border); width: 100%; text-align: left; box-shadow: var(--shadow-card); animation: panel-in var(--motion-slow) var(--motion-ease) 50ms both; }
.auth-card h2 { margin: 0 0 8px; color: var(--color-text); font-size: 24px; line-height: 1.2; }
.auth-card p { margin: 0; color: var(--color-muted); }
.auth-tabs { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); margin: var(--space-6) 0 var(--space-5); padding: 4px; background: var(--color-bg-muted); border: 1px solid var(--color-border); border-radius: var(--radius-card); }
.auth-tabs button { min-height: var(--control-md); padding: 0 12px; border: none; border-radius: var(--radius-control); background: transparent; cursor: pointer; font-weight: 800; color: var(--color-muted); }
.auth-tabs button.active { background: var(--color-surface); color: var(--color-primary); box-shadow: var(--shadow-card); }
.auth-form { display: flex; flex-direction: column; gap: 12px; }
.input { min-height: var(--control-lg); padding: 0 14px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-control); outline: none; color: var(--color-text); background: var(--color-surface); transition: border-color var(--motion-base), box-shadow var(--motion-base), transform var(--motion-base); }
.input:focus { border-color: var(--color-primary); box-shadow: var(--shadow-focus); transform: translateY(-1px); }
.auth-field { animation: panel-in var(--motion-slow) var(--motion-ease) both; }
.auth-fields-enter-active, .auth-fields-leave-active { transition: opacity var(--motion-base) var(--motion-ease), transform var(--motion-base) var(--motion-ease), max-height var(--motion-slow) var(--motion-ease); overflow: hidden; }
.auth-fields-enter-from, .auth-fields-leave-to { opacity: 0; transform: translateY(-6px); max-height: 0; }
.auth-fields-enter-to, .auth-fields-leave-from { opacity: 1; transform: translateY(0); max-height: 60px; }
.btn { min-height: var(--control-lg); padding: 0 18px; border-radius: var(--radius-control); border: 1px solid transparent; cursor: pointer; font-weight: 800; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; text-align: center; transition: background var(--motion-base), border-color var(--motion-base), color var(--motion-base), transform var(--motion-base), box-shadow var(--motion-base); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.primary { background: var(--color-primary); color: white; }
.primary:hover:not(:disabled) { background: var(--color-primary-hover); transform: translateY(-2px); box-shadow: var(--shadow-card-hover); }
.secondary { background: var(--color-surface); border-color: var(--color-primary); color: var(--color-primary); }
.dashboard-section { max-width: var(--panel-max-width); width: 100%; margin: 0 auto; animation: panel-in var(--motion-slow) var(--motion-ease) both; }
.dashboard-head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); margin-bottom: var(--space-5); }
.dashboard-head h1 { margin: 10px 0 0; font-size: 28px; line-height: 1.2; color: var(--color-text); }
.dashboard-head p { margin: 8px 0 0; color: var(--color-muted); font-size: 14px; line-height: 1.7; }
.overview-layout { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr); align-items: stretch; gap: 16px; margin-bottom: 20px; }
.recent-panel, .metric-panel { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-card); box-shadow: var(--shadow-card); }
.recent-panel { padding: 18px; }
.metric-panel { padding: 18px; background: linear-gradient(135deg, #fffafb 0%, #f8eef1 100%); text-align: center; }
.metric-panel h2, .panel-title-row h2, .chart-panel h3 { margin: 0; color: var(--color-text); font-size: 17px; }
.metric-panel p, .panel-title-row p { margin: 6px 0 0; color: var(--color-muted); font-size: 13px; line-height: 1.7; }
.metric-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.metric-grid article { min-height: 58px; padding: 10px 8px; border: 1px solid rgba(139, 41, 66, 0.12); border-radius: var(--radius-control); background: rgba(255, 255, 255, 0.72); text-align: center; }
.metric-grid span { display: block; color: var(--color-muted); font-size: 12px; font-weight: 800; }
.metric-grid strong { display: block; margin-top: 4px; color: var(--color-primary); font-size: 22px; line-height: 1.1; }
.panel-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.text-link { color: var(--color-primary); font-size: 13px; font-weight: 800; text-decoration: none; white-space: nowrap; }
.text-link:hover { text-decoration: underline; }
.recent-list { display: flex; flex-direction: column; gap: 8px; }
.recent-item { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 10px; min-height: 48px; padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-control); background: rgba(255, 250, 251, 0.5); transition: border-color var(--motion-base), background var(--motion-base), transform var(--motion-base); }
.recent-item:hover { border-color: var(--color-primary-border); background: var(--color-primary-soft); transform: translateY(-1px); }
.recent-main { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.recent-main b { color: var(--color-text); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-main span { color: var(--color-muted); font-size: 12px; }
.status-badge { display: inline-flex; min-height: 24px; align-items: center; padding: 0 8px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-control); font-size: 11px; font-weight: 800; white-space: nowrap; }
.status-ok { background: var(--color-primary-soft); color: var(--color-primary); }
.status-err { border-color: #fecdd3; background: var(--color-danger-soft); color: var(--color-danger); }
.status-pending { border-color: var(--color-border); background: var(--color-bg-muted); color: var(--color-muted); }
.mini-action { min-height: 30px; padding: 0 10px; border: 1px solid var(--color-primary); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-primary); font: inherit; font-size: 12px; font-weight: 800; cursor: pointer; white-space: nowrap; }
.mini-action:hover:not(:disabled) { background: var(--color-primary); color: #fff; }
.mini-action:disabled { opacity: 0.45; cursor: not-allowed; }
.recent-empty { display: grid; place-items: center; min-height: 118px; padding: 16px; color: var(--color-muted); text-align: center; border: 1px dashed var(--color-primary-border); border-radius: var(--radius-control); background: rgba(255, 250, 251, 0.5); }
.recent-empty h3 { margin: 0 0 8px; color: var(--color-text); font-size: 16px; }
.recent-empty p { margin: 0 0 14px; font-size: 13px; line-height: 1.7; }
.chart-panel { background: var(--color-surface); padding: var(--panel-padding); border-radius: var(--radius-card); border: 1px solid var(--color-border); margin-bottom: 20px; box-shadow: var(--shadow-card); animation: panel-in var(--motion-slow) var(--motion-ease) 150ms both; }
.loading-note { color: var(--color-primary); font-size: 12px; font-weight: 800; white-space: nowrap; }
.action-row { display: flex; gap: 16px; justify-content: center; }
.error { color: var(--color-danger); font-size: 14px; background: var(--color-danger-soft); border: 1px solid #fee2e2; padding: 10px 12px; border-radius: var(--radius-control); }
.recent-error { margin: 12px 0 0; }
@media (max-width: 900px) {
  .auth-section { grid-template-columns: 1fr; gap: var(--space-8); min-height: auto; padding: var(--space-6) 0; }
  .auth-intro { text-align: center; }
  .auth-intro p { margin: 0 auto; }
  .intro-steps { justify-content: center; }
  .overview-layout { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  .home-container { padding: var(--space-4); }
  .dashboard-head { align-items: stretch; flex-direction: column; }
  .recent-item { grid-template-columns: 1fr; align-items: stretch; }
  .panel-title-row { flex-direction: column; }
  .auth-card { padding: var(--space-5); }
}
</style>
