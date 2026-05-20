<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { me, setAuthToken } from "./api/client";
import { store } from "./store";

const router = useRouter();

function logout() {
  store.setToken("");
  store.currentUser = null;
  setAuthToken("");
  store.addLog("用户已退出登录");
  router.push("/home");
}

onMounted(async () => {
  if (store.token) {
    try {
      setAuthToken(store.token);
      store.currentUser = await me(store.baseUrl);
      store.addLog(`欢迎回来，${store.currentUser.username}`);
    } catch {
      store.setToken("");
      setAuthToken("");
      store.currentUser = null;
      router.push("/home");
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
          <router-link to="/profile" class="username-link">
            {{ store.currentUser?.username || "个人中心" }}
          </router-link>
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
body {
  margin: 0;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
  background: var(--color-bg);
  color: var(--color-text);
}

* {
  box-sizing: border-box;
}

.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.navbar {
  height: 70px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  padding: 0 40px;
  gap: 40px;
  position: sticky;
  top: 0;
  z-index: 20;
}

.brand {
  font-size: 20px;
  font-weight: 800;
  color: var(--color-primary);
  cursor: pointer;
  letter-spacing: 0;
  transition:
    transform var(--motion-base) var(--motion-ease),
    color var(--motion-base) var(--motion-ease);
}

.brand:hover {
  color: var(--color-primary-hover);
  transform: translateY(-1px);
}

.nav-links {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 18px;
  row-gap: 10px;
  max-width: 72vw;
}

.nav-group {
  font-size: 11px;
  font-weight: 800;
  color: var(--color-muted-light);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-right: 4px;
}

.nav-item,
.username-link {
  text-decoration: none;
  color: var(--color-muted);
  font-weight: 600;
  font-size: 13px;
  transition:
    color var(--motion-base),
    transform var(--motion-base);
  white-space: nowrap;
}

.nav-item.router-link-active,
.username-link.router-link-active {
  color: var(--color-primary);
  font-weight: 700;
}

.nav-item:hover,
.username-link:hover {
  color: var(--color-primary);
  transform: translateY(-1px);
}

.user-area {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 16px;
}

.logout-btn {
  background: var(--color-surface);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-border);
  padding: 0 14px;
  min-height: var(--control-sm);
  border-radius: var(--radius-control);
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
}

.logout-btn:hover {
  background: var(--color-primary-soft);
  border-color: var(--color-primary);
  transform: translateY(-1px);
}

.main-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.fade-enter-active,
.fade-leave-active {
  transition:
    opacity var(--motion-slow) var(--motion-ease),
    transform var(--motion-slow) var(--motion-ease);
}

.fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

@media (max-width: 720px) {
  .navbar {
    height: auto;
    min-height: 64px;
    padding: 12px 16px;
    gap: 16px;
    flex-wrap: wrap;
  }

  .brand {
    font-size: 18px;
  }

  .nav-links {
    max-width: none;
  }

  .user-area {
    margin-left: 0;
  }
}
</style>
