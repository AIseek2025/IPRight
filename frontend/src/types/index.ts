export interface TaskItem {
  id: string;
  keyword: string;
  product_name: string;
  version: string;
  status: string;
  current_stage: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskDetail {
  id: string;
  keyword: string;
  product_name: string;
  version: string;
  industry: string | null;
  notes: string | null;
  status: string;
  current_stage: string | null;
  active_build_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface EventItem {
  id: string;
  event_type: string;
  title: string;
  detail: string | null;
  created_at: string;
}

export interface ExportItem {
  id: string;
  export_type: string;
  file_name: string;
  status: string;
  download_url: string | null;
  build_id?: string | null;
  build_no?: number | null;
  build_finished_at?: string | null;
  is_latest?: boolean;
  created_at: string;
}

export interface ArtifactItem {
  id: string;
  artifact_type: string;
  artifact_name: string;
  mime_type: string | null;
  created_at: string;
}

export interface ScreenshotItem {
  id: string;
  scenario_id: string;
  page_title: string;
  route: string;
  caption: string | null;
  created_at: string;
}

export interface TaskDashboard {
  task: TaskDetail;
  timeline: EventItem[];
  exports: ExportItem[];
  prd_summary: string | null;
  screenshot_previews: string[];
}

export interface ApiResponse<T = unknown> {
  code: string;
  message: string;
  data: T;
}

export interface TaskListData {
  items: TaskItem[];
  total: number;
  page: number;
  page_size: number;
}

export const STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  planning: 'PRD 规划中',
  coding: '代码生成中',
  building: '构建中',
  running: '运行验证中',
  capturing: '页面截图中',
  writing_manual: '说明书生成中',
  writing_code_book: '源码文档生成中',
  publishing: '发布中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  needs_review: '待审核',
};

export const STATUS_COLORS: Record<string, string> = {
  queued: 'default',
  planning: 'processing',
  coding: 'processing',
  building: 'processing',
  running: 'processing',
  capturing: 'processing',
  writing_manual: 'cyan',
  writing_code_book: 'cyan',
  publishing: 'cyan',
  completed: 'success',
  failed: 'error',
  cancelled: 'default',
  needs_review: 'warning',
};
