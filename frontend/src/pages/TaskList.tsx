import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tag, Typography, Input, Select, Space, Card } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { listTasks } from '@/api/client';
import { STATUS_LABELS, STATUS_COLORS } from '@/types';
import type { TaskItem } from '@/types';
import dayjs from 'dayjs';

const { Title } = Typography;

export default function TaskList() {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [keywordFilter, setKeywordFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const data = await listTasks({
        page,
        page_size: pageSize,
        status: statusFilter,
        keyword: keywordFilter || undefined,
      });
      setTasks(data.items);
      setTotal(data.total);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, [page, statusFilter]);

  const columns: ColumnsType<TaskItem> = [
    {
      title: '软件名称',
      dataIndex: 'product_name',
      key: 'product_name',
      render: (text: string, record: TaskItem) => (
        <a onClick={() => navigate(`/tasks/${record.id}`)}>{text}</a>
      ),
    },
    {
      title: '关键词',
      dataIndex: 'keyword',
      key: 'keyword',
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 80,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 140,
      render: (status: string) => (
        <Tag color={STATUS_COLORS[status] || 'default'}>
          {STATUS_LABELS[status] || status}
        </Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm'),
    },
  ];

  return (
    <div>
      <div className="page-container">
        <Title level={4}>任务列表</Title>
        <Space style={{ marginBottom: 16 }}>
          <Input.Search
            placeholder="搜索关键词"
            value={keywordFilter}
            onChange={(e) => setKeywordFilter(e.target.value)}
            onSearch={fetchTasks}
            style={{ width: 240 }}
            allowClear
          />
          <Select
            placeholder="筛选状态"
            value={statusFilter}
            onChange={(v) => { setStatusFilter(v); setPage(1); }}
            allowClear
            style={{ width: 160 }}
            options={Object.entries(STATUS_LABELS).map(([k, v]) => ({ value: k, label: v }))}
          />
        </Space>
        <Table
          columns={columns}
          dataSource={tasks}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            onChange: (p) => setPage(p),
            showTotal: (t) => `共 ${t} 条`,
          }}
          onRow={(record) => ({
            onClick: () => navigate(`/tasks/${record.id}`),
            style: { cursor: 'pointer' },
          })}
        />
      </div>
    </div>
  );
}
