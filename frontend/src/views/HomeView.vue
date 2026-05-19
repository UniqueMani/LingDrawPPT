<script setup lang="ts">
import { ref } from 'vue';
import { store } from '../store';
import { login, register, setAuthToken } from '../api/client';
import ChartPreview from '../components/ChartPreview.vue';

const authTab = ref<'login' | 'register'>('login');
const authName = ref("");
const authPwd = ref("");
const regFullName = ref("");
const regEmail = ref("");
const regOrg = ref("");
const regConfirmPwd = ref("");
const authLoading = ref(false);
const authMessage = ref("");

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
          full_name: regFullName.value,
          email: regEmail.value,
          organization: regOrg.value,
        });
    store.setToken(resp.token);
    store.currentUser = resp.user;
    setAuthToken(resp.token);
    store.addLog(`用户 ${resp.user.username} 登录成功`);
  } catch (e: any) {
    authMessage.value = e?.message || String(e);
  } finally {
    authLoading.value = false;
  }
}

// 首页图表数据（用于总览展示）
const usageTrendOption = {
  tooltip: { trigger: 'axis' },
  grid: { left: 24, right: 16, top: 24, bottom: 24 },
  xAxis: { type: 'category', data: ['上传', '解析', '生成', '采用'] },
  yAxis: { type: 'value' },
  series: [{ type: 'line', smooth: true, data: [10, 25, 18, 12] }],
};
</script>

<template>
  <div class="home-container">
    <!-- 未登录状态：显示登录/注册 -->
    <section v-if="!store.token" class="auth-section">
      <div class="auth-card">
        <h1>LingDraw PPT Studio</h1>
        <p>让 PPT 可视化更简单</p>
        <div class="auth-tabs">
          <button :class="{ active: authTab === 'login' }" @click="authTab = 'login'">登录</button>
          <button :class="{ active: authTab === 'register' }" @click="authTab = 'register'">注册</button>
        </div>
        <div class="auth-form">
          <input v-model="authName" placeholder="用户名" class="input" />
          <input v-model="authPwd" type="password" placeholder="密码" class="input" />
          <button @click="doAuth" class="btn primary" :disabled="authLoading">
            {{ authLoading ? '处理中...' : (authTab === 'login' ? '登录' : '注册') }}
          </button>
          <p v-if="authMessage" class="error">{{ authMessage }}</p>
        </div>
      </div>
    </section>

    <!-- 已登录状态：显示总览看板 -->
    <section v-else class="dashboard-section">
      <div class="dashboard-grid">
        <div class="stat-card">
          <div class="label">当前文件</div>
          <div class="value">{{ store.docName || '未上传' }}</div>
        </div>
        <div class="stat-card">
          <div class="label">页面总数</div>
          <div class="value">{{ store.slides.length }}</div>
        </div>
        <div class="stat-card">
          <div class="label">已生成结果</div>
          <div class="value">{{ store.generatedCount }}</div>
        </div>
      </div>
      
      <div class="chart-panel">
        <h3>使用趋势分析</h3>
        <ChartPreview :option="usageTrendOption" :height="300" />
      </div>

      <div class="action-row">
        <router-link to="/workspace" class="btn primary">进入工作台（上传与配图）</router-link>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-container { padding: 20px; }
.auth-section { display: flex; justify-content: center; padding-top: 50px; }
.auth-card { background: white; padding: 40px; border-radius: 16px; border: 1px solid #dcefe5; width: 400px; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.05); }
.auth-tabs { display: flex; gap: 10px; margin: 20px 0; border-bottom: 1px solid #eee; }
.auth-tabs button { flex: 1; padding: 10px; border: none; background: none; cursor: pointer; font-weight: bold; }
.auth-tabs button.active { border-bottom: 2px solid #1f9d60; color: #1f9d60; }
.auth-form { display: flex; flex-direction: column; gap: 12px; }
.input { padding: 12px; border: 1px solid #ddd; border-radius: 8px; }
.btn { padding: 12px; border-radius: 8px; border: none; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; text-align: center; }
.primary { background: #1f9d60; color: white; }
.secondary { background: white; border: 1px solid #1f9d60; color: #1f9d60; }
.dashboard-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px; }
.stat-card { background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2f3ea; }
.label { font-size: 14px; color: #666; }
.value { font-size: 24px; font-weight: bold; color: #1f9d60; }
.chart-panel { background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2f3ea; margin-bottom: 20px; }
.action-row { display: flex; gap: 16px; justify-content: center; }
.error { color: #b91c1c; font-size: 14px; }
</style>
