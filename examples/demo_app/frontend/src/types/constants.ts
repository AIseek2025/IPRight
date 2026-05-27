/** Additional utility types and constants for the demo application. */

export const APP_VERSION = 'V1.0';
export const APP_NAME = '智慧园区管理平台';

export const DATE_FORMAT = 'YYYY-MM-DD';
export const DATETIME_FORMAT = 'YYYY-MM-DD HH:mm:ss';
export const TIME_FORMAT = 'HH:mm:ss';

export const DEFAULT_PAGE_SIZE = 20;
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export const DEVICE_TYPES = [
  { value: '监控设备', label: '监控设备', icon: '📹' },
  { value: '通行设备', label: '通行设备', icon: '🚪' },
  { value: '暖通设备', label: '暖通设备', icon: '🌡️' },
  { value: '消防设备', label: '消防设备', icon: '🧯' },
  { value: '电力设备', label: '电力设备', icon: '⚡' },
  { value: '给排水设备', label: '给排水设备', icon: '💧' },
  { value: '安防设备', label: '安防设备', icon: '🔒' },
];

export const ALERT_LEVELS = [
  { value: '严重', label: '严重', color: '#ff4d4f' },
  { value: '警告', label: '警告', color: '#faad14' },
  { value: '提示', label: '提示', color: '#1890ff' },
];

export const USER_ROLES = [
  { value: '管理员', label: '管理员', description: '拥有全部系统权限' },
  { value: '运维人员', label: '运维人员', description: '设备和告警管理' },
  { value: '保安队长', label: '保安队长', description: '告警和日志查看' },
  { value: '财务', label: '财务', description: '报表查看和生成' },
  { value: '巡检员', label: '巡检员', description: '设备查看和巡检' },
  { value: '操作员', label: '操作员', description: '基础数据查看' },
];

export const DEVICE_STATUS_MAP: Record<string, string> = {
  '在线': 'success',
  '离线': 'error',
  '维护中': 'warning',
};

export const REPORT_TYPES = [
  { value: '库存', label: '库存报表' },
  { value: '巡检', label: '巡检报表' },
  { value: '工单', label: '工单报表' },
  { value: '能耗', label: '能耗报表' },
  { value: '安全', label: '安全报表' },
  { value: '维修', label: '维修报表' },
  { value: '财务', label: '财务报表' },
  { value: '人力', label: '人力报表' },
];

export const NAVIGATION_ITEMS = [
  { key: 'dashboard', path: '/dashboard', label: '首页', icon: '📊' },
  { key: 'users', path: '/users', label: '用户管理', icon: '👥' },
  { key: 'devices', path: '/devices', label: '设备管理', icon: '🔧' },
  { key: 'reports', path: '/reports', label: '报表统计', icon: '📋' },
  { key: 'alerts', path: '/alerts', label: '设备告警', icon: '🚨' },
  { key: 'settings', path: '/settings', label: '系统设置', icon: '⚙️' },
];

export const ERROR_MESSAGES: Record<string, string> = {
  NETWORK_ERROR: '网络连接失败，请检查网络设置',
  UNAUTHORIZED: '登录已过期，请重新登录',
  FORBIDDEN: '没有操作权限',
  NOT_FOUND: '请求的资源不存在',
  SERVER_ERROR: '服务器内部错误，请稍后重试',
  VALIDATION_ERROR: '输入数据验证失败，请检查后重试',
  TIMEOUT: '请求超时，请稍后重试',
};

export const SUCCESS_MESSAGES: Record<string, string> = {
  CREATE: '创建成功',
  UPDATE: '更新成功',
  DELETE: '删除成功',
  SAVE: '保存成功',
  SUBMIT: '提交成功',
  LOGIN: '登录成功',
  LOGOUT: '已安全退出',
  EXPORT: '导出成功',
  IMPORT: '导入成功',
};

export function getErrorMessage(code: string): string {
  return ERROR_MESSAGES[code] || '未知错误';
}

export function getSuccessMessage(action: string): string {
  return SUCCESS_MESSAGES[action] || '操作成功';
}

export const SESSION_KEYS = {
  AUTH_TOKEN: 'auth_token',
  USER_INFO: 'user_info',
  SETTINGS: 'app_settings',
  LAST_PAGE: 'last_page',
} as const;
