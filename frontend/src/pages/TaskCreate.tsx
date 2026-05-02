import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  Form,
  Input,
  Select,
  Button,
  Typography,
  Space,
  message,
  Divider,
} from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import { createTask } from '@/api/client';

const { Title, Paragraph } = Typography;

export default function TaskCreate() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (values: {
    keyword: string;
    product_name?: string;
    version?: string;
    industry?: string;
    notes?: string;
  }) => {
    setLoading(true);
    try {
      const result = await createTask(values);
      message.success(`任务创建成功: ${result.task_id}`);
      navigate(`/tasks/${result.task_id}`);
    } catch (err) {
      message.error('创建任务失败，请检查后端服务');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-container" style={{ marginBottom: 24 }}>
        <Title level={3}>
          <ThunderboltOutlined /> IPRight 软著材料自动生成平台
        </Title>
        <Paragraph type="secondary">
          输入关键词，平台自动完成 PRD 生成、软件开发、运行截图、说明书 Word 和源码 Word 的全流程自动生产。
        </Paragraph>
      </div>

      <div className="page-container">
        <Title level={4}>创建新任务</Title>
        <Form
          form={form}
          layout="vertical"
          className="task-create-form"
          onFinish={handleSubmit}
          initialValues={{ version: 'V1.0' }}
        >
          <Form.Item
            name="keyword"
            label="关键词"
            rules={[{ required: true, message: '请输入产品关键词' }]}
          >
            <Input placeholder="例如: 智慧园区管理平台" size="large" />
          </Form.Item>

          <Form.Item name="product_name" label="软件名称（可选，默认同关键词）">
            <Input placeholder="软件名称" />
          </Form.Item>

          <Form.Item name="version" label="版本号">
            <Select
              options={[
                { value: 'V1.0', label: 'V1.0' },
                { value: 'V2.0', label: 'V2.0' },
                { value: 'V3.0', label: 'V3.0' },
              ]}
            />
          </Form.Item>

          <Form.Item name="industry" label="行业类型">
            <Select
              placeholder="选择行业"
              options={[
                { value: '园区', label: '园区' },
                { value: '物流', label: '物流' },
                { value: '制造', label: '制造' },
                { value: '金融', label: '金融' },
                { value: '医疗', label: '医疗' },
                { value: '教育', label: '教育' },
                { value: '能源', label: '能源' },
                { value: '交通', label: '交通' },
              ]}
              allowClear
            />
          </Form.Item>

          <Form.Item name="notes" label="补充说明">
            <Input.TextArea
              placeholder="可选: 对产品功能、目标用户的补充说明"
              rows={3}
            />
          </Form.Item>

          <Divider />

          <Space>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              loading={loading}
              icon={<ThunderboltOutlined />}
            >
              一键开始生成
            </Button>
            <Button size="large" onClick={() => form.resetFields()}>
              重置
            </Button>
          </Space>
        </Form>
      </div>
    </div>
  );
}
