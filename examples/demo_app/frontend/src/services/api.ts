/** API service layer for the demo application. */

const API_BASE = 'http://127.0.0.1:8001/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API Error ${response.status}: ${error}`);
  }
  return response.json();
}

export const api = {
  login: (username: string, password: string) =>
    request<{ success: boolean; token?: string; role?: string }>(
      `/login?username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
      { method: 'POST' }
    ),

  getDashboardStats: () =>
    request<{ park_count: number; device_count: number; order_count: number; online_users: number; alert_count: number }>('/dashboard/stats'),

  getUsers: (params?: { page?: number; keyword?: string; status?: string }) => {
    const qs = new URLSearchParams();
    if (params?.page) qs.set('page', String(params.page));
    if (params?.keyword) qs.set('keyword', params.keyword);
    if (params?.status) qs.set('status', params.status);
    return request<{ total: number; items: any[] }>(`/users?${qs.toString()}`);
  },

  getUser: (id: number) => request<any>(`/users/${id}`),

  createUser: (data: Record<string, string>) => {
    const qs = new URLSearchParams(data).toString();
    return request<{ success: boolean; user: any }>(`/users?${qs}`, { method: 'POST' });
  },

  updateUser: (id: number, data: Record<string, string>) => {
    const qs = new URLSearchParams(data).toString();
    return request<{ success: boolean }>(`/users/${id}?${qs}`, { method: 'PUT' });
  },

  deleteUser: (id: number) =>
    request<{ success: boolean }>(`/users/${id}`, { method: 'DELETE' }),

  getDevices: (params?: { page?: number; device_type?: string; status?: string; location?: string }) => {
    const qs = new URLSearchParams();
    if (params?.page) qs.set('page', String(params.page));
    if (params?.device_type) qs.set('device_type', params.device_type);
    if (params?.status) qs.set('status', params.status);
    if (params?.location) qs.set('location', params.location);
    return request<{ total: number; items: any[] }>(`/devices?${qs.toString()}`);
  },

  getReports: (page?: number) => {
    const qs = page ? `?page=${page}` : '';
    return request<{ total: number; items: any[] }>(`/reports${qs}`);
  },

  getAlerts: (params?: { page?: number; level?: string }) => {
    const qs = new URLSearchParams();
    if (params?.page) qs.set('page', String(params.page));
    if (params?.level) qs.set('level', params.level);
    return request<{ total: number; items: any[] }>(`/alerts?${qs.toString()}`);
  },

  getSettings: () => request<any>('/settings'),

  updateSettings: (data: Record<string, any>) => {
    const qs = new URLSearchParams(
      Object.fromEntries(
        Object.entries(data).map(([k, v]) => [k, String(v)])
      )
    ).toString();
    return request<{ success: boolean; updated_fields: string[] }>(`/settings?${qs}`, { method: 'PUT' });
  },
};
