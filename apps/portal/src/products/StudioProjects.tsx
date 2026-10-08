import { useState } from "react";
import { Frame, PageHead, Notice, type ProductAPI } from "./kit";

const values = (x: any): any[] => Object.values(x);
export function StudioProjects({ api }: { api: ProductAPI }) {
  const { s, d } = api, w = s.world, isConfig = s.task_id === 41;
  const query = new URLSearchParams(location.search);
  const [page, setPage] = useState(query.has('file') ? 'file' : query.has('output') ? 'output' : 'home');
  const [projectId, setProjectId] = useState(w.projects[0].id);
  const [outputId, setOutputId] = useState(query.get('output') || '');
  const [fileId, setFileId] = useState(query.get('file') || '');
  const [error, setError] = useState('');
  const [copyBusy, setCopyBusy] = useState(false);
  const project = w.projects.find((p: any) => p.id === projectId);
  function nav(next: string) { setPage(next);setError('');api.clearNotice?.(); }
  function openProject(id: string) { setProjectId(id);nav('project'); }
  const command = (op: string, target = '', data = {}) => api.mutate(op, target, JSON.stringify(data));
  const link = (q: Record<string,string>) => api.applicationLink?.('studio', q) || '#';
  const person = (id: number) => w.people.find((p: any) => p.id === id)?.name || '';
  const resource = (kind: string, id: string) => w[kind].find((r: any) => r.id === id);
  const label = (kind: string, id: string) => {const r=resource(kind,id);return r ? `${r.name} / ${r.version}` : '未绑定';};
  async function download(id: string) {try {await api.downloadFile?.(id,d.files[id].name);} catch(e) {setError(String(e));}}
  async function copy(item: any) {
    setCopyBusy(true);setError('');
    try {
      await command('output.copy',item.id);
    } catch(e) {setError(String(e));} finally {setCopyBusy(false);}
  }
  function Provenance({config}: {config:any}) {
    return <dl className="studio-provenance"><dt>模型</dt><dd>{d.objects[config.model]?.name}</dd><dt>提示词</dt><dd>{label('templates',config.template)}</dd><dt>输入资料</dt><dd>{label('documents',config.document)}</dd></dl>;
  }
  function ConfigEditor({p}: {p:any}) {
    const current=w.configs[p.id];
    const [model,setModel]=useState(current?.model || '');
    const [template,setTemplate]=useState(current?.template || '');
    const [document,setDocument]=useState(current?.document || '');
    const pending=!current||model!==current.model||template!==current.template||document!==current.document;
    const selectedTemplate=resource('templates',template),selectedDocument=resource('documents',document);
    return <section className="studio-panel">
      <h2>项目配置</h2><p>上下文至少 {p.min_context} K · 模型须在本项目可用名单内。</p>
      <p>本次要求：{label('templates',p.template)}；{label('documents',p.document)}。</p>
      <label>生成模型<select aria-label="生成模型" value={model} onChange={e=>setModel(e.target.value)}><option value="">请选择模型</option>{p.available_models.map((id:string)=>{const m=d.objects[id];return <option key={id} value={id} disabled={m.context<p.min_context}>{m.model_code} · {m.name} · {m.context} K · ¥{m.price} / 百万 token{m.context<p.min_context?'（上下文不足）':''}</option>;})}</select></label>
      <label>提示词模板<select aria-label="提示词模板" value={template} onChange={e=>setTemplate(e.target.value)}><option value="">请选择模板与版本</option>{w.templates.map((r:any)=><option key={r.id} value={r.id}>{r.name} / {r.version}</option>)}</select></label>
      {selectedTemplate&&<blockquote>{selectedTemplate.text}</blockquote>}
      <label>输入资料<select aria-label="输入资料" value={document} onChange={e=>setDocument(e.target.value)}><option value="">请选择资料与版本</option>{w.documents.map((r:any)=><option key={r.id} value={r.id}>{r.name} / {r.version}</option>)}</select></label>
      {selectedDocument&&<ul>{selectedDocument.records.map((line:string,i:number)=><li key={i}>{line}</li>)}</ul>}
      <div className="studio-actions"><button className="product-primary" disabled={api.busy||!model||!template||!document} onClick={()=>command('config.save',p.id,{model,template,document})}>保存项目配置</button><button disabled={api.busy||!current||pending} onClick={()=>command('generation.run',p.id)}>运行生成</button></div>
      <small>{pending?'配置有未保存的内容，请先保存再运行。':'运行使用已保存配置；固定资料按模板逐条整理，可复现相同结果。'}</small>
    </section>;
  }
  function Generation({g}: {g:any}) {
    const [folder,setFolder]=useState(g.project);
    return <article className="studio-panel" data-generation={g.id}><h3>{g.id} · {w.projects.find((p:any)=>p.id===g.project)?.name}</h3><Provenance config={g.config}/><pre className="studio-content-text">{g.body}</pre><label>归档项目<select aria-label="归档项目" value={folder} onChange={e=>setFolder(e.target.value)}>{w.projects.map((p:any)=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><button disabled={api.busy} onClick={()=>command('generation.archive',g.id,{project:folder})}>归档生成结果</button></article>;
  }
  function Output({item}: {item:any}) {
    const p=w.projects.find((p:any)=>p.id===item.project);
    const [recipient,setRecipient]=useState('');
    const check=w.checks[item.id],file=w.saved[item.id],row=w.delivery.rows[item.id],receipts=w.receipts.filter((r:any)=>r.target===item.id);
    return <article className="studio-panel" data-output={item.id}>
      <PageHead eyebrow={item.record_code} title={item.name} description={`${item.project_name} · ${item.batch}`}/>
      <pre className="studio-content-text studio-code-text">{item.code}</pre>
      <div className="studio-actions"><button className="product-primary" disabled={api.busy} onClick={()=>command('output.check',item.id)}>运行语法检查</button><span className={check?.passed?'studio-pass':'studio-fail'} role="status">{check?.message||'尚未检查'}</span></div>
      {p&&<><h3>交付操作</h3><p>项目指定联系人：{person(p.recipient)}。按约定方式交付通过项。</p><div className="studio-actions"><button disabled={api.busy||!check?.passed} onClick={()=>command('output.save',item.id)}>保存文件</button><button disabled={api.busy||copyBusy||!check?.passed} onClick={()=>copy(item)}>{copyBusy?'正在复制…':'复制代码'}</button><label>交付联系人<select aria-label="交付联系人" value={recipient} onChange={e=>setRecipient(e.target.value)}><option value="">请选择联系人</option>{w.people.map((r:any)=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label><button disabled={api.busy||!check?.passed||!recipient} onClick={()=>command('output.send',item.id,{recipient:Number(recipient)})}>发送结果</button></div>
      {file&&<div className="studio-delivery-record"><a href={link({file})}>{d.files[file].name}</a><button disabled={api.busy} onClick={()=>command('delivery.line',item.id,{kind:'saved',reference:'files/'+file})}>将保存文件加入清单</button></div>}
      {w.copies[item.id]&&<div className="studio-delivery-record"><details><summary>查看工作区内已复制的内容</summary><pre>{w.copies[item.id].body}</pre></details><button disabled={api.busy} onClick={()=>command('delivery.paste',item.id,{body:w.copies[item.id].body})}>粘贴到交付清单</button><label>复制交付内容<textarea aria-label="复制交付内容" rows={7} readOnly value={row?.kind==='copied'?row.body:''} placeholder="从本文件已复制的内容粘贴到交付清单"/></label>{row?.kind==='copied'&&<span>{row.body===item.code?'已粘贴完整内容':'粘贴内容与本文件不一致，请重新复制并粘贴。'}</span>}</div>}
      {receipts.map((r:any)=><div className="studio-delivery-record" data-receipt={r.id} key={r.id}><span>{r.id} · 已发送给 {person(r.recipient)}</span><button disabled={api.busy} onClick={()=>command('delivery.line',item.id,{kind:'sent',reference:'receipts/'+r.id})}>将发送回执加入清单</button><a href={api.applicationLink?.('im')}>打开团队消息 →</a></div>)}
      {row&&<p className="studio-pass">已加入交付清单 · {({saved:'文件',copied:'粘贴内容',sent:'发送回执'} as Record<string,string>)[row.kind]}</p>}
      {(file||w.copies[item.id]||receipts.length>0)&&<button disabled={api.busy} onClick={()=>command('output.clear',item.id)}>撤销本项交付</button>}
      <button onClick={()=>nav('delivery')}>查看交付清单</button></>}
    </article>;
  }
  const output=d.objects[outputId];
  const file=d.files[fileId];
  return <Frame brand="VIC Studio" accent="#7564a6" page={page} navigate={nav} tabs={isConfig?[['home','工作台'],['projects','内容项目'],['models','模型库'],['templates','提示词库'],['documents','资料库'],['archives','归档文件']]:[['home','工作台'],['projects','内容项目'],['delivery','交付清单'],['history','历史项目']]} tools={(!isConfig||s.cross_platform)&&<a href={api.applicationLink?.('im')}>团队消息 ↗</a>}>
    <main className="product-main studio-workflows"><Notice api={api}/>{error&&<p role="alert">{error}</p>}
      {page==='home'&&<><PageHead eyebrow="CREATE WITH INTENTION" title="开始一次有条理的创作。" description="管理项目输入，核对生成内容，保存完整的交付记录。"/><div className="studio-start"><span className="studio-spark">✳</span><h2>{isConfig?'让资料与项目配置保持一致':'检查完成，再交付。'}</h2><p>{s.execution.assignment}</p><button onClick={()=>nav('projects')}>打开内容项目</button></div><section className="studio-brief" aria-label="工作范围"><strong>本期工作安排</strong><p>{w.brief}</p></section></>}
      {(page==='home'||page==='projects')&&<><PageHead title="内容项目" description="三个项目 · 本期工作区"/><div className="studio-projects">{w.projects.map((p:any)=><button data-project={p.id} key={p.id} onClick={()=>openProject(p.id)}><span>▤</span><h3>{p.name}</h3><p>{isConfig?`上下文要求 ${p.min_context} K · ${w.configs[p.id]?'已配置':'待配置'}`:`${p.outputs.length} 个输出 · 联系人 ${person(p.recipient)}`}</p></button>)}</div></>}
      {page==='project'&&<><PageHead title={project.name} description={isConfig?'配置输入、运行并归档':'本期输出清单 · 2026-W06'} action={<button onClick={()=>nav('projects')}>所有项目</button>}/>{isConfig?<><ConfigEditor key={project.id} p={project}/><h2>生成历史</h2>{values(w.generations).filter(g=>g.project===project.id).reverse().map(g=><Generation key={g.id} g={g}/>)}{!values(w.generations).some(g=>g.project===project.id)&&<p>保存配置后运行，结果会保留输入版本信息。</p>}</>:<div className="studio-output-list">{project.outputs.map((id:string)=>{const o=d.objects[id];return <button key={id} data-output-link={id} onClick={()=>{setOutputId(id);nav('output');}}><b>{o.name}</b><span>{o.record_code}</span><small>{w.checks[id]?.message||'尚未检查'}{w.delivery.rows[id]?' · 已加入清单':''}</small></button>;})}</div>}</>}
      {page==='output'&&(output?<Output key={output.id} item={output}/>:<p role="alert">生成结果不存在</p>)}
      {page==='models'&&<><PageHead title="模型库" description="上下文单位 K · 人民币 / 百万 token · 名称长度包含空格"/><div className="studio-models">{s.items.map((m:any)=><article key={m.id}><div className="studio-model-logo">◈</div><h2>{m.name}</h2><p>{m.model_code}</p><dl><dt>上下文</dt><dd>{m.context} K</dd><dt>价格</dt><dd>¥{m.price}</dd><dt>名称长度</dt><dd>{m.name_length}</dd></dl><p>可用项目：{w.projects.filter((p:any)=>p.available_models.includes(m.id)).map((p:any)=>p.name).join('、')||'不在本期项目名单'}</p></article>)}</div></>}
      {(page==='templates'||page==='documents')&&<><PageHead title={page==='templates'?'提示词库':'资料库'} description="选择项目要求的版本；历史版本保留备查。"/>{w[page].map((r:any)=><article className="studio-panel" key={r.id}><h2>{r.name} / {r.version}</h2>{r.text?<p>{r.text}</p>:<ul>{r.records.map((text:string,i:number)=><li key={i}>{text}</li>)}</ul>}</article>)}</>}
      {page==='archives'&&<><PageHead title="归档文件" description="归档保留生成内容及其输入配置。"/>{!values(w.archives).length&&<p>还没有归档文件。</p>}{values(w.archives).map(a=><article className="studio-panel" data-archive={a.id} key={a.id}><h2>{w.projects.find((p:any)=>p.id===a.project)?.name}</h2><Provenance config={a.config}/><div className="studio-actions"><a href={link({file:a.file})}>{d.files[a.file]?.name}</a><button onClick={()=>download(a.file)}>下载文件</button><button disabled={api.busy} onClick={()=>command('archive.remove',a.id)}>移除归档</button></div></article>)}</>}
      {page==='file'&&(file?<article className="studio-panel"><PageHead title={file.name} description={`${file.size} 字节`} action={<button onClick={()=>download(fileId)}>下载文件</button>}/><pre className="studio-content-text">{new TextDecoder().decode(Uint8Array.from(atob(file.content),(c)=>c.charCodeAt(0)))}</pre></article>:<p role="alert">文件不存在或已移除</p>)}
      {page==='delivery'&&<><PageHead title="生成结果交付清单" description="逐项关联真实文件、粘贴内容或发送回执，再保存清单。"/>{w.projects.map((p:any)=><section className="studio-panel" key={p.id}><h2>{p.name}</h2><p>联系人：{person(p.recipient)}</p>{p.outputs.filter((id:string)=>w.delivery.rows[id]).map((id:string)=>{const row=w.delivery.rows[id],item=d.objects[id];return <article className="studio-manifest-row" key={id} data-delivery={id}><b>{item.record_code} · {item.name}</b><p>方式：{({saved:'保存文件',copied:'复制交付',sent:'发送结果'} as Record<string,string>)[row.kind]} · {row.reference}</p>{row.kind==='saved'?<a href={link({file:row.reference.slice(6)})}>查看交付文件</a>:row.kind==='copied'?<pre className="studio-content-text">{row.body}</pre>:<a href={api.applicationLink?.('im')}>查看团队消息</a>}<div className="studio-actions"><a href={link({output:id})}>查看源结果</a><button disabled={api.busy} onClick={()=>command('delivery.remove',id)}>移出清单</button></div></article>;})}{!p.outputs.some((id:string)=>w.delivery.rows[id])&&<p>尚未加入交付记录。</p>}</section>)}<div className="studio-actions"><button className="product-primary" disabled={api.busy||!Object.keys(w.delivery.rows).length} onClick={()=>command('delivery.save')}>保存交付清单</button>{d.files['delivery-manifest']&&<><a href={link({file:'delivery-manifest'})}>打开清单文件</a><button onClick={()=>download('delivery-manifest')}>下载交付清单</button></>}</div><p role="status">{JSON.stringify(w.delivery.saved)===JSON.stringify(w.delivery.rows)?'清单已保存':'清单尚未保存，或有未保存的变更。'}</p></>}
      {page==='history'&&<><PageHead title="历史项目" description="历史输出供查阅，不属于本期交付范围。"/>{s.items.filter((o:any)=>o.project==='historical').map((o:any)=><button key={o.id} onClick={()=>{setOutputId(o.id);nav('output');}}>{o.record_code} · {o.name} · {o.batch}</button>)}</>}
    </main>
  </Frame>;
}
