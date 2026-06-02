import { createRouter, createWebHashHistory } from 'vue-router';
import { store } from '../store';

const routes = [
  {
    path: '/',
    redirect: '/home'
  },
  {
    path: '/home',
    name: 'Home',
    component: () => import('../views/HomeView.vue')
  },
  {
    path: '/upload',
    name: 'Upload',
    component: () => import('../views/UploadView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/workspace',
    name: 'Workspace',
    component: () => import('../views/WorkspaceView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/charts/intent',
    name: 'ChartIntent',
    component: () => import('../views/ChartIntentView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/charts/code',
    name: 'ChartCode',
    component: () => import('../views/ChartCodeView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/illustration/prompt',
    name: 'IllustrationPrompt',
    component: () => import('../views/IllustrationPromptView.vue'),
    meta: { requiresAuth: true }
  }
];

const router = createRouter({
  history: createWebHashHistory(),
  routes
});

// 路由守卫：未登录时强制跳转登录（由于本项目首页即登录，这里做个简单跳转）
router.beforeEach((to, from, next) => {
  if (to.meta.requiresAuth && !store.token) {
    next('/home');
  } else {
    next();
  }
});

export default router;
