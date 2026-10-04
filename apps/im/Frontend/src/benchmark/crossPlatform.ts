/** Native IM conversations backed by actual source requests and artifact snapshots. */
export async function crossPlatformResponse(s:any,path:string,method:string,body:any,run:string,token:string,command:(op:string,target?:string,value?:string)=>Promise<any>){
  const h=s.cross_platform,stamp=1790899200;
  const native=(module:string,query='')=>module==='code'?`/native/code/${run}/#${token}`:`/native/product/${module}/${run}${query}#${token}`;
  const work=native(h.primary_app);
  const peer=Number(path.match(/^\/api\/conversations\/(\d+)/)?.[1]);
  const person=h.people.find((p:any)=>p.id===peer);
  const link=(r:any)=>h.primary_app==='blog'&&r.link.startsWith('posts/')?native('blog','?post='+encodeURIComponent(r.link.slice(6))):h.primary_app==='studio'&&r.link.startsWith('files/')?native('studio','?file='+encodeURIComponent(r.link.slice(6))):h.primary_app==='shop'&&r.link.startsWith('orders/')?native('shop','?order='+encodeURIComponent(r.link.slice(7))):h.primary_app==='travel'?native('travel','?file=travel-itinerary'):h.primary_app==='media'?native('media','?file=screening-timetable'):work;
  if(method==='GET'&&path==='/api/workspace')return {instructions:'查看委托人的有效需求与源附件，进入业务应用完成处理，再回到对应会话交付实际成果。过期草案不作为执行依据。',handoff:work};
  if(method==='GET'&&path==='/api/friends')return {friends:h.people.map((p:any)=>({user_id:p.id,username:p.name,group:p.role}))};
  if(method==='GET'&&path==='/api/conversations')return {conversations:h.people.map((p:any)=>({conversation_id:p.id,type:'private',name:p.name,peer_user:{user_id:p.id,username:p.name},other_user_id:p.id,unread_count:h.read?.[String(p.id)]?0:h.requests.filter((r:any)=>r.requester===p.id&&r.revision===2).length,last_message:{content:h.receipts.some((r:any)=>r.recipient===p.id)?'成果已交付':h.requests.find((r:any)=>r.requester===p.id&&r.revision===2)?.title||'其他项目沟通',created_at:stamp}}))};
  if(method==='POST'&&path.endsWith('/read')&&person){await command('handoff.read',String(peer));return {read:true};}
  if(method==='GET'&&path==='/api/handoff/resources'){
    const fresh=await command('handoff.refresh');
    return {resources:fresh.state.cross_platform.available,people:h.people};
  }
  if(method==='GET'&&path.endsWith('/messages')&&person){
    const requests=h.requests.filter((r:any)=>r.requester===peer).map((r:any,i:number)=>({msg_id:3000+h.requests.indexOf(r),sender_id:peer,sender_name:person.name,created_at:stamp+i,content:r.title,handoff_request:{...r,url:work}}));
    const nativeReceipts=s.task_id===43?s.world.receipts.filter((r:any)=>r.recipient===peer).map((r:any,i:number)=>({msg_id:25000+i,sender_id:1,sender_name:s.source.operator||'我',created_at:stamp+90+i,content:'生成结果：'+r.record_code+' · '+r.name,studio_share:{...r,url:native('studio','?output='+encodeURIComponent(r.target))}})):[];
    const receipts=h.receipts.filter((r:any)=>r.recipient===peer).map((r:any,i:number)=>({msg_id:10000+Number(r.id.split('-').at(-1)),sender_id:1,sender_name:s.source.operator||'我',created_at:stamp+100+i,content:'回复需求 '+r.request+' · 实际成果交付',handoff_delivery:{...r,attachments:r.attachments.map((a:any)=>({...a,url:link(a),related_links:h.primary_app==='blog'?(a.record?.index||[]).map((row:any)=>({label:'栏目文章 '+row.publication,url:native('blog','?post='+encodeURIComponent(row.publication))})):[]}))}}));
    const messages=h.messages.filter((m:any)=>m.recipient===peer).map((m:any)=>({msg_id:20000+m.id,sender_id:1,sender_name:s.source.operator||'我',created_at:stamp+1000+m.id,content:m.body}));
    return {messages:[...requests,...nativeReceipts,...receipts,...messages].sort((a,b)=>b.created_at-a.created_at)};
  }
  if(method==='POST'&&path.endsWith('/messages')&&person){await command('handoff.message',String(peer),JSON.stringify({text:body.content}));return {msg_id:20000+h.messages.length+1};}
  const profile=h.people.find((p:any)=>p.id===Number(path.match(/\/user\/(\d+)/)?.[1]));
  if(method==='GET'&&profile)return {user_id:profile.id,username:profile.name,bio:profile.role};
  return undefined;
}
