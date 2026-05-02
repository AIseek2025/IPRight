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

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

function unwrap<T>(res: { data: ApiResponse<T> }): T {
  return res.data.data;
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

export async function getTaskArtifacts(taskId: string) {
  const res = await client.get<ApiResponse<{ items: ArtifactItem[] }>>(`/tasks/${taskId}/artifacts`);
  return unwrap(res);
}

export async function getTaskExports(taskId: string) {
  const res = await client.get<ApiResponse<{ items: ExportItem[] }>>(`/tasks/${taskId}/exports`);
  return unwrap(res);
}

export async function getTaskScreenshots(taskId: string) {
  const res = await client.get<ApiResponse<{ items: ScreenshotItem[] }>>(`/tasks/${taskId}/screenshots`);
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
