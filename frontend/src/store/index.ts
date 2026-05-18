import { computed, reactive } from "vue";
import type { SlideState, UserDTO } from "../types";

const base = reactive({
  baseUrl: "http://127.0.0.1:8000",
  token: localStorage.getItem("token") || "",
  currentUser: null as UserDTO | null,
  slides: [] as SlideState[],
  currentIndex: 0,
  docName: "",
  activityLogs: ["欢迎进入 LingDraw PPT Studio"],

  setToken(token: string) {
    base.token = token;
    if (token) {
      localStorage.setItem("token", token);
    } else {
      localStorage.removeItem("token");
    }
  },
  addLog(msg: string) {
    base.activityLogs.unshift(`${new Date().toLocaleTimeString()} - ${msg}`);
  },
});

export const store = Object.assign(base, {
  isLoggedIn: computed(() => !!base.token),
  currentSlide: computed(() => base.slides[base.currentIndex] || null),
  generatedCount: computed(
    () => base.slides.filter((s: SlideState) => s.analyze || s.illustration).length
  ),
});
