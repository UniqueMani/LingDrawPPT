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

export interface ExtractTextResponse {
  filename: string;
  text: string;
  title: string;
  pages: number;
  pages_detail: Array<{ page: number; title: string; text: string }>;
}

export interface UserDTO {
  id: number;
  username: string;
  is_admin: boolean;
  full_name: string;
  email: string;
  organization: string;
  created_at: string;
}

export interface AuthResponse {
  token: string;
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
  input: SlideRequest;
  analyze?: AnalyzeResponse;
  illustration?: IllustrationStrategyResponse;
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
  source: string;
  rawLlmExcerpt?: string | null;
}

export interface VizLabIllustrationResponse {
  needIllus: boolean;
  keywords: string[];
  prompt: string;
  reason: string;
  experiment: Record<string, any>;
}

