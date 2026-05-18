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
        <span class="nav-group">流程</span>
        <router-link to="/home" class="nav-item">总览</router-link>
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
body { margin: 0; font-family: 'Inter', -apple-system, sans-serif; -webkit-font-smoothing: antialiased; background: #fafafa; color: #1a1a1a; }
* { box-sizing: border-box; }

.app-shell { min-height: 100vh; display: flex; flex-direction: column; }

.navbar { height: 70px; background: #ffffff; border-bottom: 1px solid #e8e0e2; display: flex; align-items: center; padding: 0 40px; gap: 40px; }
.brand { font-size: 20px; font-weight: 800; color: #8b2942; cursor: pointer; letter-spacing: -0.02em; }
.nav-links { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; row-gap: 10px; max-width: 72vw; }
.nav-group { font-size: 11px; font-weight: 800; color: #9a9a9a; text-transform: uppercase; letter-spacing: 0.04em; margin-right: 4px; }
.nav-divider { width: 1px; height: 18px; background: #e8e0e2; margin: 0 6px; }
.nav-item { text-decoration: none; color: #7a7a7a; font-weight: 600; font-size: 13px; transition: color 0.2s; white-space: nowrap; }
.nav-item.sub { font-size: 13px; }
.nav-item.illus { color: #8b2942; }
.nav-item.router-link-active { color: #8b2942; font-weight: 700; }
.nav-item.illus.router-link-active { color: #8b2942; }
.nav-item:hover { color: #8b2942; }
.nav-item.illus:hover { color: #6d2135; }

.user-area { margin-left: auto; display: flex; align-items: center; gap: 16px; }
.username { font-size: 14px; font-weight: 600; color: #3d3d3d; }
.logout-btn { background: #ffffff; color: #8b2942; border: 1px solid #d9cdd1; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 12px; }
.logout-btn:hover { background: #fffafb; border-color: #8b2942; }

.main-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

/* 路由切换动画 */
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
