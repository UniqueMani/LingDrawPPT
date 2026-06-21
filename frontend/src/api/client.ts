import type {
  AnalyzeResponse,
  AdminAuditLogDTO,
  AdminOverviewDTO,
  AdminUserDTO,
  AuthResponse,
  ExtractTextResponse,
  FileDetail,
  FileRecord,
  IllustrationStrategyResponse,
  OCRRegionRequest,
  OCRRegionResponse,
  PaginatedResponse,
  SlideRequest,
  UpdateMeResponse,
  UploadedFileDTO,
  UsageLogDTO,
  UserDTO,
  VizLabChartCodeResponse,
  VizLabIllustrationResponse,
  VizLabIntentResponse,
  AnalyzeDocumentResponse,
  FluxGenerateImagePayload,
  FluxGenerateImageResponse,
  InsertImageResponse,
  ListPageImagesResponse,
  NormalizedRect,
  RecommendPlacementResponse,
  RemoveImageResponse,
  RemoveLastImageResponse,
  StageImageResponse,
  UpdateImagePlacementResponse,
} from "../types";

let authToken = "";

export function setAuthToken(token: string) {
  authToken = token || "";
}

function normalizeBaseUrl(baseUrl: string) {
  const s = baseUrl.trim();
  if (!s) return "";
  return s.endsWith("/") ? s.slice(0, -1) : s;
}

function wrapFetchError(error: unknown, url: string): Error {
  if (error instanceof TypeError) {
    return new Error(
      `无法连接后端。请确认 uvicorn 已在仓库根目录运行，且地址为 ${url.split("/api")[0] || url}`
    );
  }
  return error instanceof Error ? error : new Error(String(error));
}

async function postJSON<T>(url: string, payload: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`HTTP ${res.status}: ${t}`);
    }
    return (await res.json()) as T;
  } catch (error) {
    throw wrapFetchError(error, url);
  }
}

async function getJSON<T>(url: string): Promise<T> {
  try {
    const res = await fetch(url, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`HTTP ${res.status}: ${t}`);
    }
    return (await res.json()) as T;
  } catch (error) {
    throw wrapFetchError(error, url);
  }
}

export async function analyze(baseUrl: string, req: SlideRequest) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<AnalyzeResponse>(`${b}/api/analyze`, req);
}

export async function illustration(baseUrl: string, req: SlideRequest) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<IllustrationStrategyResponse>(
    `${b}/api/illustration`,
    req
  );
}

export async function vizLabIntent(baseUrl: string, req: SlideRequest) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<VizLabIntentResponse>(`${b}/api/viz-lab/intent`, req);
}

export async function vizLabChartCode(
  baseUrl: string,
  payload: { slide: SlideRequest; targets: string[]; instructions?: string | null }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<VizLabChartCodeResponse>(`${b}/api/viz-lab/chart-code`, payload);
}

export async function vizLabIllustration(
  baseUrl: string,
  payload: {
    slide: SlideRequest;
    image_model: string;
    style_ref_url?: string | null;
    lora_hint?: string | null;
    extra_style_words?: string | null;
  }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<VizLabIllustrationResponse>(`${b}/api/viz-lab/illustration`, payload);
}

export async function analyzeDocumentConsistency(
  baseUrl: string,
  payload: { doc_title?: string; pages: Array<{ page: number; topic: string; body?: string }> }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<AnalyzeDocumentResponse>(`${b}/api/document/analyze-consistency`, payload);
}

export async function fluxGenerateImage(
  baseUrl: string,
  payload: FluxGenerateImagePayload
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const body: Record<string, unknown> = { ...payload };
  if (payload.doc_consistency) {
    body.doc_consistency = {
      style: payload.doc_consistency.style,
      entities: payload.doc_consistency.entities,
      slide_plans: payload.doc_consistency.slide_plans,
    };
  }
  return await postJSON<FluxGenerateImageResponse>(`${b}/api/flux/generate-image`, body);
}

export async function extractText(baseUrl: string, file: File) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const form = new FormData();
  form.append("file", file);
  const url = `${b}/api/extract-text`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
      body: form,
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`HTTP ${res.status}: ${t}`);
    }
    return (await res.json()) as ExtractTextResponse;
  } catch (error) {
    throw wrapFetchError(error, url);
  }
}

export async function listFiles(baseUrl: string) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await getJSON<FileRecord[]>(`${b}/api/files`);
}

export async function getFileDetail(baseUrl: string, fileId: number) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await getJSON<FileDetail>(`${b}/api/files/${fileId}`);
}

export async function deleteFile(baseUrl: string, fileId: number) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const res = await fetch(`${b}/api/files/${fileId}`, {
    method: "DELETE",
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  return (await res.json()) as { ok: boolean; deleted_id: number };
}

export async function downloadFile(baseUrl: string, fileId: number, filename: string) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const res = await fetch(`${b}/api/files/${fileId}/download`, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function exportDocumentFile(
  baseUrl: string,
  fileId: number,
  filename: string,
  format: "pptx" | "pdf"
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const params = new URLSearchParams({ format });
  const res = await fetch(`${b}/api/files/${fileId}/export?${params.toString()}`, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function ocrRegion(baseUrl: string, payload: OCRRegionRequest) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<OCRRegionResponse>(`${b}/api/ocr-region`, payload);
}

export async function register(
  baseUrl: string,
  payload: {
    username: string;
    password: string;
    full_name: string;
    email: string;
    organization: string;
  }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<AuthResponse>(`${b}/api/register`, payload);
}

export async function login(baseUrl: string, username: string, password: string) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<AuthResponse>(`${b}/api/login`, { username, password });
}

export async function me(baseUrl: string) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const res = await fetch(`${b}/api/me`, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  return (await res.json()) as UserDTO;
}

export async function updateMe(
  baseUrl: string,
  payload: {
    username?: string;
    full_name?: string;
    email?: string;
    organization?: string;
    old_password?: string;
    new_password?: string;
  }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  const res = await fetch(`${b}/api/me`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  return (await res.json()) as UpdateMeResponse;
}

export async function adminUsers(baseUrl: string) {
  return await adminListUsers(baseUrl);
}

function adminQuery(params: Record<string, string | number | boolean | undefined | null>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return query.toString();
}

async function adminFetch<T>(baseUrl: string, path: string, init?: RequestInit) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string> | undefined) };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  const url = `${b}${path}`;
  try {
    const res = await fetch(url, {
      ...init,
      headers,
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`HTTP ${res.status}: ${t}`);
    }
    return (await res.json()) as T;
  } catch (error) {
    throw wrapFetchError(error, url);
  }
}

export async function adminOverview(baseUrl: string) {
  return await adminFetch<AdminOverviewDTO>(baseUrl, "/api/admin/overview");
}

export async function adminListUsers(baseUrl: string, params: Record<string, string | number | boolean | undefined> = {}) {
  return await adminFetch<PaginatedResponse<AdminUserDTO>>(baseUrl, `/api/admin/users?${adminQuery(params)}`);
}

export async function adminUpdateUser(baseUrl: string, userId: number, payload: { full_name?: string; email?: string; organization?: string }) {
  return await adminFetch<AdminUserDTO>(baseUrl, `/api/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function adminSetUserStatus(baseUrl: string, userId: number, isActive: boolean) {
  return await adminFetch<AdminUserDTO>(baseUrl, `/api/admin/users/${userId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_active: isActive }),
  });
}

export async function adminResetPassword(baseUrl: string, userId: number, password: string) {
  return await adminFetch<{ ok: boolean }>(baseUrl, `/api/admin/users/${userId}/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
}

export async function adminListFiles(baseUrl: string, params: Record<string, string | number | boolean | undefined> = {}) {
  return await adminFetch<PaginatedResponse<UploadedFileDTO>>(baseUrl, `/api/admin/files?${adminQuery(params)}`);
}

export function adminFileDownloadUrl(baseUrl: string, fileId: number) {
  return `${normalizeBaseUrl(baseUrl)}/api/admin/files/${fileId}/download`;
}

export async function adminDownloadFile(baseUrl: string, fileId: number, filename: string) {
  const b = normalizeBaseUrl(baseUrl);
  const res = await fetch(`${b}/api/admin/files/${fileId}/download`, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function adminDeleteFile(baseUrl: string, fileId: number) {
  return await adminFetch<{ ok: boolean }>(baseUrl, `/api/admin/files/${fileId}`, { method: "DELETE" });
}

export async function adminListLogs(baseUrl: string, params: Record<string, string | number | undefined> = {}) {
  return await adminFetch<PaginatedResponse<UsageLogDTO>>(baseUrl, `/api/admin/logs?${adminQuery(params)}`);
}

export async function adminExportLogs(baseUrl: string, params: Record<string, string | number | undefined> = {}) {
  const b = normalizeBaseUrl(baseUrl);
  const res = await fetch(`${b}/api/admin/logs/export?${adminQuery(params)}`, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "usage-logs.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export async function adminClearLogs(baseUrl: string, before: string) {
  return await adminFetch<{ ok: boolean; deleted: number }>(baseUrl, `/api/admin/logs?${adminQuery({ before })}`, { method: "DELETE" });
}

export async function adminListAuditLogs(baseUrl: string, params: Record<string, string | number | undefined> = {}) {
  return await adminFetch<PaginatedResponse<AdminAuditLogDTO>>(baseUrl, `/api/admin/audit-logs?${adminQuery(params)}`);
}

export async function getStats(baseUrl: string, days = 30) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const res = await fetch(`${b}/api/stats?days=${days}`, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  return (await res.json()) as { events: Record<string, number>; detail: { name: string; label: string; count: number }[] };
}

export async function postStatsEvent(baseUrl: string, eventType: string) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<{ ok: boolean }>(`${b}/api/stats/event`, { event_type: eventType });
}

export async function recommendPptPlacement(
  baseUrl: string,
  payload: { file_id: number; page: number; image_url: string; aspect_ratio?: string }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<RecommendPlacementResponse>(`${b}/api/ppt/recommend-placement`, payload);
}

export async function insertPptImage(
  baseUrl: string,
  payload: { file_id: number; page: number; image_url: string; placement: NormalizedRect }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<InsertImageResponse>(`${b}/api/ppt/insert-image`, payload);
}

export async function removeLastPptImage(
  baseUrl: string,
  payload: { file_id: number; page: number }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<RemoveLastImageResponse>(`${b}/api/ppt/remove-last-image`, payload);
}

export async function listPageImages(baseUrl: string, payload: { file_id: number; page: number }) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<ListPageImagesResponse>(`${b}/api/ppt/list-page-images`, payload);
}

export async function updatePptImagePlacement(
  baseUrl: string,
  payload: { file_id: number; page: number; shape_index: number; placement: NormalizedRect }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<UpdateImagePlacementResponse>(`${b}/api/ppt/update-image-placement`, payload);
}

export async function removePptImage(
  baseUrl: string,
  payload: { file_id: number; page: number; shape_index: number }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<RemoveImageResponse>(`${b}/api/ppt/remove-image`, payload);
}

export async function fetchPptShapeImageBlobUrl(
  baseUrl: string,
  payload: { file_id: number; page: number; shape_index: number }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const params = new URLSearchParams({
    file_id: String(payload.file_id),
    page: String(payload.page),
    shape_index: String(payload.shape_index),
  });
  const res = await fetch(`${b}/api/ppt/shape-image?${params.toString()}`, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return URL.createObjectURL(await res.blob());
}

export async function stagePptImage(
  baseUrl: string,
  payload: { file_id: number; image_data: string }
) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  return await postJSON<StageImageResponse>(`${b}/api/ppt/stage-image`, payload);
}

export async function fetchAuthedAssetBlobUrl(baseUrl: string, path: string) {
  const b = normalizeBaseUrl(baseUrl);
  const url = path.startsWith("http") ? path : `${b}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return URL.createObjectURL(await res.blob());
}

