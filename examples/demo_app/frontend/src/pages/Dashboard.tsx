export default function Dashboard() {
  const stats = [
    { title: '园区总数', value: '12', color: '#1890ff' },
    { title: '在管设备', value: '1,248', color: '#52c41a' },
    { title: '今日工单', value: '36', color: '#faad14' },
    { title: '在线用户', value: '89', color: '#722ed1' },
  ];
  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 24 }}>📊 系统首页</h1>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        {stats.map(s => (
          <div key={s.title} style={{ background: '#fff', padding: 20, borderRadius: 8, textAlign: 'center' }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: s.color }}>{s.value}</div>
            <div style={{ color: '#666', marginTop: 8 }}>{s.title}</div>
          </div>
        ))}
      </div>
      <div style={{ background: '#fff', padding: 20, borderRadius: 8 }}>
        <h3 style={{ marginTop: 0 }}>最近操作日志</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr style={{ borderBottom: '1px solid #f0f0f0' }}>
            <th style={{ padding: '8px 12px', textAlign: 'left' }}>时间</th>
            <th style={{ padding: '8px 12px', textAlign: 'left' }}>操作</th>
            <th style={{ padding: '8px 12px', textAlign: 'left' }}>用户</th>
            <th style={{ padding: '8px 12px', textAlign: 'left' }}>状态</th>
          </tr></thead>
          <tbody>
            {[['2026-04-30 14:30', '设备巡检', '张工', '完成'],
              ['2026-04-30 13:15', '园区报修', '李管理', '处理中'],
              ['2026-04-30 11:00', '用户注册', '系统', '成功']].map((row, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #fafafa' }}>
                {row.map((cell, j) => <td key={j} style={{ padding: '8px 12px' }}>{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
