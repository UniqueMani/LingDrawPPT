import { computed, reactive } from "vue";
import { listFiles } from "../api/client";
import type { FileRecordDTO, SlideState, UserDTO } from "../types";

const base = reactive({
  baseUrl: "http://127.0.0.1:8000",
  token: localStorage.getItem("token") || "",
  currentUser: null as UserDTO | null,
  slides: [] as SlideState[],
  currentIndex: 0,
  docName: "",
  currentFileId: 0,
  files: [] as FileRecordDTO[],
  filesLoading: false,
  activityLogs: ["欢迎进入 LingDraw PPT Studio"],
  usageStats: {} as Record<string, number>,

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
    if (!base.token || base.currentUser?.is_admin) return;
    base.filesLoading = true;
    try {
      base.files = await listFiles(base.baseUrl);
    } catch (error: any) {
      base.addLog(`文件列表加载失败: ${error?.message || String(error)}`);
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
