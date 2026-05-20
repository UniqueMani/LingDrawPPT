<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { store } from './store';
import { me, setAuthToken } from './api/client';
import { useRouter } from 'vue-router';

const router = useRouter();
const navOpen = ref(false);

function logout() {
  store.setToken("");
  store.currentUser = null;
  setAuthToken("");
  store.addLog("用户已退出登录");
  navOpen.value = false;
  router.push('/home');
}

function closeNav() {
  navOpen.value = false;
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
      <div class="brand" @click="router.push('/home'); closeNav()">LingDraw PPT Studio</div>

      <!-- 桌面导航 -->
      <nav v-if="store.token" class="nav-links desktop-nav">
        <span class="nav-group">流程</span>
        <router-link to="/home" class="nav-item">总览</router-link>
        <router-link to="/workspace" class="nav-item">工作台</router-link>
      </nav>

      <div class="user-area">
        <template v-if="store.token">
          <router-link to="/profile" class="username-link desktop-only">{{ store.currentUser?.username }}</router-link>
          <button class="logout-btn desktop-only" @click="logout">退出</button>
          <!-- 汉堡按钮（移动端） -->
          <button class="hamburger" :class="{ open: navOpen }" aria-label="菜单" @click="navOpen = !navOpen">
            <span /><span /><span />
          </button>
        </template>
      </div>
    </header>

    <!-- 移动端抽屉菜单 -->
    <div v-if="store.token && navOpen" class="mobile-menu" @click.self="closeNav">
      <nav class="mobile-nav">
        <router-link to="/home" class="m-item" @click="closeNav">总览</router-link>
        <router-link to="/workspace" class="m-item" @click="closeNav">工作台</router-link>
        <router-link to="/profile" class="m-item" @click="closeNav">{{ store.currentUser?.username }}</router-link>
        <button class="m-item m-logout" @click="logout">退出登录</button>
      </nav>
    </div>

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

.navbar { height: 70px; background: #ffffff; border-bottom: 1px solid #e8e0e2; display: flex; align-items: center; padding: 0 24px; gap: 24px; position: relative; z-index: 100; }
.brand { font-size: 20px; font-weight: 800; color: #8b2942; cursor: pointer; letter-spacing: -0.02em; flex-shrink: 0; }
.nav-links { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; row-gap: 10px; }
.nav-group { font-size: 11px; font-weight: 800; color: #9a9a9a; text-transform: uppercase; letter-spacing: 0.04em; margin-right: 4px; }
.nav-item { text-decoration: none; color: #7a7a7a; font-weight: 600; font-size: 13px; transition: color 0.2s; white-space: nowrap; }
.nav-item.router-link-active { color: #8b2942; font-weight: 700; }
.nav-item:hover { color: #8b2942; }

.user-area { margin-left: auto; display: flex; align-items: center; gap: 12px; }
.username-link { font-size: 14px; font-weight: 600; color: #3d3d3d; text-decoration: none; padding: 4px 8px; border-radius: 4px; transition: color 0.15s, background 0.15s; }
.username-link:hover { color: #8b2942; background: #fdf5f7; }
.username-link.router-link-active { color: #8b2942; }
.logout-btn { background: #ffffff; color: #8b2942; border: 1px solid #d9cdd1; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 12px; }
.logout-btn:hover { background: #fffafb; border-color: #8b2942; }

/* 汉堡按钮 */
.hamburger {
  display: none;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  width: 36px;
  height: 36px;
  padding: 6px;
  background: none;
  border: 1px solid #d9cdd1;
  border-radius: 6px;
  cursor: pointer;
}
.hamburger span {
  display: block;
  height: 2px;
  background: #3d3d3d;
  border-radius: 2px;
  transition: transform 0.2s, opacity 0.2s;
}
.hamburger.open span:nth-child(1) { transform: translateY(7px) rotate(45deg); }
.hamburger.open span:nth-child(2) { opacity: 0; }
.hamburger.open span:nth-child(3) { transform: translateY(-7px) rotate(-45deg); }

/* 移动菜单 */
.mobile-menu {
  position: fixed;
  inset: 70px 0 0 0;
  background: rgba(0,0,0,0.3);
  z-index: 99;
}
.mobile-nav {
  background: #fff;
  display: flex;
  flex-direction: column;
  padding: 12px 0;
  border-bottom: 1px solid #e8e0e2;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.m-item {
  display: block;
  padding: 14px 24px;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
  text-decoration: none;
  cursor: pointer;
  background: none;
  border: none;
  text-align: left;
  width: 100%;
  transition: background 0.12s;
}
.m-item:hover, .m-item.router-link-active { background: #fdf5f7; color: #8b2942; }
.m-logout { color: #8b2942; border-top: 1px solid #f0e8eb; margin-top: 8px; padding-top: 16px; }

/* 响应式断点 */
@media (max-width: 640px) {
  .desktop-nav { display: none; }
  .desktop-only { display: none !important; }
  .hamburger { display: flex; }
  .navbar { padding: 0 16px; gap: 12px; }
}

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

