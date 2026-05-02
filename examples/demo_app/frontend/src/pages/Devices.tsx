export default function Devices() {
  const devices = [
    { id: 'DEV-001', name: '园区大门摄像头', type: '监控设备', location: 'A区入口', status: '在线' },
    { id: 'DEV-002', name: '停车场道闸', type: '通行设备', location: 'B1层', status: '在线' },
    { id: 'DEV-003', name: '中央空调主机', type: '暖通设备', location: '机房1', status: '维护中' },
    { id: 'DEV-004', name: '消防水泵', type: '消防设备', location: '泵房', status: '在线' },
    { id: 'DEV-005', name: '电梯1号', type: '通行设备', location: '1号楼', status: '离线' },
  ];
  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 24 }}>🔧 设备管理</h1>
      <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8 }}>
        <thead><tr style={{ borderBottom: '2px solid #f0f0f0', background: '#fafafa' }}>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>设备编号</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>设备名称</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>类型</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>位置</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>状态</th>
        </tr></thead>
        <tbody>{devices.map((d, i) => (
          <tr key={i} style={{ borderBottom: '1px solid #f0f0f0' }}>
            <td style={{ padding: '12px 16px' }}>{d.id}</td>
            <td style={{ padding: '12px 16px' }}>{d.name}</td>
            <td style={{ padding: '12px 16px' }}>{d.type}</td>
            <td style={{ padding: '12px 16px' }}>{d.location}</td>
            <td style={{ padding: '12px 16px' }}>{d.status}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
