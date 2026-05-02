export default function Settings() {
  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 24 }}>⚙️ 系统设置</h1>
      <div style={{ background: '#fff', padding: 24, borderRadius: 8 }}>
        <h3>基本设置</h3>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 4 }}>系统名称</label>
          <input defaultValue="智慧园区管理平台" style={{ padding: '6px 12px', border: '1px solid #d9d9d9', borderRadius: 4, width: 300 }} />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 4 }}>版本号</label>
          <input defaultValue="V1.0" disabled style={{ padding: '6px 12px', border: '1px solid #d9d9d9', borderRadius: 4, width: 300, background: '#f5f5f5' }} />
        </div>
        <h3 style={{ marginTop: 24 }}>通知设置</h3>
        <div style={{ marginBottom: 16 }}>
          <label><input type="checkbox" defaultChecked style={{ marginRight: 8 }} />启用设备告警通知</label>
        </div>
        <div style={{ marginBottom: 16 }}>
          <label><input type="checkbox" defaultChecked style={{ marginRight: 8 }} />启用工单推送</label>
        </div>
        <button style={{ padding: '8px 24px', background: '#1890ff', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', marginTop: 16 }}>保存设置</button>
      </div>
    </div>
  );
}
