import {useState} from 'react';
import {Frame, PageHead, Notice, type ProductAPI} from './kit';
import './communications-documents.css';

export function CommunicationsDocuments({api}:{api:ProductAPI}) {
  const {s,d}=api,w=s.world;
  const [page,setPage]=useState('home'),[project,setProject]=useState(new URLSearchParams(location.search).get('project')||w.projects[0].id);
  const [file,setFile]=useState(''),[group,setGroup]=useState('');
  const active=w.projects.find((p:any)=>p.id===project)||w.projects[0];
  const save=(op:string,target='',data:any={})=>api.mutate(op,target,JSON.stringify(data));
  const chat=(query:Record<string,string>={})=>api.applicationLink?.('chat',query);
  const title=s.task_id===11?'项目资料库':s.task_id===13?'班次交接文档':'项目启动简报';
  return <Frame brand="VIC Studio" accent="#7564a6" page={page} navigate={setPage}
    tabs={[["home","工作台"],["documents",title]]}
    tools={<a href={api.applicationLink?.(s.app)}>返回 {s.app==='im'?'VIC IM':'VIC Chat'} ↗</a>}>
    <main className="product-main"><Notice api={api}/>
      {page==='home'?<><PageHead eyebrow="PROJECT DOCUMENTS" title="让资料跟上项目。" description="整理源文件、班次交接和团队启动资料。"/>
        <div className="studio-projects">{w.projects.map((p:any)=><button key={p.id} onClick={()=>{setProject(p.id);setFile('');setPage('documents')}}><span>▤</span><h3>{p.name}</h3><p>{p.id} · {title}</p></button>)}</div>
        <section className="comm-doc-brief"><h2>团队委托</h2><p>{w.brief}</p></section>
      </>:<><PageHead eyebrow="TEAM WORKSPACE" title={title} description={w.brief}/>
        <div className="comm-doc-layout"><aside aria-label="项目"><h3>项目目录</h3>{w.projects.map((p:any)=><button key={p.id} aria-pressed={project===p.id} onClick={()=>{setProject(p.id);setFile('');setGroup('')}}>{p.name}<small>{p.id}</small></button>)}</aside>
          <section className="comm-doc-content">
            {s.task_id===11?<><h2>{active.name} · 原文件</h2><p>按请求核对项目、类型及版本，再按视频规则选文件。导入后可在 Chat 的附件窗口发送原文件。</p>
              <div className="comm-doc-files">{s.items.filter((x:any)=>x.project===active.id).map((item:any)=><button key={item.id} data-file-id={item.id} aria-pressed={file===item.id} onClick={()=>setFile(item.id)}><b>{item.name}</b><span>{item.file_type} · {item.version} · {item.size} 字节</span><small>{item.record_code}{d.files[item.id]?' · 已导入 Chat':''}</small></button>)}</div>
              {file&&<section className="comm-doc-preview"><h3>文件内容</h3><pre>{s.items.find((x:any)=>x.id===file)?.file_text}</pre><button className="product-primary" disabled={api.busy} onClick={()=>save('document.import',file)}>导入 Chat 附件</button></section>}
              <p><a href={chat({open:String(active.request_conversation)})}>返回请求人的会话 ↗</a></p>
            </>:s.task_id===13?<><h2>{active.name} · 交接事项</h2><p>查阅原消息及处理记录，选择本班需要交接的事项；历史消息仍可查阅。</p>
              {s.items.filter((x:any)=>x.project===active.id).map((item:any)=>{const obj=d.objects[item.id],row=w.handover.rows[item.id];return <article className="comm-doc-message" key={item.id} data-message-id={item.id}>
                <a href={chat({open:String(item.conversation),msg:String(item.message_id)})}>{item.record_code} · 查看原消息 ↗</a><p>{item.text}</p><small>实际状态：{obj.archived?'已归档':obj.starred?'已收藏':d.messages.some((m:any)=>m.reference===item.id)?'已转发':'待处理'}</small>
                {row?<div className="comm-doc-fields"><label>交接处理结果<select aria-label={'交接结果 '+item.record_code} disabled={api.busy||w.handover.sent} value={row.status} onChange={e=>save('handover.line',item.id,{status:e.target.value})}>{['待处理','已转发','已收藏','已归档'].map(x=><option key={x}>{x}</option>)}</select></label><button disabled={api.busy||w.handover.sent} onClick={()=>save('handover.remove',item.id)}>移出清单</button></div>:<button disabled={api.busy||w.handover.sent} onClick={()=>save('handover.line',item.id,{status:'待处理'})}>加入交接清单</button>}
              </article>})}
              <section className="comm-doc-preview"><h3>整班交接清单 · {Object.keys(w.handover.rows).length} 项</h3>{Object.values(w.handover.rows).map((row:any)=><p key={row.message}>{row.task_number} · {row.project} · {row.status}</p>)}<button className="product-primary" disabled={api.busy||w.handover.sent||!Object.keys(w.handover.rows).length} onClick={()=>save('handover.save')}>保存交接文档</button><p><a href={chat()}>返回 Chat 发送文档 ↗</a></p></section>
            </>:<><h2>{active.name} · 启动资料</h2><pre className="comm-doc-preview">{active.material_text}</pre><p>项目简报需包含正确工作群的公告和实际成员账号。先在 IM 建群并填写公告，再选择对应群编制文档。</p>
              <label>关联工作群<select aria-label="简报关联工作群" value={group} onChange={e=>setGroup(e.target.value)}><option value="">选择已创建的工作群</option>{Object.values(w.groups).map((g:any)=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
              {group&&w.groups[group]&&<section className="comm-doc-preview"><h3>{w.groups[group].name}</h3><p>{w.groups[group].announcement||'尚未填写公告'}</p>{w.groups[group].members.map((id:string)=>{const p=s.items.find((x:any)=>x.id===id);return <p key={id}>{p?.name} · {p?.account}</p>})}</section>}
              <button className="product-primary" disabled={api.busy||!group} onClick={()=>save('project.brief',active.id,{group})}>保存项目简报</button>
              {w.documents['brief-'+active.id]&&<section className="comm-doc-preview"><h3>已保存简报</h3><pre>{w.documents['brief-'+active.id].body}</pre><p>群内分享入口：{active.material_link}</p></section>}
              <p><a href={api.applicationLink?.('im')}>返回 IM 发布到项目群 ↗</a></p>
            </>}
          </section>
        </div>
      </>}
    </main>
  </Frame>;
}
