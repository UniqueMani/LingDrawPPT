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
  {
    path: "/profile",
    name: "Profile",
    component: () => import("../views/ProfileView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/admin",
    name: "Admin",
    component: () => import("../views/AdminView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach((to, _from, next) => {
  if (to.meta.requiresAuth && !store.token) {
    next("/home");
  } else if (to.meta.requiresAdmin && store.currentUser && !store.currentUser.is_admin) {
    next("/home");
  } else if (store.currentUser?.is_admin && (to.path === "/home" || to.path === "/workspace")) {
    next("/admin");
  } else {
    next();
  }
});

export default router;
