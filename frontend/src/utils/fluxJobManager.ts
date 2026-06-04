import type { FluxGenerateImageResponse, FluxImageJob, SlideState } from "../types";

type FluxJobMap = Record<string, FluxImageJob>;

export function createFluxRequestKey(slideId: string) {
  return `${slideId}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function beginFluxJob(
  jobs: FluxJobMap,
  slide: SlideState,
  requestKey: string,
  startedAt = Date.now()
) {
  jobs[slide.id] = { status: "loading", startedAt, requestKey };
  slide.statusFluxImage = "loading";
  slide.errorFluxImage = undefined;
}

export function shouldApplyFluxJob(jobs: FluxJobMap, slideId: string, requestKey: string) {
  return jobs[slideId]?.requestKey === requestKey;
}

export function completeFluxJob(
  jobs: FluxJobMap,
  slides: SlideState[],
  slideId: string,
  requestKey: string,
  result: FluxGenerateImageResponse
) {
  if (!shouldApplyFluxJob(jobs, slideId, requestKey)) return false;
  const slide = slides.find((s) => s.id === slideId);
  if (!slide) return false;

  slide.fluxImage = result;
  slide.statusFluxImage = "success";
  slide.errorFluxImage = undefined;
  jobs[slideId] = { ...jobs[slideId], status: "success" };
  return true;
}

export function failFluxJob(
  jobs: FluxJobMap,
  slides: SlideState[],
  slideId: string,
  requestKey: string,
  message: string
) {
  if (!shouldApplyFluxJob(jobs, slideId, requestKey)) return false;
  const slide = slides.find((s) => s.id === slideId);
  if (!slide) return false;

  slide.statusFluxImage = "error";
  slide.errorFluxImage = message;
  jobs[slideId] = { ...jobs[slideId], status: "error" };
  return true;
}

export function clearFluxRuntimeState(jobs: FluxJobMap, slides: SlideState[]) {
  for (const key of Object.keys(jobs)) {
    delete jobs[key];
  }
  for (const slide of slides) {
    slide.fluxImage = undefined;
    slide.statusFluxImage = "idle";
    slide.errorFluxImage = undefined;
  }
}
