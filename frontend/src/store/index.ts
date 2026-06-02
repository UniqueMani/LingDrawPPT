import { reactive, computed } from 'vue';
import type { SlideState, UserDTO } from '../types';

export const store = reactive({
  baseUrl: "http://127.0.0.1:8000",
  token: localStorage.getItem("token") || "",
  currentUser: null as UserDTO | null,
  slides: [] as SlideState[],
  currentIndex: 0,
  docName: "",
  activityLogs: ["欢迎进入 LingDraw PPT Studio"],

  // 状态计算
  isLoggedIn: computed(() => !!store.token),
  currentSlide: computed(() => store.slides[store.currentIndex] || null),
  generatedCount: computed(() => store.slides.filter((s) => s.analyze || s.illustration).length),
  
  // 方法
  setToken(token: string) {
    store.token = token;
    if (token) {
      localStorage.setItem("token", token);
    } else {
      localStorage.removeItem("token");
    }
  },
  addLog(msg: string) {
    store.activityLogs.unshift(`${new Date().toLocaleTimeString()} - ${msg}`);
  }
});
