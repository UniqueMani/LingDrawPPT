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

export interface PageDetailItem {
  page: number;
  title: string;
  text: string;
  preview_url?: string;
  thumbnail_url?: string;
  preview_updated_at?: number;
  text_blocks?: TextBlock[];
  page_width?: number | null;
  page_height?: number | null;
}

export interface ExtractTextResponse {
  filename: string;
  text: string;
  title: string;
  pages: number;
  pages_detail: PageDetailItem[];
  file_id: number;
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

export interface FileRecord {
  id: number;
  user_id: number;
  original_filename: string;
  mime_type: string;
  file_size: number;
  pages: number;
  parse_status: string;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface FileDetail extends FileRecord {
  extracted_text: string;
  pages_detail: PageDetailItem[];
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
  pageWidth?: number;
  pageHeight?: number;
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
  fluxImage?: FluxGenerateImageResponse;
  fluxAspectRatio?: string;
  statusFluxImage: "idle" | "loading" | "success" | "error";
  errorFluxImage?: string;
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

export interface FluxGenerateImagePayload {
  selected_text: string;
  topic?: string;
  prompt?: string;
  generation_mode?: "standard" | "fast";
  slide_page?: number;
  slide_type?: SlideType;
  use_doc_style?: boolean;
  use_entity_sync?: boolean;
  doc_consistency?: AnalyzeDocumentResponse | null;
  preview_path?: string | null;
  aspect_ratio?: string;
  model?: string;
  prompt_extend?: boolean;
  extra_style_words?: string | null;
}

export interface FluxImageJob {
  status: "loading" | "success" | "error";
  startedAt: number;
  requestKey: string;
}

export interface ImageQualityDimensionScore {
  key: string;
  label: string;
  score: number;
  maxScore?: number;
  deducted?: number;
  weight: number;
  detail: string;
  deductionReason?: string;
}

export interface ImageQualityEvaluation {
  passed: boolean;
  totalScore: number;
  passThreshold: number;
  dimensions: ImageQualityDimensionScore[];
  feedback: string;
}

export interface ImageJudgeFix {
  issueArea: string;
  severity: string;
  problem: string;
  constraint: string;
  preserve: string[];
  priority: number;
}

export interface ImageJudgeFeedback {
  feedbackConfidence: number;
  cannotModify: string[];
  fixes: ImageJudgeFix[];
  lowScoreDimensions: Record<string, number>;
  discarded: boolean;
  source: string;
}

export interface ImageGenAttemptLog {
  attempt: number;
  promptUsed: string;
  resultImageUrl: string;
  evaluation: ImageQualityEvaluation;
  judgeFeedback?: ImageJudgeFeedback | null;
}

export interface DocumentStyleProfile {
  domain: string;
  style_tokens: string[];
  style_prompt_zh: string;
  color_palette: string[];
  negative_style: string;
  color_theme?: string[];
  visual_density?: string;
  illustration_style?: string;
  illustration_level?: string;
  shape_language?: string;
  icon_style?: string;
  layout_style?: string;
  render_style?: string;
}

export interface SharedEntity {
  id: string;
  name: string;
  visual_anchor: string;
  color_hint: string;
  pages: number[];
  frequency: number;
  entity_type?: string;
  importance?: number;
  relations?: string[];
}

export interface SlideVisualPlan {
  page: number;
  topic: string;
  slide_role: string;
  visual_focus: string;
  entity_ids: string[];
  topic_type?: string;
  content_intent?: string;
  visual_type?: string;
  page_role?: string;
  visual_primitives?: string[];
  focus?: string;
  layout?: string;
  related_pages?: number[];
  global_constraints?: string;
  page_constraints?: string;
  primitive_keys?: string[];
}

export interface AnalyzeDocumentResponse {
  style: DocumentStyleProfile;
  entities: SharedEntity[];
  slide_plans: SlideVisualPlan[];
  summary: string;
  source: string;
}

export interface FluxGenerateImageResponse {
  taskId: string;
  resultImageUrl: string;
  originImageUrl?: string | null;
  promptUsed: string;
  mode: string;
  attempts?: number;
  regenerated?: boolean;
  selectedAttempt?: number;
  evaluation?: ImageQualityEvaluation | null;
  attemptsLog?: ImageGenAttemptLog[];
}

export interface NormalizedRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface InsertSession {
  fileId: number;
  page: number;
  imageUrl: string;
  aspectRatio: string;
  previewUrl: string;
  thumbnailUrl?: string;
  textBlocks: TextBlock[];
  docName: string;
  source?: "flux" | "chart";
}

export interface StageImageResponse {
  image_url: string;
}

export interface RecommendPlacementResponse {
  recommended: NormalizedRect;
  occupied_blocks: TextBlock[];
  preview_url: string;
  page_width?: number | null;
  page_height?: number | null;
}

export interface InsertImageResponse {
  ok: boolean;
  page: number;
  preview_url: string;
  download_url: string;
  message: string;
  picture?: PptPagePicture | null;
}

export interface RemoveLastImageResponse {
  ok: boolean;
  page: number;
  removed: boolean;
  preview_url: string;
  message: string;
}

export interface PptPagePicture {
  shape_index: number;
  x: number;
  y: number;
  width: number;
  height: number;
  aspect_ratio: string;
}

export interface ListPageImagesResponse {
  pictures: PptPagePicture[];
  page_width?: number | null;
  page_height?: number | null;
}

export interface UpdateImagePlacementResponse {
  ok: boolean;
  page: number;
  preview_url: string;
  message: string;
}

export interface RemoveImageResponse {
  ok: boolean;
  page: number;
  removed: boolean;
  preview_url: string;
  message: string;
}

