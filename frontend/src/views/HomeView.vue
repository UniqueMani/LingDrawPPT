<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { store } from '../store';
import { login, register, setAuthToken, getStats } from '../api/client';
import ChartPreview from '../components/ChartPreview.vue';

const authTab = ref<'login' | 'register'>('login');
const authName = ref("");
const authPwd = ref("");
const regConfirmPwd = ref("");
const authLoading = ref(false);
const authMessage = ref("");

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
    store.fetchFiles();
    await loadStats();
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
    yAxis: { type: 'value' as const, min: 0, interval: 1, splitLine: { lineStyle: { color: '#f0e8eb' } } },
    color: ['#8b2942'],
    series: [{ type: 'line' as const, smooth: true, data, areaStyle: { color: 'rgba(139, 41, 66, 0.08)' } }],
  };
});

onMounted(() => {
  if (store.token) loadStats();
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
          <h1>项目状态</h1>
        </div>
        <div class="head-links">
          <router-link to="/workspace" class="btn primary">进入工作台</router-link>
          <router-link to="/files" class="btn secondary">我的文件</router-link>
        </div>
      </div>

      <div class="dashboard-grid">
        <div class="stat-card motion-card">
          <div class="label">归档文件</div>
          <div class="value">{{ store.files.length }}</div>
        </div>
        <div class="stat-card motion-card">
          <div class="label">当前文件</div>
          <div class="value">{{ store.docName || '未上传' }}</div>
        </div>
        <div class="stat-card motion-card">
          <div class="label">页面总数</div>
          <div class="value">{{ store.slides.length }}</div>
        </div>
        <div class="stat-card motion-card">
          <div class="label">已生成结果</div>
          <div class="value">{{ store.generatedCount }}</div>
        </div>
      </div>
      
      <div class="chart-panel motion-card">
        <h3>使用趋势分析</h3>
        <ChartPreview :option="usageTrendOption" :height="300" />
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
.head-links { display: flex; gap: 10px; flex-shrink: 0; }
.dashboard-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }
.stat-card { background: var(--color-surface); padding: var(--space-5); min-height: 112px; border-radius: var(--radius-card); border: 1px solid var(--color-border); box-shadow: var(--shadow-card); animation: panel-in var(--motion-slow) var(--motion-ease) both; }
.stat-card:nth-child(2) { animation-delay: 50ms; }
.stat-card:nth-child(3) { animation-delay: 100ms; }
.stat-card:nth-child(4) { animation-delay: 150ms; }
.label { font-size: 13px; color: var(--color-muted); font-weight: 600; }
.value { margin-top: 10px; font-size: 28px; line-height: 1.15; font-weight: 800; color: var(--color-primary); overflow-wrap: anywhere; animation: panel-in var(--motion-slow) var(--motion-ease) both; }
.chart-panel { background: var(--color-surface); padding: var(--panel-padding); border-radius: var(--radius-card); border: 1px solid var(--color-border); margin-bottom: 20px; box-shadow: var(--shadow-card); animation: panel-in var(--motion-slow) var(--motion-ease) 150ms both; }
.chart-panel h3 { margin: 0 0 14px; color: var(--color-text); font-size: 16px; }
.action-row { display: flex; gap: 16px; justify-content: center; }
.error { color: var(--color-danger); font-size: 14px; background: var(--color-danger-soft); border: 1px solid #fee2e2; padding: 10px 12px; border-radius: var(--radius-control); }
@media (max-width: 900px) {
  .auth-section { grid-template-columns: 1fr; gap: var(--space-8); min-height: auto; padding: var(--space-6) 0; }
  .auth-intro { text-align: center; }
  .auth-intro p { margin: 0 auto; }
  .intro-steps { justify-content: center; }
}
@media (max-width: 720px) {
  .home-container { padding: var(--space-4); }
  .dashboard-grid { grid-template-columns: 1fr 1fr; }
  .dashboard-head { align-items: stretch; flex-direction: column; }
  .head-links { flex-direction: column; }
  .auth-card { padding: var(--space-5); }
}
</style>
