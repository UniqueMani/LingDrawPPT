<script setup lang="ts">
import { onMounted } from 'vue';
import { store } from './store';
import { me, setAuthToken } from './api/client';
import { useRouter } from 'vue-router';

const router = useRouter();

function logout() {
  store.setToken("");
  store.currentUser = null;
  setAuthToken("");
  store.addLog("用户已退出登录");
  router.push('/home');
}

onMounted(async () => {
  if (store.token) {
    try {
      setAuthToken(store.token);
      store.currentUser = await me(store.baseUrl);
      store.addLog(`欢迎回来，${store.currentUser.username}`);
    } catch {
      store.setToken("");
    }
  }
});
</script>

<template>
  <div class="app-shell">
    <header class="navbar">
      <div class="brand" @click="router.push('/home')">LingDraw PPT Studio</div>
      <nav v-if="store.token" class="nav-links">
        <router-link to="/home" class="nav-item">总览</router-link>
        <router-link to="/upload" class="nav-item">上传</router-link>
        <router-link to="/workspace" class="nav-item">工作台</router-link>
      </nav>
      <div class="user-area">
        <template v-if="store.token">
          <span class="username">{{ store.currentUser?.username }}</span>
          <button class="logout-btn" @click="logout">退出</button>
        </template>
      </div>
    </header>

    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style>
/* 全局基础样式 */
body { margin: 0; font-family: 'Inter', -apple-system, sans-serif; -webkit-font-smoothing: antialiased; background: #f8fafc; color: #0f172a; }
* { box-sizing: border-box; }

.app-shell { min-height: 100vh; display: flex; flex-direction: column; }

.navbar { height: 70px; background: white; border-bottom: 1px solid #e2e8f0; display: flex; align-items: center; padding: 0 40px; gap: 40px; }
.brand { font-size: 20px; font-weight: 800; color: #1f9d60; cursor: pointer; }
.nav-links { display: flex; gap: 24px; }
.nav-item { text-decoration: none; color: #64748b; font-weight: 600; font-size: 14px; transition: color 0.2s; }
.nav-item.router-link-active { color: #1f9d60; }
.nav-item:hover { color: #1f9d60; }

.user-area { margin-left: auto; display: flex; align-items: center; gap: 16px; }
.username { font-size: 14px; font-weight: 600; }
.logout-btn { background: #fee2e2; color: #b91c1c; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 12px; }

.main-content { flex: 1; position: relative; }

/* 路由切换动画 */
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
