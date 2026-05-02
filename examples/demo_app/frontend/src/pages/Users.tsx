export default function Users() {
  const users = [
    { name: '陈志远', role: '管理员', email: 'chen.zhiyuan@park.com', status: '正常' },
    { name: '林晓彤', role: '运维人员', email: 'lin.xiaotong@park.com', status: '正常' },
    { name: '周明轩', role: '保安队长', email: 'zhou.mingxuan@park.com', status: '停用' },
    { name: '许静怡', role: '财务', email: 'xu.jingyi@park.com', status: '正常' },
  ];
  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 24 }}>👥 用户管理</h1>
      <div style={{ marginBottom: 16 }}>
        <button style={{ padding: '6px 16px', background: '#1890ff', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>新增用户</button>
        <input placeholder="搜索用户..." style={{ marginLeft: 12, padding: '6px 12px', border: '1px solid #d9d9d9', borderRadius: 4, width: 200 }} />
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8 }}>
        <thead><tr style={{ borderBottom: '2px solid #f0f0f0', background: '#fafafa' }}>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>姓名</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>角色</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>邮箱</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>状态</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>操作</th>
        </tr></thead>
        <tbody>{users.map((u, i) => (
          <tr key={i} style={{ borderBottom: '1px solid #f0f0f0' }}>
            <td style={{ padding: '12px 16px' }}>{u.name}</td>
            <td style={{ padding: '12px 16px' }}>{u.role}</td>
            <td style={{ padding: '12px 16px' }}>{u.email}</td>
            <td style={{ padding: '12px 16px' }}>
              <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 12, background: u.status === '正常' ? '#f6ffed' : '#fff2f0', color: u.status === '正常' ? '#52c41a' : '#ff4d4f' }}>{u.status}</span>
            </td>
            <td style={{ padding: '12px 16px' }}>
              <button style={{ marginRight: 8, padding: '2px 8px', cursor: 'pointer' }}>编辑</button>
              <button style={{ padding: '2px 8px', cursor: 'pointer', color: '#ff4d4f' }}>删除</button>
            </td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
