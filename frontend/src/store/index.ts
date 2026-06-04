import { computed, reactive } from "vue";
import { listFiles } from "../api/client";
import type { AnalyzeDocumentResponse, FileRecord, FluxImageJob, SlideState, UserDTO } from "../types";

const WORKSPACE_DRAFT_PREFIX = "lingdraw.workspaceDraft.";

function draftKey(fileId: number) {
  return `${WORKSPACE_DRAFT_PREFIX}${fileId}`;
}

function settledAnalyzeStatus(slide: SlideState) {
  if (slide.statusAnalyze === "loading") return slide.analyze || slide.intentSemantic || slide.chartCode ? "success" : "idle";
  return slide.statusAnalyze;
}

function settledIllustrationStatus(slide: SlideState) {
  if (slide.statusIllustration === "loading") return slide.illustration || slide.vizIllustration ? "success" : "idle";
  return slide.statusIllustration;
}

function settledFluxStatus(slide: SlideState) {
  if (slide.statusFluxImage === "loading") return slide.fluxImage ? "success" : "idle";
  return slide.statusFluxImage;
}

const base = reactive({
  baseUrl: "http://127.0.0.1:8000",
  token: localStorage.getItem("token") || "",
  currentUser: null as UserDTO | null,
  slides: [] as SlideState[],
  currentIndex: 0,
  docName: "",
  currentFileId: 0,
  docConsistency: null as AnalyzeDocumentResponse | null,
  fluxJobs: {} as Record<string, FluxImageJob>,
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
    } catch (error: any) {
      base.addLog(`文件列表更新失败: ${error?.message || String(error)}`);
    } finally {
      base.filesLoading = false;
    }
  },
  saveCurrentWorkspaceDraft() {
    if (!base.currentFileId || !base.slides.length) return false;
    const payload = {
      version: 1,
      savedAt: Date.now(),
      fileId: base.currentFileId,
      docName: base.docName,
      currentIndex: base.currentIndex,
      docConsistency: base.docConsistency,
      slides: base.slides.map((slide) => ({
        page: slide.page,
        input: slide.input,
        analyze: slide.analyze,
        illustration: slide.illustration,
        intentSemantic: slide.intentSemantic,
        chartCode: slide.chartCode,
        vizIllustration: slide.vizIllustration,
        fluxImage: slide.fluxImage,
        statusAnalyze: settledAnalyzeStatus(slide),
        statusIllustration: settledIllustrationStatus(slide),
        statusFluxImage: settledFluxStatus(slide),
        errorAnalyze: slide.errorAnalyze,
        errorIllustration: slide.errorIllustration,
        errorFluxImage: slide.errorFluxImage,
        history: slide.history,
      })),
    };
    localStorage.setItem(draftKey(base.currentFileId), JSON.stringify(payload));
    return true;
  },
  restoreWorkspaceDraft(fileId: number) {
    const raw = localStorage.getItem(draftKey(fileId));
    if (!raw) return false;
    try {
      const draft = JSON.parse(raw);
      if (!draft || !Array.isArray(draft.slides)) return false;
      const byPage = new Map<number, any>(
        draft.slides
          .filter((item: any) => item && Number.isFinite(Number(item.page)))
          .map((item: any) => [Number(item.page), item])
      );
      base.slides = base.slides.map((slide) => {
        const saved = byPage.get(slide.page);
        if (!saved) return slide;
        return {
          ...slide,
          input: saved.input || slide.input,
          analyze: saved.analyze,
          illustration: saved.illustration,
          intentSemantic: saved.intentSemantic,
          chartCode: saved.chartCode,
          vizIllustration: saved.vizIllustration,
          fluxImage: saved.fluxImage,
          statusAnalyze: saved.statusAnalyze || (saved.analyze || saved.intentSemantic || saved.chartCode ? "success" : "idle"),
          statusIllustration: saved.statusIllustration || (saved.illustration || saved.vizIllustration ? "success" : "idle"),
          statusFluxImage: saved.statusFluxImage || (saved.fluxImage ? "success" : "idle"),
          errorAnalyze: saved.errorAnalyze,
          errorIllustration: saved.errorIllustration,
          errorFluxImage: saved.errorFluxImage,
          history: Array.isArray(saved.history) ? saved.history : slide.history,
        };
      });
      base.currentIndex = Math.min(
        Math.max(0, Number(draft.currentIndex) || 0),
        Math.max(0, base.slides.length - 1)
      );
      base.docConsistency = draft.docConsistency || base.docConsistency;
      return true;
    } catch (error: any) {
      base.addLog(`工作台草稿恢复失败: ${error?.message || String(error)}`);
      return false;
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
