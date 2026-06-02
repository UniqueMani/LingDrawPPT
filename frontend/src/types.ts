export type SlideType = "cover" | "section-divider" | "content" | "unknown";
export type Mode = "auto" | "mock" | "deepseek";

export interface SlideRequest {
  topic: string;
  body?: string | null;
  data_description?: string | null;
  slide_type: SlideType;
  mode: Mode;
}

export type EChartsOption = Record<string, any>;

export interface ChartResponse {
  intent: string;
  chartType: string;
  echartsOption: EChartsOption;
  reason: string;
  extracted?: Record<string, any>;
}

export interface AnalyzeResponse {
  semantic: Record<string, any>;
  chart: ChartResponse;
}

export interface IllustrationResponse {
  needIllus: boolean;
  keywords: string[];
  prompt: string;
  reason: string;
}

export interface IllustrationStrategyResponse {
  illustration: IllustrationResponse;
}

export interface TextBlock {
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface OCRRegionRequest {
  preview_url: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface OCRRegionResponse {
  text: string;
  source: "ocr";
}

export interface ExtractTextResponse {
  file_id: number;
  filename: string;
  text: string;
  title: string;
  pages: number;
  pages_detail: Array<{ page: number; title: string; text: string; preview_url?: string; thumbnail_url?: string; text_blocks?: TextBlock[] }>;
}

export interface FileRecordDTO {
  id: number;
  original_filename: string;
  file_size: number;
  pages: number;
  parse_status: string;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface FileDetailDTO extends FileRecordDTO {
  pages_detail: ExtractTextResponse["pages_detail"];
  extracted_text: string;
}

export interface UserDTO {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  full_name: string;
  email: string;
  organization: string;
  created_at: string;
}

export interface AdminUserDTO extends UserDTO {
  disabled_at?: string | null;
}

export interface UploadedFileDTO {
  id: number;
  user_id: number;
  username: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  pages: number;
  parse_status: string;
  error_message: string;
  created_at: string;
  deleted_at?: string | null;
}

export interface UsageLogDTO {
  id: number;
  user_id: number;
  username: string;
  event_type: string;
  created_at: string;
}

export interface AdminAuditLogDTO {
  id: number;
  admin_user_id: number;
  admin_username: string;
  action_type: string;
  target_type: string;
  target_id: string;
  detail: string;
  created_at: string;
}

export interface AdminOverviewDTO {
  total_users: number;
  active_users: number;
  total_files: number;
  failed_files: number;
  recent_events: number;
  event_counts: Record<string, number>;
  recent_failed_files: UploadedFileDTO[];
  recent_audit_logs: AdminAuditLogDTO[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuthResponse {
  token: string;
  user: UserDTO;
}

export interface UpdateMeResponse {
  token?: string | null;
  user: UserDTO;
}

export interface SlideSnapshot {
  timestamp: number;
  input: SlideRequest;
  analyze?: AnalyzeResponse;
  illustration?: IllustrationStrategyResponse;
}

export interface SlideState {
  id: string;
  page: number;
  previewUrl?: string;
  thumbnailUrl?: string;
  sourceTitle: string;
  sourceText: string;
  textBlocks: TextBlock[];
  sourceDataDescription?: string;
  input: SlideRequest;
  analyze?: AnalyzeResponse;
  illustration?: IllustrationStrategyResponse;
  intentSemantic?: Record<string, any>;
  chartCode?: VizLabChartCodeResponse;
  vizIllustration?: VizLabIllustrationResponse;
  statusAnalyze: "idle" | "loading" | "success" | "error";
  statusIllustration: "idle" | "loading" | "success" | "error";
  errorAnalyze?: string;
  errorIllustration?: string;
  history: SlideSnapshot[];
}

export interface VizLabIntentResponse {
  semantic: Record<string, any>;
}

export interface ChartCodeValidationIssue {
  target: string;
  severity: string;
  message: string;
}

export interface VizLabChartCodeResponse {
  echartsOption?: Record<string, any> | null;
  chartJsConfig?: Record<string, any> | null;
  mermaidSource?: string | null;
  validationIssues: ChartCodeValidationIssue[];
  generatedTargets: string[];
  source: string;
  llmAttempted: boolean;
  llmSucceeded: boolean;
  fallbackReason: string;
  rawLlmExcerpt?: string | null;
}

export interface VizLabIllustrationResponse {
  needIllus: boolean;
  keywords: string[];
  prompt: string;
  reason: string;
  experiment: Record<string, any>;
}

