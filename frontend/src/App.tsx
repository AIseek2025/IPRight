import { Routes, Route } from 'react-router-dom';
import { Layout } from 'antd';
import { Suspense, lazy, useEffect } from 'react';
import { Spin } from 'antd';
import AppHeader from './components/AppHeader';
import { setApiToken } from './api/client';

const TaskCreate = lazy(() => import('./pages/TaskCreate'));
const TaskList = lazy(() => import('./pages/TaskList'));
const TaskDetail = lazy(() => import('./pages/TaskDetail'));

const { Content, Footer } = Layout;

function PageLoading() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
      <Spin size="large" tip="加载中..." />
    </div>
  );
}

export default function App() {
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const url = new URL(window.location.href);
    const searchToken = url.searchParams.get('token') || url.searchParams.get('api_token');
    const hashParams = new URLSearchParams(url.hash.startsWith('#') ? url.hash.slice(1) : url.hash);
    const hashToken = hashParams.get('token') || hashParams.get('api_token');
    const token = (searchToken || hashToken || '').trim();

    if (!token) return;

    setApiToken(token);
    url.searchParams.delete('token');
    url.searchParams.delete('api_token');
    hashParams.delete('token');
    hashParams.delete('api_token');
    const nextHash = hashParams.toString();
    window.history.replaceState({}, document.title, `${url.pathname}${url.search}${nextHash ? `#${nextHash}` : ''}`);
  }, []);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <AppHeader />
      <Content style={{ padding: '24px', maxWidth: 1200, margin: '0 auto', width: '100%' }}>
        <Suspense fallback={<PageLoading />}>
          <Routes>
            <Route path="/" element={<TaskCreate />} />
            <Route path="/tasks" element={<TaskList />} />
            <Route path="/tasks/:taskId" element={<TaskDetail />} />
          </Routes>
        </Suspense>
      </Content>
      <Footer style={{ textAlign: 'center' }}>
        IPRight - 软著材料自动生成平台
      </Footer>
    </Layout>
  );
}
