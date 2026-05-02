export default function Alerts() {
  const alerts = [
    { id: 'ALT-001', device: '中央空调主机', type: '温度异常', level: '严重', time: '2026-04-30 14:35', status: '未处理' },
    { id: 'ALT-002', device: '电梯1号', type: '运行故障', level: '严重', time: '2026-04-30 12:10', status: '处理中' },
    { id: 'ALT-003', device: '消防水泵', type: '压力偏低', level: '警告', time: '2026-04-30 10:22', status: '已处理' },
    { id: 'ALT-004', device: '园区大门摄像头', type: '信号丢失', level: '严重', time: '2026-04-29 23:45', status: '已处理' },
    { id: 'ALT-005', device: '停车场道闸', type: '通信超时', level: '警告', time: '2026-04-29 18:30', status: '已处理' },
    { id: 'ALT-006', device: '配电柜A区', type: '电流过载', level: '严重', time: '2026-04-29 15:00', status: '处理中' },
    { id: 'ALT-007', device: '供水泵', type: '流量异常', level: '提示', time: '2026-04-29 09:15', status: '已处理' },
    { id: 'ALT-008', device: '门禁系统', type: '非法闯入', level: '严重', time: '2026-04-28 22:00', status: '已处理' },
  ];

  const levelColors: Record<string, string> = { '严重': '#ff4d4f', '警告': '#faad14', '提示': '#1890ff' };
  const statusColors: Record<string, string> = { '未处理': '#ff4d4f', '处理中': '#faad14', '已处理': '#52c41a' };

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 24 }}>🚨 设备告警</h1>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        {[{ title: '未处理', value: '2', color: '#ff4d4f' }, { title: '处理中', value: '2', color: '#faad14' }, { title: '已处理', value: '4', color: '#52c41a' }, { title: '总计', value: '8', color: '#1890ff' }].map(s => (
          <div key={s.title} style={{ background: '#fff', padding: 16, borderRadius: 8, textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: s.color }}>{s.value}</div>
            <div style={{ color: '#666', marginTop: 4 }}>{s.title}</div>
          </div>
        ))}
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8 }}>
        <thead><tr style={{ borderBottom: '2px solid #f0f0f0', background: '#fafafa' }}>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>编号</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>设备</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>告警类型</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>级别</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>时间</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>状态</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>操作</th>
        </tr></thead>
        <tbody>{alerts.map((a, i) => (
          <tr key={i} style={{ borderBottom: '1px solid #f0f0f0' }}>
            <td style={{ padding: '12px 16px' }}>{a.id}</td>
            <td style={{ padding: '12px 16px' }}>{a.device}</td>
            <td style={{ padding: '12px 16px' }}>{a.type}</td>
            <td style={{ padding: '12px 16px' }}><span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 12, background: levelColors[a.level] + '20', color: levelColors[a.level] }}>{a.level}</span></td>
            <td style={{ padding: '12px 16px' }}>{a.time}</td>
            <td style={{ padding: '12px 16px' }}><span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 12, background: statusColors[a.status] + '20', color: statusColors[a.status] }}>{a.status}</span></td>
            <td style={{ padding: '12px 16px' }}><button style={{ padding: '2px 8px', cursor: 'pointer', marginRight: 4 }}>处理</button><button style={{ padding: '2px 8px', cursor: 'pointer' }}>忽略</button></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
