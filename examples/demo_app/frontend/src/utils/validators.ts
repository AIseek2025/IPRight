/**
 * Comprehensive validation utilities for form inputs and data validation.
 * Provides reusable validation functions for the entire application.
 */

export const validators = {
  required: (value: any, message: string = '此字段为必填'): string | undefined => {
    if (value === null || value === undefined || (typeof value === 'string' && value.trim().length === 0)) {
      return message;
    }
    return undefined;
  },

  minLength: (min: number, message?: string) => (value: string): string | undefined => {
    if (!value || value.length < min) {
      return message || `最少需要 ${min} 个字符`;
    }
    return undefined;
  },

  maxLength: (max: number, message?: string) => (value: string): string | undefined => {
    if (value && value.length > max) {
      return message || `最多允许 ${max} 个字符`;
    }
    return undefined;
  },

  email: (value: string, message: string = '请输入有效的邮箱地址'): string | undefined => {
    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (value && !emailRegex.test(value)) {
      return message;
    }
    return undefined;
  },

  phone: (value: string, message: string = '请输入有效的手机号码'): string | undefined => {
    const phoneRegex = /^1[3-9]\d{9}$/;
    if (value && !phoneRegex.test(value)) {
      return message;
    }
    return undefined;
  },

  number: (value: any, message: string = '请输入有效的数字'): string | undefined => {
    if (value !== null && value !== undefined && value !== '' && isNaN(Number(value))) {
      return message;
    }
    return undefined;
  },

  integer: (value: any, message: string = '请输入有效的整数'): string | undefined => {
    if (value !== null && value !== undefined && value !== '' && !Number.isInteger(Number(value))) {
      return message;
    }
    return undefined;
  },

  min: (min: number, message?: string) => (value: any): string | undefined => {
    if (value !== null && value !== undefined && value !== '' && Number(value) < min) {
      return message || `值不能小于 ${min}`;
    }
    return undefined;
  },

  max: (max: number, message?: string) => (value: any): string | undefined => {
    if (value !== null && value !== undefined && value !== '' && Number(value) > max) {
      return message || `值不能大于 ${max}`;
    }
    return undefined;
  },

  pattern: (regex: RegExp, message: string) => (value: string): string | undefined => {
    if (value && !regex.test(value)) {
      return message;
    }
    return undefined;
  },

  url: (value: string, message: string = '请输入有效的URL'): string | undefined => {
    const urlRegex = /^https?:\/\/[^\s/$.?#].[^\s]*$/i;
    if (value && !urlRegex.test(value)) {
      return message;
    }
    return undefined;
  },

  ipAddress: (value: string, message: string = '请输入有效的IP地址'): string | undefined => {
    const ipRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
    if (value && !ipRegex.test(value)) {
      return message;
    }
    return undefined;
  },

  password: (value: string, message: string = '密码至少需要8个字符，包含字母和数字'): string | undefined => {
    const passwordRegex = /^(?=.*[a-zA-Z])(?=.*\d).{8,}$/;
    if (value && !passwordRegex.test(value)) {
      return message;
    }
    return undefined;
  },

  confirmPassword: (password: string) => (value: string, message: string = '两次输入的密码不一致'): string | undefined => {
    if (value !== password) {
      return message;
    }
    return undefined;
  },
};

export type ValidationRule = (value: any) => string | undefined;
export type ValidationSchema = Record<string, ValidationRule[]>;

export interface ValidationResult {
  valid: boolean;
  errors: Record<string, string>;
}

export function validateField(value: any, rules: ValidationRule[]): string | undefined {
  for (const rule of rules) {
    const error = rule(value);
    if (error) return error;
  }
  return undefined;
}

export function validateForm(
  values: Record<string, any>,
  schema: ValidationSchema,
): ValidationResult {
  const errors: Record<string, string> = {};

  for (const [field, rules] of Object.entries(schema)) {
    const error = validateField(values[field], rules);
    if (error) {
      errors[field] = error;
    }
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
  };
}

export function createUserFormSchema(): ValidationSchema {
  return {
    name: [validators.required(), validators.maxLength(50)],
    email: [validators.required(), validators.email()],
    phone: [validators.required(), validators.phone()],
    role: [validators.required()],
    department: [validators.required()],
  };
}

export function createDeviceFormSchema(): ValidationSchema {
  return {
    name: [validators.required(), validators.maxLength(100)],
    type: [validators.required()],
    location: [validators.required()],
    ip: [validators.required(), validators.ipAddress()],
  };
}

export function createLoginFormSchema(): ValidationSchema {
  return {
    username: [validators.required(), validators.minLength(3)],
    password: [validators.required(), validators.minLength(6)],
  };
}

export function createSettingsFormSchema(): ValidationSchema {
  return {
    system_name: [validators.required(), validators.maxLength(100)],
    log_retention_days: [validators.required(), validators.integer(), validators.min(1), validators.max(365)],
    session_timeout_minutes: [validators.required(), validators.integer(), validators.min(1), validators.max(1440)],
    max_login_attempts: [validators.required(), validators.integer(), validators.min(1), validators.max(10)],
    password_min_length: [validators.required(), validators.integer(), validators.min(6), validators.max(32)],
  };
}
