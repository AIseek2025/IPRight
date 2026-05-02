import type { CSSProperties } from 'react';

const tableStyle: CSSProperties = {
  width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8,
};

const thStyle: CSSProperties = {
  padding: '12px 16px', textAlign: 'left' as const,
  borderBottom: '2px solid #f0f0f0', background: '#fafafa',
};

const tdStyle: CSSProperties = {
  padding: '12px 16px', borderBottom: '1px solid #f0f0f0',
};

const statusBadge = (status: string) => ({
  padding: '2px 8px', borderRadius: 4, fontSize: 12,
  background: status === '正常' || status === '在线' || status === '已完成'
    ? '#f6ffed' : status === '处理中' || status === '维护中'
    ? '#fff7e6' : '#fff2f0',
  color: status === '正常' || status === '在线' || status === '已完成'
    ? '#52c41a' : status === '处理中' || status === '维护中'
    ? '#faad14' : '#ff4d4f',
});

export interface Column<T> {
  key: string;
  title: string;
  render?: (record: T, index: number) => React.ReactNode;
}

export function DataTable<T extends Record<string, any>>({
  columns,
  data,
}: {
  columns: Column<T>[];
  data: T[];
}) {
  return (
    <table style={tableStyle}>
      <thead>
        <tr style={{ borderBottom: '2px solid #f0f0f0', background: '#fafafa' }}>
          {columns.map(col => (
            <th key={col.key} style={thStyle}>{col.title}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map((row, i) => (
          <tr key={i} style={{ borderBottom: '1px solid #f0f0f0' }}>
            {columns.map(col => (
              <td key={col.key} style={tdStyle}>
                {col.render ? col.render(row, i) : row[col.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export { statusBadge };
