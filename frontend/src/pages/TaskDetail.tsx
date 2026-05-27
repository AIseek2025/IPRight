import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import {
  Typography,
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
  getTaskBundleDownload,
  getTaskStreamUrl,
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
  const [artifactsLoading, setArtifactsLoading] = useState(false);
  const [screenshotsLoading, setScreenshotsLoading] = useState(false);
  const [artifactsError, setArtifactsError] = useState<string | null>(null);
  const [screenshotsError, setScreenshotsError] = useState<string | null>(null);
  const dashboardRequestSeq = useRef(0);
  const supportingRequestSeq = useRef(0);
  const realtimeRefreshTimer = useRef<number | null>(null);

  const fetchSupportingData = useCallback(async () => {
    if (!taskId) return;
    const seq = ++supportingRequestSeq.current;
    setArtifactsLoading(true);
    setScreenshotsLoading(true);
    try {
      const [artifactsResult, screenshotsResult] = await Promise.allSettled([
        getTaskArtifacts(taskId, { limit: 80 }),
        getTaskScreenshots(taskId, { limit: 24 }),
      ]);

      if (seq !== supportingRequestSeq.current) return;

      if (artifactsResult.status === 'fulfilled') {
        setArtifacts(artifactsResult.value.items);
        setArtifactsError(null);
      } else {
        setArtifactsError('工件列表加载失败，已保留上一次结果');
      }

      if (screenshotsResult.status === 'fulfilled') {
        setScreenshots(screenshotsResult.value.items);
        setScreenshotsError(null);
      } else {
        setScreenshotsError('页面截图加载失败，已保留上一次结果');
      }
    } finally {
      if (seq === supportingRequestSeq.current) {
        setArtifactsLoading(false);
        setScreenshotsLoading(false);
      }
    }
  }, [taskId]);

  const fetchDashboardData = useCallback(async (background = false) => {
    if (!taskId) return;
    const seq = ++dashboardRequestSeq.current;
    if (!background) {
      setLoading(true);
    }

    try {
      const data = await getTaskDashboard(taskId);
      if (seq !== dashboardRequestSeq.current) return;
      setDashboard(data);
      setError(null);
    } catch {
      if (seq !== dashboardRequestSeq.current) return;
      setError('加载任务详情失败，请检查后端服务是否运行');
    } finally {
      if (!background && seq === dashboardRequestSeq.current) {
        setLoading(false);
      }
    }
  }, [taskId]);

  const refreshAll = useCallback(async () => {
    await fetchDashboardData();
    await fetchSupportingData();
  }, [fetchDashboardData, fetchSupportingData]);

  const scheduleRealtimeRefresh = useCallback((includeSupporting = false) => {
    if (realtimeRefreshTimer.current !== null) {
      window.clearTimeout(realtimeRefreshTimer.current);
    }
    realtimeRefreshTimer.current = window.setTimeout(() => {
      void fetchDashboardData(true);
      if (includeSupporting) {
        void fetchSupportingData();
      }
      realtimeRefreshTimer.current = null;
    }, includeSupporting ? 250 : 400);
  }, [fetchDashboardData, fetchSupportingData]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    if (!taskId) return;

    const source = new EventSource(getTaskStreamUrl(taskId));
    const onStatus = () => {
      scheduleRealtimeRefresh(false);
    };
    const onTaskEvent = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as { event_type?: string };
        const shouldRefreshSupporting = Boolean(
          payload.event_type?.includes('capture')
          || payload.event_type?.includes('publish')
          || payload.event_type?.includes('completed')
          || payload.event_type?.includes('failed')
        );
        scheduleRealtimeRefresh(shouldRefreshSupporting);
      } catch {
        scheduleRealtimeRefresh(false);
      }
    };

    source.addEventListener('status', onStatus);
    source.addEventListener('task_event', onTaskEvent);

    return () => {
      if (realtimeRefreshTimer.current !== null) {
        window.clearTimeout(realtimeRefreshTimer.current);
        realtimeRefreshTimer.current = null;
      }
      source.removeEventListener('status', onStatus);
      source.removeEventListener('task_event', onTaskEvent);
      source.close();
    };
  }, [taskId, scheduleRealtimeRefresh]);

  useEffect(() => {
    const status = dashboard?.task.status;
    const isTerminalStatus = status === 'completed' || status === 'failed' || status === 'cancelled';
    if (isTerminalStatus) {
      return;
    }
    const interval = setInterval(() => {
      void fetchDashboardData(true);
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchDashboardData, dashboard?.task.status]);

  const handleRetry = async (fromStage?: string) => {
    if (!taskId) return;
    setActionLoading(true);
    try {
      await retryTask(taskId, fromStage);
      message.success('重试已触发');
      void refreshAll();
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
      void refreshAll();
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
          extra={<Button type="primary" onClick={() => void refreshAll()}>重试</Button>}
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
  const readyExports = exports.filter((exp) => exp.status === 'ready');
  const manualExport = readyExports.find((exp) => exp.file_name === 'software_manual.docx');
  const codeBookExport = readyExports.find((exp) => exp.file_name === 'source_code_book.docx');
  const applicationFormExport = readyExports.find((exp) => exp.file_name === 'application_form.docx');
  const summaryItems = [
    { label: '任务 ID', value: (
      <Text copyable={{ text: task.id }} style={{ wordBreak: 'break-all' }}>
        {task.id}
      </Text>
    ) },
    { label: '关键词', value: <span style={{ wordBreak: 'break-word' }}>{task.keyword}</span> },
    { label: '行业', value: task.industry || '-' },
    {
      label: '当前阶段',
      value: STATUS_LABELS[task.current_stage || ''] || task.current_stage || '-',
    },
    { label: '创建时间', value: dayjs(task.created_at).format('YYYY-MM-DD HH:mm:ss') },
    { label: '更新时间', value: dayjs(task.updated_at).format('YYYY-MM-DD HH:mm:ss') },
  ];
  const getExportHref = (exportId: string, exportType: string) => {
    if (exportType === 'bundle_zip') {
      return getTaskBundleDownload(task.id);
    }
    return getExportDownload(exportId);
  };
  const getExportLabel = (fileName: string, exportType: string) => {
    if (exportType === 'bundle_zip') return '整套交付 ZIP';
    if (fileName === 'software_manual.docx') return '软件说明书 / 操作手册';
    if (fileName === 'source_code_book.docx') return '软件源代码';
    if (fileName === 'application_form.docx') return '申请表';
    return fileName;
  };

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

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 12,
          }}
        >
          {summaryItems.map((item) => (
            <div
              key={item.label}
              style={{
                border: '1px solid #f0f0f0',
                borderRadius: 8,
                padding: 12,
                minWidth: 0,
              }}
            >
              <div style={{ color: '#666', fontSize: 12, marginBottom: 6 }}>{item.label}</div>
              <div style={{ fontWeight: 500, wordBreak: 'break-word' }}>{item.value}</div>
            </div>
          ))}
        </div>

        <Space style={{ marginTop: 16 }} wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void refreshAll()} loading={loading}>
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

      <div className="page-container">
        <Title level={5}>
          <PictureOutlined /> 页面截图 ({screenshots.length})
        </Title>
        {screenshotsError && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message={screenshotsError}
          />
        )}
        {screenshots.length > 0 ? (
          <List
            loading={screenshotsLoading}
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
        ) : (
          <Empty description={screenshotsLoading ? '页面截图加载中' : '暂无页面截图'} />
        )}
      </div>

      <div className="page-container">
        <Title level={5}>工件列表 ({artifacts.length})</Title>
        {artifactsError && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message={artifactsError}
          />
        )}
        {artifacts.length > 0 ? (
          <List
            loading={artifactsLoading}
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
          <Empty description={artifactsLoading ? '工件列表加载中' : '暂无工件'} />
        )}
      </div>

      <div className="page-container">
        <Title level={5}>可下载文件</Title>
        <Space style={{ marginBottom: 16 }} wrap>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            href={getTaskBundleDownload(task.id)}
            target="_blank"
            disabled={!isTerminal}
          >
            下载整套软件/文件/文档 ZIP
          </Button>
          <Button
            icon={<DownloadOutlined />}
            href={manualExport ? getExportDownload(manualExport.id) : undefined}
            target="_blank"
            disabled={!manualExport}
          >
            下载软件说明书
          </Button>
          <Button
            icon={<DownloadOutlined />}
            href={codeBookExport ? getExportDownload(codeBookExport.id) : undefined}
            target="_blank"
            disabled={!codeBookExport}
          >
            下载源码文档
          </Button>
          <Button
            icon={<DownloadOutlined />}
            href={applicationFormExport ? getExportDownload(applicationFormExport.id) : undefined}
            target="_blank"
            disabled={!applicationFormExport}
          >
            下载申请表
          </Button>
        </Space>
        <Alert
          style={{ marginBottom: 16 }}
          type="info"
          showIcon
          message="整套 ZIP 包含当前任务目录下的软件源码、运行工作区、PRD/清单、截图工件、构建产物、软件说明书、源码文档和申请表。"
        />
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
                      href={getExportHref(exp.id, exp.export_type)}
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
                  title={getExportLabel(exp.file_name, exp.export_type)}
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
