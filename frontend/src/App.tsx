import { Routes, Route } from 'react-router-dom';
import { Layout } from 'antd';
import { Suspense, lazy } from 'react';
import { Spin } from 'antd';
import AppHeader from './components/AppHeader';

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
