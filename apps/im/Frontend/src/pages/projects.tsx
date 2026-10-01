import {useEffect,useState} from 'react';
import {useRouter} from 'next/router';
import Link from 'next/link';
import Head from 'next/head';
import {Button,Card,Table,Typography,Alert,Spin} from 'antd';
import {nativeFetch as fetch} from '../benchmark/bridge';

export default function Projects(){
  const router=useRouter();
  const [data,setData]=useState<any>();
  const [error,setError]=useState('');
  useEffect(()=>{fetch('/api/projects').then(r=>r.json()).then(r=>{if(r.code!==0)throw Error(r.info);setData(r)}).catch(e=>setError(String(e)))},[]);
  const projects=data?.projects.filter((p:any)=>!router.query.project||p.id===router.query.project)||[];
  return <main style={{minHeight:'100vh',background:'#f3f8fe',padding:'32px max(24px,calc((100vw - 1100px)/2))',color:'#21364c'}}>
    <Head><title>项目通知与资料 · VIC IM</title></Head>
    <header style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:24}}><div><Typography.Text type="secondary">团队协作 / 项目启动</Typography.Text><Typography.Title level={2}>项目通知与资料</Typography.Title></div><Link href="/"><Button>返回消息</Button></Link></header>
    {error&&<Alert type="error" description={error}/>} {!data&&!error&&<Spin/>}
    {projects.map((p:any)=><Card key={p.id} title={p.id+' · '+p.name} style={{marginBottom:24}} extra={<Link href="/group_build">发起群聊</Link>}>
      <Typography.Paragraph>请按视频标准从以下候选中选择三名成员，建立工作群。姓名、账号与所属项目应一一对应；比较使用通知发布时的属性快照，并列按照下表顺序。</Typography.Paragraph>
      <Typography.Paragraph><strong>工作群名称：</strong>{p.group_name}</Typography.Paragraph>
      <Typography.Paragraph copyable={{text:p.announcement}}><strong>群公告：</strong>{p.announcement}</Typography.Paragraph>
      <Table rowKey="account" pagination={false} size="small" dataSource={data.candidates.filter((c:any)=>c.project===p.id)} columns={[
        {title:'姓名',dataIndex:'username'},{title:'成员账号',dataIndex:'account'},
        {title:'初始最近联系时间（UTC）',dataIndex:'last_contact_at',render:(v:string)=>v.replace('T',' ').slice(0,16)},
        {title:'初始未读数',dataIndex:'unread'},
      ]}/>
      <div style={{marginTop:22,padding:20,background:'#f6faff',borderRadius:8}}><Typography.Title level={5}>项目资料 · {p.material}</Typography.Title><pre style={{whiteSpace:'pre-wrap',fontFamily:'inherit',lineHeight:1.9}}>{p.material_text}</pre><Typography.Paragraph copyable={{text:p.material_link}}><strong>分享链接：</strong><a href={p.material_link}>{p.material_link}</a></Typography.Paragraph></div>
    </Card>)}
  </main>;
}
