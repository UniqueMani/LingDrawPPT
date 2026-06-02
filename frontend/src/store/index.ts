import { computed, reactive } from "vue";
import type { FileRecord, SlideState, UserDTO } from "../types";
import { listFiles } from "../api/client";

const base = reactive({
  baseUrl: "http://127.0.0.1:8000",
  token: localStorage.getItem("token") || "",
  currentUser: null as UserDTO | null,
  slides: [] as SlideState[],
  currentIndex: 0,
  docName: "",
  currentFileId: 0 as number,
  activityLogs: ["欢迎进入 LingDraw PPT Studio"],
  usageStats: {} as Record<string, number>,
  files: [] as FileRecord[],
  filesLoading: false,

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
  async fetchFiles() {
    if (!base.token) return;
    base.filesLoading = true;
    try {
      base.files = await listFiles(base.baseUrl);
    } catch {
      // 静默失败
    } finally {
      base.filesLoading = false;
    }
  },
});

export const store = Object.assign(base, {
  isLoggedIn: computed(() => !!base.token),
  currentSlide: computed(() => base.slides[base.currentIndex] || null),
  generatedCount: computed(
    () => base.slides.filter((s: SlideState) => s.analyze || s.illustration).length
  ),
});
