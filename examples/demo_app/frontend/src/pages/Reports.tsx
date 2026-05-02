export default function Reports() {
  const reports = [
    { id: 'RPT-001', name: '月度库存报表', type: '库存', creator: '系统', date: '2026-04-01', status: '已完成' },
    { id: 'RPT-002', name: '设备巡检周报', type: '巡检', creator: '张工', date: '2026-04-25', status: '已完成' },
    { id: 'RPT-003', name: '工单处理日报', type: '工单', creator: '李管理', date: '2026-04-30', status: '处理中' },
    { id: 'RPT-004', name: '园区能耗分析', type: '能耗', creator: '系统', date: '2026-04-28', status: '已完成' },
    { id: 'RPT-005', name: '安全巡检月报', type: '安全', creator: '王队长', date: '2026-04-29', status: '已完成' },
    { id: 'RPT-006', name: '设备维修统计', type: '维修', creator: '系统', date: '2026-04-30', status: '处理中' },
  ];

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 24 }}>📋 报表统计</h1>
      <div style={{ marginBottom: 16 }}>
        <button style={{ padding: '6px 16px', background: '#1890ff', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', marginRight: 8 }}>生成报表</button>
        <select style={{ padding: '6px 12px', border: '1px solid #d9d9d9', borderRadius: 4, marginRight: 8 }}>
          <option>全部类型</option><option>库存</option><option>巡检</option><option>工单</option><option>能耗</option><option>安全</option>
        </select>
        <input type="date" style={{ padding: '6px 12px', border: '1px solid #d9d9d9', borderRadius: 4 }} />
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8 }}>
        <thead><tr style={{ borderBottom: '2px solid #f0f0f0', background: '#fafafa' }}>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>编号</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>报表名称</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>类型</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>创建者</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>日期</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>状态</th>
          <th style={{ padding: '12px 16px', textAlign: 'left' }}>操作</th>
        </tr></thead>
        <tbody>{reports.map((r, i) => (
          <tr key={i} style={{ borderBottom: '1px solid #f0f0f0' }}>
            <td style={{ padding: '12px 16px' }}>{r.id}</td>
            <td style={{ padding: '12px 16px' }}>{r.name}</td>
            <td style={{ padding: '12px 16px' }}><span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 12, background: '#f0f5ff', color: '#1890ff' }}>{r.type}</span></td>
            <td style={{ padding: '12px 16px' }}>{r.creator}</td>
            <td style={{ padding: '12px 16px' }}>{r.date}</td>
            <td style={{ padding: '12px 16px' }}><span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 12, background: r.status==='已完成'?'#f6ffed':'#fff7e6', color: r.status==='已完成'?'#52c41a':'#faad14' }}>{r.status}</span></td>
            <td style={{ padding: '12px 16px' }}><button style={{ padding: '2px 8px', cursor: 'pointer', marginRight: 4 }}>查看</button><button style={{ padding: '2px 8px', cursor: 'pointer' }}>下载</button></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
