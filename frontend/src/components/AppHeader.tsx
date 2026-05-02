import { Layout, Menu } from 'antd';
import { PlusOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';

const { Header } = Layout;

export default function AppHeader() {
  const navigate = useNavigate();
  const location = useLocation();

  const items = [
    { key: '/', icon: <PlusOutlined />, label: '创建任务' },
    { key: '/tasks', icon: <UnorderedListOutlined />, label: '任务列表' },
  ];

  return (
    <Header style={{ display: 'flex', alignItems: 'center' }}>
      <div style={{ color: '#fff', fontSize: 18, fontWeight: 700, marginRight: 32, whiteSpace: 'nowrap' }}>
        IPRight
      </div>
      <Menu
        theme="dark"
        mode="horizontal"
        selectedKeys={[location.pathname]}
        items={items}
        onClick={({ key }) => navigate(key)}
        style={{ flex: 1, minWidth: 0 }}
      />
    </Header>
  );
}
