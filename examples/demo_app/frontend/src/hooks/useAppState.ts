/** State management utilities using React Context + useReducer pattern. */

import React, { createContext, useContext, useReducer, useCallback } from 'react';

export interface AppState {
  user: {
    isLoggedIn: boolean;
    username: string;
    role: string;
    permissions: string[];
  } | null;
  settings: {
    theme: 'light' | 'dark';
    language: string;
    notifications: boolean;
    pageSize: number;
  };
  ui: {
    sidebarCollapsed: boolean;
    globalLoading: boolean;
    currentPage: string;
    breadcrumbs: { title: string; path?: string }[];
  };
  cache: Record<string, { data: any; timestamp: number }>;
}

export type AppAction =
  | { type: 'LOGIN'; payload: { username: string; role: string; permissions: string[] } }
  | { type: 'LOGOUT' }
  | { type: 'SET_SETTINGS'; payload: Partial<AppState['settings']> }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_PAGE'; payload: string }
  | { type: 'SET_BREADCRUMBS'; payload: { title: string; path?: string }[] }
  | { type: 'SET_CACHE'; payload: { key: string; data: any } }
  | { type: 'CLEAR_CACHE' };

export const initialAppState: AppState = {
  user: null,
  settings: {
    theme: 'light',
    language: 'zh-CN',
    notifications: true,
    pageSize: 20,
  },
  ui: {
    sidebarCollapsed: false,
    globalLoading: false,
    currentPage: '/',
    breadcrumbs: [{ title: '首页', path: '/' }],
  },
  cache: {},
};

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'LOGIN':
      return {
        ...state,
        user: {
          isLoggedIn: true,
          username: action.payload.username,
          role: action.payload.role,
          permissions: action.payload.permissions,
        },
      };
    case 'LOGOUT':
      return {
        ...state,
        user: null,
        cache: {},
      };
    case 'SET_SETTINGS':
      return {
        ...state,
        settings: { ...state.settings, ...action.payload },
      };
    case 'TOGGLE_SIDEBAR':
      return {
        ...state,
        ui: { ...state.ui, sidebarCollapsed: !state.ui.sidebarCollapsed },
      };
    case 'SET_LOADING':
      return {
        ...state,
        ui: { ...state.ui, globalLoading: action.payload },
      };
    case 'SET_PAGE':
      return {
        ...state,
        ui: { ...state.ui, currentPage: action.payload },
      };
    case 'SET_BREADCRUMBS':
      return {
        ...state,
        ui: { ...state.ui, breadcrumbs: action.payload },
      };
    case 'SET_CACHE':
      return {
        ...state,
        cache: {
          ...state.cache,
          [action.payload.key]: {
            data: action.payload.data,
            timestamp: Date.now(),
          },
        },
      };
    case 'CLEAR_CACHE':
      return {
        ...state,
        cache: {},
      };
    default:
      return state;
  }
}

export interface AppContextType {
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
  login: (username: string, role: string, permissions: string[]) => void;
  logout: () => void;
  setLoading: (loading: boolean) => void;
  navigateTo: (page: string) => void;
  updateSettings: (settings: Partial<AppState['settings']>) => void;
  getCache: (key: string) => any;
  setCache: (key: string, data: any) => void;
}

export const AppContext = createContext<AppContextType | null>(null);

export function useAppState(): AppContextType {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useAppState must be used within AppStateProvider');
  }
  return context;
}

export function createAppContextValue(
  state: AppState,
  dispatch: React.Dispatch<AppAction>,
): AppContextType {
  return {
    state,
    dispatch,
    login: useCallback(
      (username, role, permissions) => {
        dispatch({ type: 'LOGIN', payload: { username, role, permissions } });
      },
      [dispatch],
    ),
    logout: useCallback(() => {
      dispatch({ type: 'LOGOUT' });
      localStorage.removeItem('auth_token');
    }, [dispatch]),
    setLoading: useCallback(
      (loading) => dispatch({ type: 'SET_LOADING', payload: loading }),
      [dispatch],
    ),
    navigateTo: useCallback(
      (page) => dispatch({ type: 'SET_PAGE', payload: page }),
      [dispatch],
    ),
    updateSettings: useCallback(
      (settings) => dispatch({ type: 'SET_SETTINGS', payload: settings }),
      [dispatch],
    ),
    getCache: useCallback(
      (key) => {
        const entry = state.cache[key];
        if (entry && Date.now() - entry.timestamp < 60000) {
          return entry.data;
        }
        return null;
      },
      [state.cache],
    ),
    setCache: useCallback(
      (key, data) => dispatch({ type: 'SET_CACHE', payload: { key, data } }),
      [dispatch],
    ),
  };
}

export function useUser() {
  const { state } = useAppState();
  return state.user;
}

export function useSettings() {
  const { state, updateSettings } = useAppState();
  return { settings: state.settings, updateSettings };
}

export function useUI() {
  const { state, dispatch } = useAppState();
  return {
    ui: state.ui,
    toggleSidebar: () => dispatch({ type: 'TOGGLE_SIDEBAR' }),
    setBreadcrumbs: (items: { title: string; path?: string }[]) =>
      dispatch({ type: 'SET_BREADCRUMBS', payload: items }),
  };
}

export function useCache() {
  const { getCache, setCache, dispatch } = useAppState();
  return {
    getCache,
    setCache,
    clearCache: () => dispatch({ type: 'CLEAR_CACHE' }),
  };
}
