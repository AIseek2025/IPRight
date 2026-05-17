import axios from 'axios';
import type {
  ApiResponse,
  TaskListData,
  TaskDetail,
  TaskDashboard,
  EventItem,
  ExportItem,
  ArtifactItem,
  ScreenshotItem,
} from '@/types';

const TOKEN_STORAGE_KEY = 'ipright_api_token';

declare global {
  interface ImportMetaEnv {
    readonly VITE_IPRIGHT_API_TOKEN?: string;
  }
  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }
  interface Window {
    __IPRIGHT_API_TOKEN__?: string;
  }
}

export function getApiToken(): string {
  if (typeof window !== 'undefined') {
    if (window.__IPRIGHT_API_TOKEN__) return window.__IPRIGHT_API_TOKEN__;
    try {
      const fromStorage = window.localStorage?.getItem(TOKEN_STORAGE_KEY);
      if (fromStorage) return fromStorage;
    } catch {
      // ignore (private browsing / SSR contexts where storage is restricted)
    }
  }
  const fromEnv = import.meta?.env?.VITE_IPRIGHT_API_TOKEN;
  return typeof fromEnv === 'string' ? fromEnv : '';
}

export function setApiToken(token: string): void {
  if (typeof window === 'undefined') return;
  try {
    if (token) {
      window.localStorage?.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage?.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // ignore storage errors; in-memory window override below still works
  }
  if (token) {
    window.__IPRIGHT_API_TOKEN__ = token;
  } else {
    delete window.__IPRIGHT_API_TOKEN__;
  }
}

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

client.interceptors.request.use((config) => {
  const token = getApiToken();
  if (token) {
    config.headers = config.headers ?? {};
    if (!('Authorization' in (config.headers as Record<string, unknown>))) {
      (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

function unwrap<T>(res: { data: ApiResponse<T> }): T {
  return res.data.data;
}

function withTokenQuery(url: string): string {
  const token = getApiToken();
  if (!token) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}token=${encodeURIComponent(token)}`;
}

export async function createTask(params: {
  keyword: string;
  product_name?: string;
  version?: string;
  industry?: string;
  notes?: string;
}) {
  const res = await client.post<ApiResponse<{ task_id: string; status: string }>>('/tasks', params);
  return unwrap(res);
}

export async function listTasks(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  keyword?: string;
}) {
  const res = await client.get<ApiResponse<TaskListData>>('/tasks', { params });
  return unwrap(res);
}

export async function getTask(taskId: string) {
  const res = await client.get<ApiResponse<TaskDetail>>(`/tasks/${taskId}`);
  return unwrap(res);
}

export async function getTaskDashboard(taskId: string) {
  const res = await client.get<ApiResponse<TaskDashboard>>(`/tasks/${taskId}/dashboard`);
  return unwrap(res);
}

export async function getTaskTimeline(taskId: string) {
  const res = await client.get<ApiResponse<{ items: EventItem[] }>>(`/tasks/${taskId}/timeline`);
  return unwrap(res);
}

export async function getTaskArtifacts(taskId: string, params?: { limit?: number }) {
  const res = await client.get<ApiResponse<{ items: ArtifactItem[] }>>(`/tasks/${taskId}/artifacts`, {
    params,
  });
  return unwrap(res);
}

export async function getTaskExports(taskId: string) {
  const res = await client.get<ApiResponse<{ items: ExportItem[] }>>(`/tasks/${taskId}/exports`);
  return unwrap(res);
}

export async function getTaskScreenshots(taskId: string, params?: { limit?: number }) {
  const res = await client.get<ApiResponse<{ items: ScreenshotItem[] }>>(`/tasks/${taskId}/screenshots`, {
    params,
  });
  return unwrap(res);
}

export async function retryTask(taskId: string, fromStage?: string) {
  const res = await client.post<ApiResponse<{ task_id: string }>>(`/tasks/${taskId}/retry`, {
    from_stage: fromStage,
  });
  return unwrap(res);
}

export async function cancelTask(taskId: string) {
  const res = await client.post<ApiResponse<{ task_id: string }>>(`/tasks/${taskId}/cancel`);
  return unwrap(res);
}

export function getExportDownload(exportId: string): string {
  return `/api/v1/exports/${exportId}/download`;
}

export function getTaskBundleDownload(taskId: string): string {
  return `/api/v1/tasks/${taskId}/bundle/download`;
}

/**
 * URL for SSE consumers (browser ``EventSource`` cannot set custom headers,
 * so the API token is added as a ``?token=`` query string instead).
 */
export function getTaskStreamUrl(taskId: string): string {
  return withTokenQuery(`/api/v1/tasks/${taskId}/stream`);
}
