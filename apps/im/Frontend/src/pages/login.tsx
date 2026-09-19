import {nativeFetch as fetch} from '../benchmark/bridge';
import React, { useState } from 'react';
import { Button, Form, Input, Card, message, Tabs, Typography } from 'antd';
import UserOutlined from '@ant-design/icons/UserOutlined';
import LockOutlined from '@ant-design/icons/LockOutlined';
import MailOutlined from '@ant-design/icons/MailOutlined';
import Head from 'next/head';
import { useRouter } from 'next/router';

const { Text, Title } = Typography;

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: 'calc(100vh - 24px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    background: 'linear-gradient(135deg, #ecf8ff 0%, #f8f5ff 46%, #d9efff 100%)',
  },
  shell: {
    width: 'min(1040px, 92vw)',
    minHeight: 640,
    display: 'grid',
    gridTemplateColumns: '1.08fr 0.92fr',
    borderRadius: 28,
    overflow: 'hidden',
    background: 'rgba(255, 255, 255, 0.72)',
    boxShadow: '0 30px 80px rgba(32, 112, 198, 0.18)',
    border: '1px solid rgba(255, 255, 255, 0.78)',
    backdropFilter: 'blur(18px)',
  },
  hero: {
    position: 'relative',
    padding: '56px 56px',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    background: 'linear-gradient(160deg, #11a8ff 0%, #3dc7ff 42%, #8ce3ff 100%)',
    color: '#ffffff',
    transition: 'background 0.18s ease-out',
  },
  heroGlow: {
    position: 'absolute',
    width: 260,
    height: 260,
    right: -64,
    top: 64,
    borderRadius: '50%',
    background: 'rgba(255, 255, 255, 0.22)',
  },
  heroTitle: {
    margin: 0,
    color: '#ffffff',
    fontSize: 42,
    lineHeight: 1.16,
    letterSpacing: 0,
  },
  heroText: {
    maxWidth: 360,
    marginTop: 18,
    color: 'rgba(255, 255, 255, 0.84)',
    fontSize: 16,
    lineHeight: 1.8,
  },
  bubbleStage: {
    position: 'relative',
    height: 250,
  },
  bubble: {
    position: 'absolute',
    padding: '14px 18px',
    borderRadius: 18,
    color: '#1f2d3d',
    background: 'rgba(255, 255, 255, 0.88)',
    boxShadow: '0 18px 36px rgba(17, 107, 188, 0.18)',
    transition: 'transform 0.18s ease-out',
  },
  blueBubble: {
    right: 18,
    top: 34,
    color: '#ffffff',
    background: 'linear-gradient(135deg, #2ab5ff, #0b8cff)',
  },
  whiteBubble: {
    left: 16,
    top: 116,
  },
  avatarOrb: {
    position: 'absolute',
    right: 94,
    bottom: 20,
    width: 78,
    height: 78,
    borderRadius: '50%',
    background: 'rgba(255, 255, 255, 0.28)',
    border: '1px solid rgba(255, 255, 255, 0.38)',
    transition: 'transform 0.18s ease-out',
  },
  formSide: {
    padding: '52px 48px',
    display: 'flex',
    alignItems: 'center',
    background: 'rgba(255, 255, 255, 0.9)',
  },
  card: {
    width: '100%',
    border: 'none',
    boxShadow: 'none',
    background: 'transparent',
    transition: 'transform 0.18s ease, filter 0.18s ease',
  },
  cardHover: {
    transform: 'translateY(-2px)',
    filter: 'drop-shadow(0 18px 32px rgba(54, 129, 210, 0.12))',
  },
  cardTitle: {
    marginBottom: 6,
    color: '#172033',
    fontSize: 28,
  },
  cardSub: {
    display: 'block',
    marginBottom: 28,
    color: '#7b8ba1',
  },
  input: {
    height: 46,
    borderRadius: 14,
    background: '#f4f8fd',
    transition: 'border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease',
  },
  inputFocus: {
    background: '#ffffff',
    borderColor: '#22aaff',
    boxShadow: '0 0 0 4px rgba(34, 170, 255, 0.14)',
  },
  primaryButton: {
    height: 46,
    borderRadius: 14,
    fontWeight: 600,
    background: 'linear-gradient(135deg, #22b7ff, #0a8cff)',
    border: 'none',
    boxShadow: '0 12px 24px rgba(10, 140, 255, 0.24)',
    transition: 'transform 0.16s ease, box-shadow 0.16s ease, filter 0.16s ease',
  },
  primaryButtonHover: {
    transform: 'translateY(-1px)',
    filter: 'brightness(1.04)',
    boxShadow: '0 16px 28px rgba(10, 140, 255, 0.3)',
  },
};

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('login'); 
  const [focusedField, setFocusedField] = useState<string | undefined>(undefined);
  const [mousePoint, setMousePoint] = useState({ x: 68, y: 38 });
  const [buttonHover, setButtonHover] = useState(false);
  const [cardHover, setCardHover] = useState(false);
  const [form] = Form.useForm(); 

  const [countdown, setCountdown] = useState(0);
  const [sendingCode, setSendingCode] = useState(false);

  React.useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const parallaxX = (mousePoint.x - 50) / 50;
  const parallaxY = (mousePoint.y - 50) / 50;
  const heroStyle = {
    ...styles.hero,
    background: `radial-gradient(circle at ${mousePoint.x}% ${mousePoint.y}%, rgba(255,255,255,0.42), rgba(255,255,255,0.06) 28%, transparent 46%), linear-gradient(160deg, #11a8ff 0%, #3dc7ff 42%, #8ce3ff 100%)`,
  };
  const getInputStyle = (field: string) => ({
    ...styles.input,
    ...(focusedField === field ? styles.inputFocus : undefined),
  });
  const buttonStyle = {
    ...styles.primaryButton,
    ...(buttonHover ? styles.primaryButtonHover : undefined),
  };

  // 新增：发送验证码逻辑
  const handleSendCode = async () => {
    try {
      await form.validateFields(['email']);
      const email = form.getFieldValue('email');

      setSendingCode(true);
      const response = await fetch('/api/auth/register/code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      let data: any;
      try { 
        data = await response.json(); 
      } catch { 
        message.error('服务器响应异常，请检查后端运行状态');
        return; 
      }

      if (response.ok && data.code === 0) {
        message.success('验证码已发送，请查收邮箱！');
        setCountdown(60); 
      } else {
        message.error(`发送失败: ${data.info || '未知错误'}`);
      }
    } catch (error: any) {
      if (error.errorFields) return;
      console.error('发送验证码异常:', error);
      message.error('网络请求异常，请检查后端服务！');
    } finally {
      setSendingCode(false);
    }
  };



  const handleLogin = async (values: any) => {
    setLoading(true);
    try {
      const payload = {
        username: values.username,
        password: values.password,
      };

      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      let data;
      try { data = await response.json(); } catch { throw new Error('服务器响应格式错误'); }

      if (response.ok) {
        message.success('登录成功！');
        if (data.token || data.access) {
          localStorage.setItem('token', data.token || data.access);
        }
        localStorage.setItem('username', values.username);
        if (typeof data.user_id === 'number') {
          localStorage.setItem('user_id', String(data.user_id));
        }
        router.push('/');
      } else if (response.status === 401 || response.status === 403 || response.status === 404) {
        message.error('用户名或密码错误，请重新输入！');
      } else {
        message.error(`登录失败: ${data.message || data.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('网络请求异常:', error);
      message.error('网络错误，请检查后端服务是否启动！');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (values: any) => {
    setLoading(true);
    try {
      const payload = {
        username: values.username,
        email: values.email,
        password: values.password,
        verification_code: values.verification_code, // 新增验证码字段对接后端
      };

      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      // 这里修复了你之前的 Bug，用 UI 提示替代 throw Error
      let data: any;
      try { 
        data = await response.json(); 
      } catch { 
        message.error('服务器响应异常（HTML/非JSON）'); 
        return;
      }

      if (response.ok && (data.code === 0 || !data.code)) { // 兼容 data.code 判断
        message.success('注册成功！请登录。');
        form.resetFields(); 
        setActiveTab('login'); 
      } else {
        message.error(`注册失败: ${data.info || data.message || '未知错误'}`);
      }
    } catch (error) {
      console.error('网络请求异常:', error);
      message.error('网络错误，请检查后端服务是否启动！');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Head>
        <title>登录 / 注册 - IM System</title>
      </Head>

      <div style={styles.page}>
        <div style={styles.shell}>
          <section
            style={heroStyle}
            onMouseMove={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              setMousePoint({
                x: Math.round(((event.clientX - rect.left) / rect.width) * 100),
                y: Math.round(((event.clientY - rect.top) / rect.height) * 100),
              });
            }}
          >
            <div style={styles.heroGlow} />
            <div>
              <Title style={styles.heroTitle}>IM System</Title>
              <Text style={styles.heroText}>
                轻快、清晰的即时通讯体验，让消息、联系人和协作回到一个舒适的窗口里。
              </Text>
            </div>
            <div style={styles.bubbleStage}>
              <div style={{ ...styles.bubble, ...styles.blueBubble, transform: `translate(${parallaxX * -10}px, ${parallaxY * -8}px)` }}>今天项目进展同步一下？</div>
              <div style={{ ...styles.bubble, ...styles.whiteBubble, transform: `translate(${parallaxX * 8}px, ${parallaxY * 6}px)` }}>可以，我已经准备好了。</div>
              <div style={{ ...styles.avatarOrb, transform: `translate(${parallaxX * 14}px, ${parallaxY * 10}px)` }} />
            </div>
          </section>

          <section style={styles.formSide}>
            <Card
              style={{ ...styles.card, ...(cardHover ? styles.cardHover : undefined) }}
              onMouseEnter={() => setCardHover(true)}
              onMouseLeave={() => setCardHover(false)}
            >
              <Title level={2} style={styles.cardTitle}>欢迎回来</Title>
              <Text style={styles.cardSub}>登录后继续你的会话</Text>
          <Tabs 
            activeKey={activeTab} 
            onChange={(key) => setActiveTab(key)} 
            centered
            items={[
              {
                key: 'login',
                label: '系统登录',
                children: (
                  <Form name="login_form" layout="vertical" onFinish={handleLogin}>
                    <Form.Item
                      label="用户名"
                      name="username"
                      rules={[{ required: true, message: '请输入用户名！' }]}
                    >
                      <Input
                        prefix={<UserOutlined />}
                        placeholder="请输入用户名"
                        size="large"
                        style={getInputStyle('loginUsername')}
                        onFocus={() => setFocusedField('loginUsername')}
                        onBlur={() => setFocusedField(undefined)}
                      />
                    </Form.Item>

                    <Form.Item
                      label="密码"
                      name="password"
                      rules={[{ required: true, message: '请输入密码！' }]}
                    >
                      <Input.Password
                        prefix={<LockOutlined />}
                        placeholder="请输入密码"
                        size="large"
                        style={getInputStyle('loginPassword')}
                        onFocus={() => setFocusedField('loginPassword')}
                        onBlur={() => setFocusedField(undefined)}
                      />
                    </Form.Item>

                    <Form.Item>
                      <Button
                        type="primary"
                        htmlType="submit"
                        size="large"
                        block
                        loading={loading && activeTab === 'login'}
                        style={buttonStyle}
                        onMouseEnter={() => setButtonHover(true)}
                        onMouseLeave={() => setButtonHover(false)}
                      >
                        登 录
                      </Button>
                    </Form.Item>
                  </Form>
                ),
              },
              {
                key: 'register',
                label: '注册账号',
                children: (
                  <Form form={form} name="register_form" layout="vertical" onFinish={handleRegister}>
                    <Form.Item
                      label="用户名"
                      name="username"
                      validateTrigger="onChange"
                      rules={[
                        { required: true, message: '请输入用户名！' },
                        { max: 50, message: '长度不能超过50个字符！' }
                        ,{
                          validator: (_, value) => {
                            if (!value || !/\s/.test(value)) return Promise.resolve();
                            return Promise.reject(new Error('用户名不合法：不能包含空格'));
                          },
                        }
                      ]}
                    >
                      <Input
                        prefix={<UserOutlined />}
                        placeholder="请输入用户名"
                        size="large"
                        style={getInputStyle('registerUsername')}
                        onFocus={() => setFocusedField('registerUsername')}
                        onBlur={() => setFocusedField(undefined)}
                      />
                    </Form.Item>

                    <Form.Item
                      label="邮箱"
                      name="email"
                      rules={[
                        { required: true, message: '请输入邮箱！' },
                        { type: 'email', message: '请输入有效的邮箱地址！' }
                      ]}
                    >
                      <Input
                        prefix={<MailOutlined />}
                        placeholder="请输入有效的邮箱地址"
                        size="large"
                        style={getInputStyle('registerEmail')}
                        onFocus={() => setFocusedField('registerEmail')}
                        onBlur={() => setFocusedField(undefined)}
                      />
                    </Form.Item>
                    
                    <Form.Item
                      label="验证码"
                      name="verification_code"
                      rules={[
                        { required: true, message: '请输入验证码！' },
                        { len: 6, message: '验证码必须是6位数字！' },
                        { pattern: /^\d{6}$/, message: '验证码只能包含数字！' }
                      ]}
                    >
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <Input
                          placeholder="请输入6位验证码"
                          size="large"
                          maxLength={6}
                          style={{ ...getInputStyle('verificationCode'), flex: 1 }}
                          onFocus={() => setFocusedField('verificationCode')}
                          onBlur={() => setFocusedField(undefined)}
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

                    <Form.Item
                      label="密码"
                      name="password"
                      rules={[
                        { required: true, message: '请输入密码！' },
                        { min: 6, message: '密码至少需要6个字符！' }
                      ]}
                    >
                      <Input.Password
                        prefix={<LockOutlined />}
                        placeholder="请输入至少6位密码"
                        size="large"
                        style={getInputStyle('registerPassword')}
                        onFocus={() => setFocusedField('registerPassword')}
                        onBlur={() => setFocusedField(undefined)}
                      />
                    </Form.Item>

                    <Form.Item
                      label="确认密码"
                      name="confirmPassword"
                      dependencies={['password']}
                      rules={[
                        { required: true, message: '请再次输入密码！' },
                        ({ getFieldValue }) => ({
                          validator(_, value) {
                            if (!value || getFieldValue('password') === value) {
                              return Promise.resolve();
                            }
                            return Promise.reject(new Error('两次输入的密码不一致！'));
                          },
                        }),
                      ]}
                    >
                      <Input.Password
                        prefix={<LockOutlined />}
                        placeholder="请再次确认密码"
                        size="large"
                        style={getInputStyle('confirmPassword')}
                        onFocus={() => setFocusedField('confirmPassword')}
                        onBlur={() => setFocusedField(undefined)}
                      />
                    </Form.Item>

                    <Form.Item>
                      <Button
                        type="primary"
                        htmlType="submit"
                        size="large"
                        block
                        loading={loading && activeTab === 'register'}
                        style={buttonStyle}
                        onMouseEnter={() => setButtonHover(true)}
                        onMouseLeave={() => setButtonHover(false)}
                      >
                        注 册
                      </Button>
                    </Form.Item>
                  </Form>
                ),
              },
            ]}
          />
            </Card>
          </section>
        </div>
      </div>
    </>
  );
}
