import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Table, Tag, Typography, Input, Select, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { listTasks, getApiErrorMessage } from '@/api/client';
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
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const requestSeq = useRef(0);

  const fetchTasks = async (options?: {
    nextPage?: number;
    nextStatus?: string;
    nextKeyword?: string;
  }) => {
    const nextPage = options?.nextPage ?? page;
    const nextStatus = options?.nextStatus ?? statusFilter;
    const nextKeyword = options?.nextKeyword ?? keywordFilter;
    const seq = ++requestSeq.current;
    setLoading(true);
    try {
      const data = await listTasks({
        page: nextPage,
        page_size: pageSize,
        status: nextStatus,
        keyword: nextKeyword || undefined,
      });
      if (seq !== requestSeq.current) return;
      setTasks(data.items);
      setTotal(data.total);
      setError(null);
    } catch (err) {
      if (seq !== requestSeq.current) return;
      setError(getApiErrorMessage(err, '任务列表加载失败，请检查服务状态后重试'));
    } finally {
      if (seq === requestSeq.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void fetchTasks({ nextPage: page, nextStatus: statusFilter });
    // fetchTasks depends on multiple state values via closure but the effect
    // is intentionally only re-fired by paginate / status filter change. The
    // search input has its own onSearch / onChange handlers that call
    // fetchTasks explicitly with the latest keyword.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        {error && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
            message="加载失败"
            description={error}
          />
        )}
        <Space style={{ marginBottom: 16 }}>
          <Input.Search
            placeholder="搜索关键词"
            value={keywordFilter}
            onChange={(e) => {
              const nextValue = e.target.value;
              setKeywordFilter(nextValue);
              if (!nextValue.trim()) {
                setPage(1);
                setError(null);
                void fetchTasks({ nextPage: 1, nextKeyword: '' });
              }
            }}
            onSearch={() => {
              setPage(1);
              setError(null);
              void fetchTasks({ nextPage: 1, nextKeyword: keywordFilter });
            }}
            style={{ width: 240 }}
            allowClear
          />
          <Select
            placeholder="筛选状态"
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v);
              setPage(1);
            }}
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
          locale={{
            emptyText: error ? '任务列表加载失败' : '暂无数据',
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
