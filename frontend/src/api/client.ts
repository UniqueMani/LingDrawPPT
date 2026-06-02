import type {
  AnalyzeResponse,
  AuthResponse,
  ExtractTextResponse,
  FileDetail,
  FileRecord,
  IllustrationStrategyResponse,
  SlideRequest,
  UpdateMeResponse,
  UserDTO,
  VizLabChartCodeResponse,
  VizLabIllustrationResponse,
  VizLabIntentResponse,
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

async function postJSON<T>(url: string, payload: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
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

export async function extractText(baseUrl: string, file: File) {
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${b}/api/extract-text`, {
    method: "POST",
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
    body: form,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  return (await res.json()) as ExtractTextResponse;
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
  const b = normalizeBaseUrl(baseUrl);
  if (!b) throw new Error("baseUrl 为空");
  const res = await fetch(`${b}/api/admin/users`, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  return (await res.json()) as UserDTO[];
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

// ---- 文件归档 API ----

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  return (await res.json()) as T;
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

