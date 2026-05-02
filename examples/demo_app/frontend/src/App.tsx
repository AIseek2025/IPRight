import { useState, useEffect } from 'react';
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Users from './pages/Users';
import Devices from './pages/Devices';
import Settings from './pages/Settings';
import Reports from './pages/Reports';
import Alerts from './pages/Alerts';

const AUTH_KEY = 'ipright_demo_auth';

const navItems = [
  { path: '/dashboard', label: '首页' },
  { path: '/users', label: '用户管理' },
  { path: '/devices', label: '设备管理' },
  { path: '/reports', label: '报表统计' },
  { path: '/alerts', label: '设备告警' },
  { path: '/settings', label: '系统设置' },
];

export default function App() {
  const [loggedIn, setLoggedIn] = useState(() => {
    return localStorage.getItem(AUTH_KEY) === 'true';
  });
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogin = () => {
    localStorage.setItem(AUTH_KEY, 'true');
    setLoggedIn(true);
    navigate('/dashboard');
  };

  const handleLogout = () => {
    localStorage.removeItem(AUTH_KEY);
    setLoggedIn(false);
    navigate('/login');
  };

  if (!loggedIn && location.pathname !== '/login') {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <nav style={{ width: 220, background: '#001529', color: '#fff', padding: 16 }}>
        <h2 style={{ margin: '0 0 24px', fontSize: 18, padding: '8px 0' }}>智慧园区管理平台 V1.0</h2>
        {navItems.map(item => (
          <div key={item.path}
            onClick={() => navigate(item.path)}
            style={{ padding: '10px 16px', cursor: 'pointer', borderRadius: 4,
              background: location.pathname === item.path ? '#1890ff' : 'transparent', marginBottom: 4 }}>
            {item.label}
          </div>
        ))}
        <div onClick={handleLogout}
          style={{ padding: '10px 16px', cursor: 'pointer', borderRadius: 4, marginTop: 24, color: '#ff4d4f' }}>
          退出登录
        </div>
      </nav>
      <main style={{ flex: 1, padding: 24, background: '#f5f5f5' }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/users" element={<Users />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
