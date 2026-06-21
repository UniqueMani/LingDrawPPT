import type { InsertSession, NormalizedRect, TextBlock } from "../types";

export const INSERT_SESSION_KEY = "lingdraw.insertSession";
export const INSERT_PATCH_KEY = "lingdraw.pptInsertPatch";

export function parseAspectRatio(value: string): number {
  const [w, h] = (value || "16:9").split(":").map(Number);
  if (w > 0 && h > 0) return w / h;
  return 16 / 9;
}

export function clampPlacementRect(
  rect: NormalizedRect,
  aspectRatioLabel: string,
  slideAspect = 16 / 9
): NormalizedRect {
  const imageAspect = parseAspectRatio(aspectRatioLabel);
  let width = Math.max(0.12, Math.min(0.92, rect.width));
  let height = (width * slideAspect) / imageAspect;
  if (height > 0.92) {
    height = 0.92;
    width = (height * imageAspect) / slideAspect;
  }
  height = Math.max(0.08, Math.min(0.92, height));
  const x = Math.max(0, Math.min(rect.x, 1 - width));
  const y = Math.max(0, Math.min(rect.y, 1 - height));
  return { x, y, width, height };
}

export function heightForNormalizedWidth(
  width: number,
  aspectRatioLabel: string,
  slideAspect: number
): number {
  return (width * slideAspect) / parseAspectRatio(aspectRatioLabel);
}

export function buildInsertSession(input: {
  fileId: number;
  page: number;
  imageUrl: string;
  aspectRatio: string;
  previewUrl: string;
  thumbnailUrl?: string;
  textBlocks: TextBlock[];
  docName: string;
  source: "flux" | "chart";
}): InsertSession {
  return {
    fileId: input.fileId,
    page: input.page,
    imageUrl: input.imageUrl,
    aspectRatio: input.aspectRatio,
    previewUrl: input.previewUrl,
    thumbnailUrl: input.thumbnailUrl,
    textBlocks: input.textBlocks,
    docName: input.docName,
    source: input.source,
  };
}

export function saveInsertSession(session: InsertSession) {
  sessionStorage.setItem(INSERT_SESSION_KEY, JSON.stringify(session));
}

export function inferAspectRatio(width: number, height: number) {
  if (width <= 0 || height <= 0) return "16:9";
  const ratio = width / height;
  const presets: Array<[string, number]> = [
    ["16:9", 16 / 9],
    ["4:3", 4 / 3],
    ["1:1", 1],
    ["9:16", 9 / 16],
    ["21:9", 21 / 9],
  ];
  let best = presets[0][0];
  let bestDiff = Number.POSITIVE_INFINITY;
  for (const [label, value] of presets) {
    const diff = Math.abs(ratio - value);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = label;
    }
  }
  return best;
}
