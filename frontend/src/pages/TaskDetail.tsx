import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Card,
  Typography,
  Descriptions,
  Tag,
  Timeline,
  List,
  Button,
  Space,
  Skeleton,
  message,
  Progress,
  Alert,
  Result,
  Empty,
} from 'antd';
import {
  DownloadOutlined,
  ReloadOutlined,
  CloseCircleOutlined,
  PictureOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import {
  getTaskDashboard,
  getTaskArtifacts,
  getTaskScreenshots,
  getExportDownload,
  retryTask,
  cancelTask,
} from '@/api/client';
import {
  STATUS_LABELS,
  STATUS_COLORS,
} from '@/types';
import type { TaskDashboard, ArtifactItem, ScreenshotItem, EventItem } from '@/types';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

const STAGE_ORDER = [
  'queued', 'planning', 'coding', 'building', 'running',
  'capturing', 'writing_manual', 'writing_code_book', 'publishing', 'completed',
];

function getProgress(status: string): number {
  const idx = STAGE_ORDER.indexOf(status);
  if (idx < 0) return status === 'completed' ? 100 : 0;
  return Math.round((idx / (STAGE_ORDER.length - 1)) * 100);
}

export default function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>();
  const [dashboard, setDashboard] = useState<TaskDashboard | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [screenshots, setScreenshots] = useState<ScreenshotItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchData = useCallback(async () => {
    if (!taskId) return;
    try {
      const [d, a, s] = await Promise.all([
        getTaskDashboard(taskId),
        getTaskArtifacts(taskId),
        getTaskScreenshots(taskId),
      ]);
      setDashboard(d);
      setArtifacts(a.items);
      setScreenshots(s.items);
      setError(null);
    } catch {
      setError('加载任务详情失败，请检查后端服务是否运行');
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    fetchData();
    const isActive = dashboard?.task.status !== 'completed'
      && dashboard?.task.status !== 'failed'
      && dashboard?.task.status !== 'cancelled';

    if (isActive || !dashboard) {
      const interval = setInterval(fetchData, 3000);
      return () => clearInterval(interval);
    }
  }, [fetchData, dashboard?.task.status]);

  const handleRetry = async (fromStage?: string) => {
    if (!taskId) return;
    setActionLoading(true);
    try {
      await retryTask(taskId, fromStage);
      message.success('重试已触发');
      fetchData();
    } catch {
      message.error('重试失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!taskId) return;
    setActionLoading(true);
    try {
      await cancelTask(taskId);
      message.success('任务已取消');
      fetchData();
    } catch {
      message.error('取消失败');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="page-container">
        <Skeleton active paragraph={{ rows: 6 }} />
        <br />
        <Skeleton active paragraph={{ rows: 4 }} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <Result
          status="error"
          title="加载失败"
          subTitle={error}
          extra={<Button type="primary" onClick={fetchData}>重试</Button>}
        />
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="page-container">
        <Result status="404" title="任务不存在" subTitle="请检查任务 ID 是否正确" />
      </div>
    );
  }

  const { task, timeline, exports } = dashboard;
  const progress = getProgress(task.status);
  const isTerminal = ['completed', 'failed', 'cancelled'].includes(task.status);

  return (
    <div>
      <div className="page-container">
        <Space align="center" style={{ marginBottom: 16 }} wrap>
          <Title level={4} style={{ margin: 0 }}>
            {task.product_name} {task.version}
          </Title>
          <Tag color={STATUS_COLORS[task.status]} icon={!isTerminal ? <SyncOutlined spin /> : undefined}>
            {STATUS_LABELS[task.status] || task.status}
          </Tag>
        </Space>

        {!isTerminal && (
          <Progress
            percent={progress}
            status="active"
            strokeColor={{ from: '#108ee9', to: '#87d068' }}
            style={{ marginBottom: 16 }}
          />
        )}

        {task.status === 'failed' && (
          <Alert
            type="error"
            message="任务执行失败"
            description="可尝试重试任务或查看时间线了解失败原因"
            style={{ marginBottom: 16 }}
            showIcon
          />
        )}

        <Descriptions column={3} size="small" bordered>
          <Descriptions.Item label="任务 ID">
            <Text copyable={{ text: task.id }}>{task.id.slice(0, 8)}...</Text>
          </Descriptions.Item>
          <Descriptions.Item label="关键词">{task.keyword}</Descriptions.Item>
          <Descriptions.Item label="行业">{task.industry || '-'}</Descriptions.Item>
          <Descriptions.Item label="当前阶段">
            {STATUS_LABELS[task.current_stage || ''] || task.current_stage || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {dayjs(task.created_at).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
          <Descriptions.Item label="更新时间">
            {dayjs(task.updated_at).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
        </Descriptions>

        <Space style={{ marginTop: 16 }}>
          <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
            刷新
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => handleRetry()}
            loading={actionLoading}
            disabled={task.status === 'completed' || task.status === 'cancelled'}
          >
            重试
          </Button>
          <Button
            danger
            icon={<CloseCircleOutlined />}
            onClick={handleCancel}
            loading={actionLoading}
            disabled={isTerminal}
          >
            取消
          </Button>
        </Space>
      </div>

      <div className="page-container">
        <Title level={5}>状态时间线</Title>
        {timeline.length > 0 ? (
          <Timeline
            items={timeline.map((ev: EventItem) => ({
              color: ev.event_type.includes('failed') ? 'red'
                : ev.event_type.includes('completed') ? 'green'
                : 'blue',
              children: (
                <div>
                  <div style={{ fontWeight: 500 }}>{ev.title}</div>
                  {ev.detail && <div style={{ color: '#666', fontSize: 13 }}>{ev.detail}</div>}
                  <div style={{ fontSize: 12, color: '#999' }}>
                    {dayjs(ev.created_at).format('HH:mm:ss')}
                  </div>
                </div>
              ),
            }))}
          />
        ) : (
          <Empty description="暂无事件记录" />
        )}
      </div>

      {screenshots.length > 0 && (
        <div className="page-container">
          <Title level={5}>
            <PictureOutlined /> 页面截图 ({screenshots.length})
          </Title>
          <List
            dataSource={screenshots}
            renderItem={(s: ScreenshotItem) => (
              <List.Item>
                <List.Item.Meta
                  title={`${s.page_title} (${s.scenario_id})`}
                  description={
                    <>
                      <div>路由: {s.route}</div>
                      {s.caption && <div>图注: {s.caption}</div>}
                    </>
                  }
                />
              </List.Item>
            )}
          />
        </div>
      )}

      <div className="page-container">
        <Title level={5}>工件列表 ({artifacts.length})</Title>
        {artifacts.length > 0 ? (
          <List
            dataSource={artifacts}
            renderItem={(a: ArtifactItem) => (
              <List.Item>
                <List.Item.Meta
                  title={a.artifact_name}
                  description={
                    <Space>
                      <Tag>{a.artifact_type}</Tag>
                      <span>{dayjs(a.created_at).format('HH:mm:ss')}</span>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <Empty description="暂无工件" />
        )}
      </div>

      <div className="page-container">
        <Title level={5}>可下载文件</Title>
        {exports.length === 0 ? (
          <Empty
            description={isTerminal ? '未生成导出文件' : '请等待任务完成'}
          />
        ) : (
          <List
            dataSource={exports}
            renderItem={(exp) => (
              <List.Item
                actions={[
                  exp.status === 'ready' ? (
                    <Button
                      type="primary"
                      icon={<DownloadOutlined />}
                      href={getExportDownload(exp.id)}
                      target="_blank"
                    >
                      下载
                    </Button>
                  ) : (
                    <Tag color="orange">{exp.status}</Tag>
                  ),
                ]}
              >
                <List.Item.Meta
                  title={exp.file_name}
                  description={<Tag>{exp.export_type}</Tag>}
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  );
}
