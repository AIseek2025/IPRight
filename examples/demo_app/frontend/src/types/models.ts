/** TypeScript type definitions for the demo application. */

export interface UserData {
  id: number;
  name: string;
  role: string;
  email: string;
  phone: string;
  department: string;
  status: string;
  created_at: string;
}

export interface DeviceData {
  id: string;
  name: string;
  type: string;
  location: string;
  status: string;
  ip: string;
  last_check: string;
}

export interface AlertData {
  id: string;
  device: string;
  type: string;
  level: string;
  time: string;
  status: string;
  description?: string;
  handler?: string;
}

export interface ReportData {
  id: string;
  name: string;
  type: string;
  creator: string;
  date: string;
  status: string;
  file_format?: string;
  file_size?: number;
}

export interface AppSettingsData {
  system_name: string;
  version: string;
  alerts_enabled: boolean;
  backup_enabled: boolean;
  log_retention_days: number;
  session_timeout_minutes: number;
  max_login_attempts: number;
  password_min_length: number;
}

export interface DashboardStats {
  park_count: number;
  device_count: number;
  order_count: number;
  online_users: number;
  alert_count: number;
  report_count: number;
}

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface LoginResponse {
  success: boolean;
  token?: string;
  role?: string;
  message?: string;
}

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  message?: string;
  errors?: string[];
}

export type UserRole = '管理员' | '运维人员' | '操作员' | '保安队长' | '财务' | '巡检员';
export type DeviceType = '监控设备' | '通行设备' | '暖通设备' | '消防设备' | '电力设备' | '给排水设备' | '安防设备';
export type DeviceStatus = '在线' | '离线' | '维护中';
export type AlertLevel = '严重' | '警告' | '提示';
export type AlertStatus = '未处理' | '处理中' | '已处理';
export type ReportStatus = '处理中' | '已完成';
export type ReportType = '库存' | '巡检' | '工单' | '能耗' | '安全' | '维修' | '财务' | '人力';
export type UserStatus = '正常' | '停用';

export interface FilterParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  status?: string;
  type?: string;
  level?: string;
  location?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export interface SortConfig {
  field: string;
  order: 'asc' | 'desc';
}

export interface ColumnConfig<T> {
  key: string;
  title: string;
  dataIndex?: keyof T;
  width?: number;
  fixed?: 'left' | 'right';
  sortable?: boolean;
  filterable?: boolean;
  render?: (value: any, record: T, index: number) => React.ReactNode;
}

export interface MenuItem {
  key: string;
  path: string;
  label: string;
  icon?: string;
  children?: MenuItem[];
  permission?: string;
}

export interface BreadcrumbItem {
  title: string;
  path?: string;
}

export interface FormField {
  name: string;
  label: string;
  type: 'text' | 'number' | 'select' | 'date' | 'email' | 'phone' | 'textarea' | 'switch' | 'password';
  required?: boolean;
  placeholder?: string;
  options?: { value: string; label: string }[];
  rules?: ValidationRule[];
  defaultValue?: any;
}

export interface ValidationRule {
  type: 'required' | 'min' | 'max' | 'pattern' | 'custom';
  value?: any;
  message: string;
  validator?: (value: any) => boolean;
}

export interface ActionConfig {
  type: 'button' | 'link' | 'dropdown';
  label: string;
  icon?: string;
  danger?: boolean;
  confirm?: string;
  onClick: (record: any) => void;
  visible?: (record: any) => boolean;
}

export interface TableAction {
  key: string;
  label: string;
  icon?: React.ReactNode;
  danger?: boolean;
  onClick: (record: any) => void;
}
