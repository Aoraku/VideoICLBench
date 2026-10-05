/* Native application's editable business correspondence and document module. */
(() => {
  window.VICWorksetWorkspace = {
    mount({run, headers, envelope}) {
      if (!envelope.state?.workset_delivery || document.getElementById('vic-business-documents')) return;
      let latest=envelope, tab='inbox', busy=false, formValues=null, rowValues={object:'',reference:'',detail:''};
      const host=document.createElement('div');host.id='vic-business-documents';
      const root=host.attachShadow({mode:'open'});
      const style=document.createElement('style');style.textContent=`
        :host{font:14px system-ui;color:#24344a}*{box-sizing:border-box}button,input,select,textarea{font:inherit}button{cursor:pointer;border:1px solid #d2dbe6;border-radius:7px;background:white;color:#24344a;padding:9px 13px}button:hover{background:#f2f6fa}button:disabled{opacity:.5;cursor:wait}.launcher{position:fixed;bottom:16px;left:18px;z-index:2147483000;background:#1f574b;color:white;border:0;box-shadow:0 3px 14px #0002}dialog{position:fixed;inset:4vh 4vw;width:min(1140px,92vw);height:90vh;border:1px solid #dbe3eb;border-radius:16px;padding:0;color:#24344a;background:#f8fafc;z-index:2147483500}dialog::backdrop{background:#14233770}.head{display:flex;align-items:center;justify-content:space-between;padding:20px 28px;background:white;border-bottom:1px solid #dbe3eb}.head h2{font-size:20px;margin:0}.nav{display:flex;gap:6px;padding:14px 24px;background:white}.nav button[aria-selected=true]{background:#e8f1ed;border-color:#94b7a9;color:#205442}.body{padding:22px 28px;height:calc(100% - 150px);overflow:auto}article,.panel{background:white;border:1px solid #dbe3eb;border-radius:10px;padding:20px;margin-bottom:16px}h3{margin:0 0 12px;font-size:17px}p{line-height:1.65}.meta{color:#60758a;font-size:13px;white-space:pre-wrap}.fields{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;color:#536a7d;font-size:13px}input,select,textarea{display:block;width:100%;margin-top:6px;padding:10px;border:1px solid #cdd7e2;border-radius:6px;background:white;color:#23394c}textarea{min-height:78px;resize:vertical}.wide{grid-column:1/-1}.primary{background:#1f574b;color:white;border:0}.primary:hover{background:#17483d;color:white}.actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}.error{color:#a32c2c;white-space:pre-wrap}.status{color:#2c6d4e;white-space:pre-wrap}table{border-collapse:collapse;width:100%;background:white}th,td{padding:12px;text-align:left;border-bottom:1px solid #e1e6ed;vertical-align:top}th{background:#f0f4f8}pre{white-space:pre-wrap;font:14px/1.7 system-ui;background:white;padding:18px;border:1px solid #dbe3eb;border-radius:8px}.small{padding:4px 8px}a{color:#245c82}
      `;root.append(style);
      const button=(text,fn,cls='')=>{const b=document.createElement('button');b.textContent=text;b.className=cls;b.onclick=fn;return b;};
      const el=(tag,text,cls='')=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;e.className=cls;return e;};
      const dialog=document.createElement('dialog');dialog.setAttribute('aria-label',envelope.state.workset_delivery.title);const launcher=button(envelope.state.workset_delivery.title,async()=>{render();dialog.showModal();try{await refresh();render();}catch(error){showError(error);}},'launcher');
      root.append(launcher,dialog);document.body.append(host);
      function showError(error){const box=el('p',error.message||'读取失败，请重试','error');box.setAttribute('role','alert');(dialog.querySelector('.body')||dialog).append(box);}
      async function refresh(){const r=await fetch('/api/runs/'+run,{headers});if(!r.ok)throw Error('无法读取业务资料');latest=await r.json();}
      async function send(op,target='',value='',ids=[]){const r=await fetch('/api/runs/'+run+'/commands',{method:'POST',headers,body:JSON.stringify({epoch:latest.epoch,action_id:crypto.randomUUID(),op,target,value:typeof value==='object'?JSON.stringify(value):value,ids})});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'保存失败');await refresh();}
      function render(){
        const w=latest.state.workset_delivery;dialog.replaceChildren();
        function savedState(id,snapshot){
          const d=latest.state.domain,o=snapshot?.object||d?.objects?.[id];
          if(!o)return latest.state.stopped?'练习已完成':'练习进行中';
          const parts=[];
          if(o.nickname)parts.push('备注：'+o.nickname);
          parts.push(o.label?'分类：'+o.label:'未分类');
          for(const [key,label] of [['read','已读'],['starred','已收藏'],['hidden','已隐藏'],['deleted','已删除'],['archived','已归档'],['pinned','已置顶'],['muted','已静音'],['reminder','已开启提醒']])if(o[key])parts.push(label);
          const collections=snapshot?.collections||Object.entries(d.collections).filter(([key,ids])=>ids.includes(id)).map(([key])=>key);
          for(const key of collections){const names={history:'观看历史',favorites:'收藏',watchlist:'稍后观看'};const scope=latest.state.scopes?.find(s=>'scope:'+s.id===key);if(scope||names[key])parts.push('已加入'+(scope?.collection||names[key]));}
          if(o.name)parts.push('名称：'+o.name);
          return parts.join(' · ');
        }
        const head=el('div',undefined,'head');head.append(el('h2',w.title),button('返回应用',()=>dialog.close()));dialog.append(head);
        const nav=el('nav',undefined,'nav');
        for(const [id,title] of [['inbox','业务收件箱'],['sources',w.source_title],['directory','责任团队目录'],['editor','编制'+w.title],['sent','已交付文件']]){const b=button(title,async()=>{if(busy)return;try{await refresh();tab=id;render();}catch(error){showError(error);}});b.setAttribute('aria-selected',String(tab===id));nav.append(b);}dialog.append(nav);
        const body=el('section',undefined,'body');dialog.append(body);
        const status=el('p','','status');status.setAttribute('role','status');
        const perform=async(fn)=>{if(busy)return;busy=true;status.textContent='正在保存…';try{await fn();render();}catch(error){status.textContent=error.message;status.className='error';}finally{busy=false;}};
        if(tab==='inbox'){
          body.append(el('p','执行请求与筹备预案分别列出。预案仅供查阅，本次工作请使用十月执行批次。','meta'));
          for(const request of [...w.requests].reverse()){const card=el('article');card.append(el('h3',request.title),el('p',`请求 ${request.id} · 修订 ${request.revision}\n截止时间：${request.deadline}\n责任团队编号：${request.recipient}\n资料来源：《${request.reference_register}》\n业务范围：${request.scope_ids.map(id=>latest.state.scopes?.find(s=>s.id===id)?.name||id).join('、')}`,'meta'),el('p',request.body));body.append(card);}
        }else if(tab==='sources'){
          body.append(el('h3',w.source_title),el('p','按对象编号查找关联资料。同名对象以编号区分；范围外资料也保留在目录中。','meta'));
          const table=el('table'),tr=el('tr');for(const x of ['资料编号','对象编号 / 名称',w.detail_label])tr.append(el('th',x));table.append(tr);
          for(const r of w.references){const row=el('tr');for(const x of [r.id,r.object_code+' · '+r.name+(r.supplier?' · '+r.supplier+' / '+r.supplier_contact:''),r.detail])row.append(el('td',x));table.append(row);}body.append(table);
        }else if(tab==='directory'){
          for(const r of w.directory){const card=el('article');card.append(el('h3',r.name),el('p',`团队编号：${r.id}\n交付邮箱：${r.address}`,'meta'));body.append(card);}
        }else if(tab==='editor'){
          const form=el('div',undefined,'panel'),fields=el('div',undefined,'fields'),inputs={};
          if(formValues===null)formValues={...(w.draft||{})};
          for(const [key,label] of [['request','业务请求'],['title','文档标题'],['deadline','交付截止时间'],['address','接收团队'],['summary','交付说明']]){
            const l=el('label',label,key==='summary'?'wide':'');
            const input=el(key==='request'||key==='address'?'select':key==='summary'?'textarea':'input');
            if(key==='request'){input.append(new Option('请选择业务请求',''));for(const r of [...w.requests].reverse())input.append(new Option(`${r.title} · 修订 ${r.revision}`,r.id));}
            if(key==='address'){input.append(new Option('请选择责任团队',''));for(const r of w.directory)input.append(new Option(`${r.name} · ${r.id} · ${r.address}`,r.address));}
            input.value=formValues[key]||'';if(key==='summary')input.placeholder='说明本文件用途及接收人可据此开展的工作';input.oninput=()=>{formValues[key]=input.value;};input.setAttribute('aria-label',label);inputs[key]=input;l.append(input);fields.append(l);
          }
          inputs.request.onchange=()=>{const request=w.requests.find(r=>r.id===inputs.request.value);if(request){inputs.title.value=request.title;inputs.deadline.value=request.deadline;Object.assign(formValues,{request:request.id,title:request.title,deadline:request.deadline});}};
          form.append(el('p',w.purpose,'meta'),fields,button('保存文档信息',()=>perform(()=>send('assignment.draft','',Object.fromEntries(Object.entries(inputs).map(([key,input])=>[key,input.value])))),'primary'));body.append(form);
          if(w.draft){const panel=el('div',undefined,'panel');panel.append(el('h3','添加'+w.row_title),el('p','先在应用完成规则操作，再选择实际应交付的对象。选择资料目录中对应的来源记录，带入业务信息后可编辑；保存条目时记录该对象的真实状态。','meta'));
            const rows=el('div',undefined,'fields'),objectLabel=el('label',w.row_title),select=el('select');select.setAttribute('aria-label',w.row_title);select.append(new Option('请选择对象',''));for(const r of w.references)select.append(new Option(r.object_code+' · '+r.name+' — '+savedState(r.object),r.object));select.value=rowValues.object;select.onchange=()=>{rowValues={object:select.value,reference:'',detail:''};ref.value='';detail.value='';};objectLabel.append(select);rows.append(objectLabel);
            const refLabel=el('label','关联业务资料'),ref=el('select');ref.setAttribute('aria-label','关联业务资料');ref.append(new Option('请选择来源记录',''));for(const r of w.references)ref.append(new Option(`${r.id} · ${r.object_code} · ${r.name}`,r.id));ref.value=rowValues.reference;refLabel.append(ref);rows.append(refLabel);
            const detailLabel=el('label',w.detail_label,'wide'),detail=el('input');detail.setAttribute('aria-label',w.detail_label);detail.value=rowValues.detail;detail.oninput=()=>{rowValues.detail=detail.value;};detailLabel.append(detail);rows.append(detailLabel);ref.onchange=()=>{detail.value=w.references.find(r=>r.id===ref.value)?.detail||'';rowValues={object:select.value,reference:ref.value,detail:detail.value};};panel.append(rows,button('保存文档条目',()=>perform(()=>send('assignment.row',select.value,{reference:ref.value,detail:detail.value})),'primary'));body.append(panel);
            const list=el('div',undefined,'panel');list.append(el('h3','文档正文'));
            w.draft.rows.forEach((r,i)=>{const source=w.references.find(x=>x.object===r.object),card=el('article');card.append(el('h3',`${i+1}. ${source.object_code} · ${source.name}`),el('p',`${w.detail_label}：${r.detail}\n关联资料：${r.reference}\n条目保存时：${savedState(r.object,r.snapshot)}\n应用当前：${savedState(r.object)}`,'meta'));const actions=el('div',undefined,'actions');actions.append(button('编辑',()=>{select.value=r.object;ref.value=r.reference;detail.value=r.detail;rowValues={object:r.object,reference:r.reference,detail:r.detail};panel.scrollIntoView({behavior:'smooth'});},'small'),button('刷新保存结果',()=>perform(()=>send('assignment.row',r.object,{reference:r.reference,detail:r.detail})),'small'),button('移除',()=>perform(()=>send('assignment.remove',r.object)),'small'));if(i>0)actions.append(button('上移',()=>perform(()=>{const ids=w.draft.rows.map(x=>x.object);[ids[i-1],ids[i]]=[ids[i],ids[i-1]];return send('assignment.order','','',ids);}),'small'));card.append(actions);list.append(card);});list.append(button('交付'+w.title,()=>perform(()=>send('assignment.publish')),'primary'));body.append(list);
          }
        }else{
          if(!w.publications.length)body.append(el('p','尚未交付文件。完成正文后，在文档编辑页交付。','meta'));
          for(const p of [...w.publications].reverse()){const card=el('article');card.append(el('h3',p.document.title),el('p',`已交付至 ${p.document.address}`,'meta'),el('pre',p.body));const download=button('下载文件',async()=>{try{const response=await fetch('/api/runs/'+run+'/files/'+encodeURIComponent(p.id),{headers});if(!response.ok){status.textContent='下载失败';return;}const blob=await response.blob(),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=w.title+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){showError(error);}});card.append(download);body.append(card);}
        }
        body.append(status);
      }
    }
  };
})();
