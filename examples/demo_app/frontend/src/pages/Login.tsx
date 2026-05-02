export default function Login({ onLogin }: { onLogin: () => void }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <div style={{ width: 400, padding: 40, background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
        <h1 style={{ textAlign: 'center', marginBottom: 32, fontSize: 24 }}>智慧园区管理平台</h1>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6 }}>用户名</label>
          <input name="username" placeholder="请输入用户名" defaultValue="admin"
            style={{ width: '100%', padding: '8px 12px', border: '1px solid #d9d9d9', borderRadius: 4, boxSizing: 'border-box' }} />
        </div>
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: 'block', marginBottom: 6 }}>密码</label>
          <input name="password" type="password" placeholder="请输入密码" defaultValue="admin123"
            style={{ width: '100%', padding: '8px 12px', border: '1px solid #d9d9d9', borderRadius: 4, boxSizing: 'border-box' }} />
        </div>
        <button onClick={onLogin}
          style={{ width: '100%', padding: '10px', background: '#1890ff', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 16 }}>
          登录
        </button>
        <p style={{ textAlign: 'center', marginTop: 16, color: '#999', fontSize: 13 }}>Demo账号: admin / admin123</p>
      </div>
    </div>
  );
}
