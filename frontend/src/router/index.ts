import { createRouter, createWebHashHistory } from "vue-router";
import { store } from "../store";

const routes = [
  {
    path: "/",
    redirect: "/home",
  },
  {
    path: "/home",
    name: "Home",
    component: () => import("../views/HomeView.vue"),
  },
  {
    path: "/upload",
    redirect: "/workspace",
  },
  {
    path: "/workspace",
    name: "Workspace",
    component: () => import("../views/WorkspaceView.vue"),
    meta: { requiresAuth: true },
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach((to, _from, next) => {
  if (to.meta.requiresAuth && !store.token) {
    next("/home");
  } else {
    next();
  }
});

export default router;
