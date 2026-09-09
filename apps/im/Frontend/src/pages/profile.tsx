import React, { useEffect, useState } from 'react';
import { Form, Input, Button, message, Spin, Divider, Space, Typography, Modal, Upload } from 'antd';
import {
  UserOutlined,
  MailOutlined,
  PhoneOutlined,
  LockOutlined,
  LogoutOutlined,
  DeleteOutlined,
  UploadOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import Head from 'next/head';
import { useRouter } from 'next/router';

const { Title, Text } = Typography;

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: 'calc(100vh - 24px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 28,
    background: 'linear-gradient(135deg, #f6fbff 0%, #eef5ff 48%, #dcf1ff 100%)',
  },
  shell: {
    width: 'min(1040px, 94vw)',
    minHeight: 660,
    display: 'grid',
    gridTemplateColumns: '310px 1fr',
    overflow: 'hidden',
    borderRadius: 28,
    background: 'rgba(255, 255, 255, 0.82)',
    border: '1px solid rgba(255, 255, 255, 0.88)',
    boxShadow: '0 28px 72px rgba(38, 125, 208, 0.15)',
  },
  side: {
    padding: 34,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    color: '#ffffff',
    background: 'linear-gradient(180deg, #18afff 0%, #078cf0 100%)',
  },
  avatarWrap: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: 16,
  },
  avatar: {
    width: 86,
    height: 86,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '50%',
    background: 'rgba(255, 255, 255, 0.22)',
    boxShadow: '0 18px 38px rgba(0, 104, 190, 0.22)',
    overflow: 'hidden', // 确保图片变圆
  },
  avatarImg: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },
  sideTitle: {
    margin: '12px 0 6px',
    color: '#ffffff',
    letterSpacing: 0,
  },
  sideText: {
    color: 'rgba(255, 255, 255, 0.82)',
    lineHeight: 1.7,
  },
  sideCard: {
    padding: 18,
    borderRadius: 20,
    background: 'rgba(255, 255, 255, 0.18)',
    boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.22)',
  },
  main: {
    padding: '36px 42px',
    background: '#ffffff',
  },
  mainHeader: {
    marginBottom: 26,
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 16,
  },
  backButton: {
    borderRadius: 12,
    flexShrink: 0,
  },
  input: {
    height: 44,
    borderRadius: 14,
    background: '#f5f9fe',
  },
  primaryButton: {
    height: 46,
    borderRadius: 14,
    fontWeight: 600,
    background: 'linear-gradient(135deg, #22b7ff, #0a8cff)',
    border: 'none',
    boxShadow: '0 12px 24px rgba(10, 140, 255, 0.2)',
  },
  securityNote: {
    display: 'block',
    marginBottom: 16,
    padding: '12px 14px',
    borderRadius: 14,
    color: '#5b6b82',
    background: '#f4f8fd',
    fontSize: 12,
    lineHeight: 1.7,
  },
  dangerButton: {
    borderRadius: 12,
  },
  logoutButton: {
    borderRadius: 12,
  },
};

export default function ProfilePage() {
  const router = useRouter();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [initialData, setInitialData] = useState<any>({});
  
  // 新增：头像处理状态
  const [avatarUrl, setAvatarUrl] = useState<string | undefined>(undefined);

  // 新增：验证码处理状态
  const [countdown, setCountdown] = useState(0);
  const [sendingCode, setSendingCode] = useState(false);
  
  // 监听表单邮箱字段的变化
  const currentEmail = Form.useWatch('email', form);
  const isEmailChanged = currentEmail && initialData.email && currentEmail !== initialData.email;

  // 倒计时逻辑
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  // 1. 获取个人信息
  useEffect(() => {
    const fetchProfile = async () => {
      const token = localStorage.getItem('token');
      if (!token) {
        message.warning('请先登录！');
        router.push('/login');
        return;
      }

      try {
        const response = await fetch('/api/user/profile', {
          method: 'GET',
          headers: { 'Authorization': `Bearer ${token}` },
        });

        const data = await response.json();

        if (response.status === 401 || data.code === -1) {
          message.error('登录已过期，请重新登录');
          localStorage.clear();
          router.push('/login');
          return;
        }

        if (data.code === 0) {
          setInitialData(data);
          // 渲染已有头像
          if (data.avatar) setAvatarUrl(data.avatar);
          
          form.setFieldsValue({
            username: data.username,
            email: data.email,
            phone: data.phone || '',
          });
        } else {
          message.error(data.info || '获取个人信息失败');
        }
      } catch {
        message.error('网络错误，无法连接到服务器');
      } finally {
        setLoading(false);
      }
    };

    fetchProfile();
  }, [form, router]);

  // 新增：本地头像选择转 Base64
  const handleAvatarChange = (info: any) => {
    const file = info.file.originFileObj || info.file;
    if (!file) return;

    const isJpgOrPng = file.type === 'image/jpeg' || file.type === 'image/png';
    if (!isJpgOrPng) {
      message.error('只能上传 JPG 或 PNG 格式的图片！');
      return;
    }
    const isLt2M = file.size / 1024 / 1024 < 2;
    if (!isLt2M) {
      message.error('图片必须小于 2MB！');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      setAvatarUrl(e.target?.result as string);
    };
    reader.readAsDataURL(file);
  };

  // 新增：发送换绑邮箱验证码
  const handleSendCode = async () => {
    try {
      await form.validateFields(['email']);
      const email = form.getFieldValue('email');

      setSendingCode(true);
      // 注意：此处复用发送验证码接口，如果后端有专属的修改邮箱发码接口，请修改此处 URL
      const response = await fetch('/api/auth/register/code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      let data: any;
      try { data = await response.json(); } catch { 
        message.error('服务器响应异常'); 
        return; 
      }

      if (response.ok && data.code === 0) {
        message.success('验证码已发送至新邮箱，请查收！');
        setCountdown(60); 
      } else {
        message.error(`发送失败: ${data.info || '未知错误'}`);
      }
    } catch (error: any) {
      if (error.errorFields) return;
      message.error('网络请求异常');
    } finally {
      setSendingCode(false);
    }
  };

  // 2. 更新个人信息
  const handleUpdateProfile = async (values: any) => {
    setSaving(true);
    const token = localStorage.getItem('token');

    const payload: any = {};
    if (values.username && values.username !== initialData.username) payload.username = values.username;
    if (values.phone && values.phone !== initialData.phone) payload.phone = values.phone;
    if (values.new_password) payload.new_password = values.new_password;
    if (values.old_password) payload.old_password = values.old_password;
    
    // 如果修改了邮箱，附加新邮箱和验证码
    if (isEmailChanged) {
      payload.email = values.email;
      payload.verification_code = values.verification_code;
    }

    // 如果修改了头像，附加头像 Base64
    if (avatarUrl && avatarUrl !== initialData.avatar) {
      payload.avatar = avatarUrl;
    }

    if (Object.keys(payload).length === 0) {
      message.info('未做任何修改');
      setSaving(false);
      return;
    }

    try {
      const response = await fetch('/api/user/profile', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (data.code === 0) {
        message.success('个人信息更新成功！');
        form.setFieldValue('old_password', '');
        form.setFieldValue('new_password', '');
        form.setFieldValue('verification_code', '');
        
        if (payload.username) {
          localStorage.setItem('username', payload.username);
        }
        setInitialData({ ...initialData, ...payload });
      } else if (data.code === 2) {
        message.error('原密码错误，修改认证信息失败！');
      } else if (data.code === 1) {
        message.error('该用户名已被占用！');
      } else {
        message.error(`更新失败: ${data.info}`);
      }
    } catch {
      message.error('网络错误，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  // 3. 安全退出登录
  const handleLogout = async () => {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
      });
    } catch (e) {
      console.error('Logout error', e);
    } finally {
      localStorage.clear();
      message.success('已安全退出登录');
      router.push('/login');
    }
  };

  // 4. 注销账号
  const handleDeleteAccount = () => {
    Modal.confirm({
      title: '危险操作：注销账号',
      content: (
        <div>
          <p>注销后，您的所有聊天记录、好友关系将永久丢失且不可恢复！</p>
          <Input.Password 
            id="deleteConfirmPassword" 
            placeholder="请输入密码以确认注销" 
            prefix={<LockOutlined />} 
          />
        </div>
      ),
      okText: '确认永久注销',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        const password = (document.getElementById('deleteConfirmPassword') as HTMLInputElement)?.value;
        if (!password) {
          message.error('必须输入密码才能注销账号');
          return Promise.reject();
        }

        try {
          const response = await fetch('/api/auth/delete', {
            method: 'DELETE',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({ password }),
          });
          const data = await response.json();

          if (data.code === 0) {
            message.success('账号已永久注销');
            localStorage.clear();
            router.push('/login');
          } else if (data.code === 2) {
            message.error('密码错误，注销失败');
            return Promise.reject();
          } else {
            message.error(`注销失败: ${data.info}`);
            return Promise.reject();
          }
        } catch {
          message.error('网络错误');
          return Promise.reject();
        }
      }
    });
  };

  return (
    <>
      <Head>
        <title>个人主页 - 即时通讯系统</title>
      </Head>

      <div style={styles.page}>
        <div style={styles.shell}>
          <aside style={styles.side}>
            <div style={styles.avatarWrap}>
              <div style={styles.avatar}>
                {avatarUrl ? (
                  <img src={avatarUrl} alt="Avatar" style={styles.avatarImg} />
                ) : (
                  <UserOutlined style={{ fontSize: 42, color: '#ffffff' }} />
                )}
              </div>
              
              <Upload 
                showUploadList={false} 
                beforeUpload={() => false} // 阻止默认上传动作
                onChange={handleAvatarChange}
              >
                <Button size="small" ghost icon={<UploadOutlined />} style={{ borderRadius: 12 }}>
                  更换头像
                </Button>
              </Upload>

              <div>
                <Title level={2} style={styles.sideTitle}>{initialData.username || '个人资料'}</Title>
                <Text style={styles.sideText}>{initialData.email || '管理你的账号资料与安全设置'}</Text>
              </div>
            </div>
            <div style={styles.sideCard}>
              <Text style={{ color: '#ffffff', fontWeight: 600 }}>账号安全</Text>
              <Text style={{ ...styles.sideText, display: 'block', marginTop: 8 }}>
                修改邮箱、手机号或密码时，需要输入原密码完成验证。
              </Text>
            </div>
          </aside>

          <main style={styles.main}>
            <div style={styles.mainHeader}>
              <div>
                <Title level={3} style={{ margin: 0, color: '#172033' }}>个人资料</Title>
                <Text style={{ color: '#7b8ba1' }}>更新基础信息和账号安全设置</Text>
              </div>
              <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/')} style={styles.backButton}>
                返回聊天
              </Button>
            </div>

          {loading ? (
            <div style={{ textAlign: 'center', padding: '50px 0' }}>
              <Spin description="加载中..." size="large" />
            </div>
          ) : (
            <Form form={form} layout="vertical" onFinish={handleUpdateProfile}>
              <Form.Item label="用户名" name="username" rules={[{ required: true, message: '用户名不能为空！' }]}>
                <Input prefix={<UserOutlined />} size="large" style={styles.input} />
              </Form.Item>

              <Form.Item label="绑定的邮箱" name="email" rules={[{ required: true, message: '邮箱不能为空！' }, { type: 'email', message: '格式不正确！' }]}>
                <Input prefix={<MailOutlined />} size="large" style={styles.input} />
              </Form.Item>

              {/* 动态显示的邮箱验证码区域 */}
              {isEmailChanged ? (
                <Form.Item
                  label="新邮箱验证码"
                  name="verification_code"
                  rules={[
                    { required: true, message: '请输入验证码！' },
                    { len: 6, message: '验证码必须是6位数字！' }
                  ]}
                >
                  <div style={{ display: 'flex', gap: '12px' }}>
                    <Input
                      placeholder="请输入6位验证码"
                      size="large"
                      maxLength={6}
                      style={{ ...styles.input, flex: 1 }}
                    />
                    <Button
                      size="large"
                      onClick={handleSendCode}
                      disabled={countdown > 0}
                      loading={sendingCode}
                      style={{ width: '130px', borderRadius: 14 }}
                    >
                      {countdown > 0 ? `${countdown}s 后重试` : '获取验证码'}
                    </Button>
                  </div>
                </Form.Item>
              ) : undefined}

              <Form.Item label="手机号" name="phone">
                <Input prefix={<PhoneOutlined />} size="large" placeholder="选填，请输入手机号" style={styles.input} />
              </Form.Item>

              <Divider dashed><Text type="secondary">安全验证区</Text></Divider>
              <Text type="secondary" style={styles.securityNote}>
                * 如果您要修改邮箱、手机号或设置新密码，必须在下方输入【原密码】以验证身份。
              </Text>

              <Form.Item label="原密码" name="old_password">
                <Input.Password prefix={<LockOutlined />} size="large" placeholder="修改认证信息必填" style={styles.input} />
              </Form.Item>

              <Form.Item label="新密码" name="new_password">
                <Input.Password prefix={<LockOutlined />} size="large" placeholder="如不修改密码请留空" style={styles.input} />
              </Form.Item>

              <Form.Item>
                <Button type="primary" htmlType="submit" size="large" block loading={saving} style={styles.primaryButton}>
                  保存修改
                </Button>
              </Form.Item>

              <Divider />

              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Button danger type="text" icon={<DeleteOutlined />} onClick={handleDeleteAccount} style={styles.dangerButton}>
                  注销账号
                </Button>
                <Button type="default" icon={<LogoutOutlined />} onClick={handleLogout} style={styles.logoutButton}>
                  退出登录
                </Button>
              </Space>
            </Form>
          )}
          </main>
        </div>
      </div>
    </>
  );
}
