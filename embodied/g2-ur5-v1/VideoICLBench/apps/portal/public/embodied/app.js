/* Assigned-session GUI. The model operates pixels and public controls only. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  let state = {}, frameId = null, busy = false, connected = false;
  let publicObservationCandidate = null;
  function invalidatePublicObservation(){publicObservationCandidate=null;}
  function bindPublicObservation(observation){
    if(!observation.state||observation.state.frame_id!==frameId)return;
    const publicState=JSON.parse(JSON.stringify(state));publicState.frame_id=frameId;
    publicObservationCandidate={frame_id:frameId,state:publicState,cameras:Object.keys(observation.images||{}).filter(n=>['head','left_wrist','right_wrist'].includes(n)&&typeof observation.images[n]==='string'&&observation.images[n].length)};
  }
  Object.defineProperty(window,'videoiclPublicObservation',{configurable:false,enumerable:false,get(){
    const value=publicObservationCandidate;
    if(busy||!connected||!value||value.frame_id!==frameId||!value.cameras.length)return null;
    if(value.cameras.some(n=>{const im=$('camera-'+n);return !im||im.hidden||im.dataset.measurementFrame!==frameId||!im.complete||!im.naturalWidth;}))return null;
    return JSON.parse(JSON.stringify({frame_id:value.frame_id,state:value.state}));
  }});
  let selected = {left: 'STILL', right: 'STILL'}, demoUrl = null, demoAttempted = false;
  const terminal = new Set(['done','give_up','giveup','finished','stopped','sealed','submitted','aborted','budget_exhausted','budget_paused','closed','faulted']);
  const labels = {STILL:'保持 STILL',FWD:'前进 FWD',BACK:'后退 BACK',LEFT:'向左 LEFT',RIGHT:'向右 RIGHT',UP:'上移 UP',DOWN:'下移 DOWN',GRASP:'闭合 GRASP',RELEASE:'松开 RELEASE',ROTATE_CCW:'逆时针 CCW',ROTATE_CW:'顺时针 CW',PITCH_UP:'俯仰+ PITCH_UP',PITCH_DOWN:'俯仰− PITCH_DOWN',ROLL_LEFT:'横滚+ ROLL_LEFT',ROLL_RIGHT:'横滚− ROLL_RIGHT'};
  const guide = {STILL:'保持该手当前目标姿态与夹爪状态。 Hold pose and gripper.',FWD:'沿任务 +X 平移。 Move along task +X.',BACK:'沿任务 −X 平移。 Move along task −X.',LEFT:'沿任务 +Y 平移。 Move along task +Y.',RIGHT:'沿任务 −Y 平移。 Move along task −Y.',UP:'沿任务 +Z 平移。 Move along task +Z.',DOWN:'沿任务 −Z 平移。 Move along task −Z.',GRASP:'闭合该手夹爪；保持位置与姿态。 Close gripper.',RELEASE:'张开该手夹爪；保持位置与姿态。 Open gripper.',ROTATE_CCW:'绕任务 +Z 按右手定则旋转正角度。 Positive rotation about task +Z.',ROTATE_CW:'绕任务 +Z 旋转负角度。 Negative rotation about task +Z.',PITCH_UP:'绕任务 +Y 旋转正角度。 Positive rotation about task +Y.',PITCH_DOWN:'绕任务 +Y 旋转负角度。 Negative rotation about task +Y.',ROLL_LEFT:'绕任务 +X 旋转正角度。 Positive rotation about task +X.',ROLL_RIGHT:'绕任务 +X 旋转负角度。 Negative rotation about task +X.'};
  const statusLabels = {ready:'就绪',running:'运行中',active:'运行中',done:'已声明完成 Done',give_up:'已放弃 Give up',giveup:'已放弃 Give up',finished:'已结束',stopped:'已停止',sealed:'已封存',submitted:'已提交',aborted:'已中止',budget_exhausted:'预算已用完',budget_paused:'预算已用完',closed:'已关闭',faulted:'环境异常'};
  const conditionLabels = {real:'人工实拍',sim:'仿真示范',text_rule:'文字说明'};
  const safeErrors = {operation_pending:'已有操作正在处理，请等待原操作返回新观察；不要重复提交或因此放弃。 An operation is pending; await its result without cancelling, replaying, or giving up.',unauthorized:'会话授权无效，请使用本次运行分配的链接重新打开。',forbidden:'当前会话没有执行该操作的权限。',stale_frame:'观察已更新，本次动作未执行。请刷新观察后重新选择。',invalid_action:'动作参数不符合本任务的公开限额，请检查后重试。',invalid_request:'输入格式未通过检查，请刷新后重试。',invalid_rule_report:'请填写有效的方法说明。',invalid_timestamps:'视频时间点须为有效的大于或等于 0 的秒数。',missing_timestamps:'请填写所记录方法的视频依据时间点。',rule_report_required:'当前运行要求方法记录，请刷新确认该运行的协议。',rule_report_locked:'本次运行的方法记录已锁定。',budget_exhausted:'预算已用完，可以结束本次操作。',episode_stopped:'本次运行已停止接收操作。',episode_finished:'本次运行已结束。',environment_unavailable:'环境暂时不可用，请刷新查看当前状态。',action_execution_failed:'动作执行发生异常。请刷新观察确认当前状态；不要重复提交同一动作。',not_ready:'环境尚未就绪，请稍后刷新观察。'};
  const text = (value, max=120) => typeof value === 'string' ? value.slice(0,max) : '';
  const number = value => typeof value === 'number' && Number.isFinite(value);
  const fmt = value => number(value) ? (Math.abs(value) < 1e-9 ? '0' : value.toFixed(4).replace(/\.?0+$/,'')) : '—';
  function notice(message,tone='') { $('notice').textContent=message; $('notice').className='notice'+(tone?' '+tone:''); }
  function isActive() { return connected && !terminal.has(state.status) && ['ready','running','active'].includes(state.status); }
  function isText() { return state.condition === 'text_rule'; }
  function reported() { return state.rule_reported === true; }
  function validParameter(schema) { return Boolean(schema && number(schema.minimum) && number(schema.maximum) && schema.minimum <= schema.maximum); }
  function availableTokens() {
    const values=Array.isArray((state.action_schema||{}).tokens)?state.action_schema.tokens:[];
    const clean=values.filter(value => typeof value === 'string' && /^[A-Z_]+$/.test(value));
    return [...new Set(clean)].filter(value=>!value.startsWith('MV_')||!clean.includes(value.slice(3)));
  }
  function renderGuide(tokens) {
    const key=JSON.stringify(tokens), host=$('action-guide-content');
    if(host.dataset.tokens!==key) {
      host.replaceChildren(); host.dataset.tokens=key;
      const table=document.createElement('table'),body=document.createElement('tbody');
      for(const token of tokens) {
        const code=token.replace(/^MV_/,''); const row=document.createElement('tr');
        const name=document.createElement('th');name.textContent=code;name.scope='row';
        const detail=document.createElement('td');detail.textContent=guide[code]||'按本次运行的公开动作定义执行。';
        row.append(name,detail);body.append(row);
      }
      table.append(body);host.append(table);
    }
    const schema=state.action_schema||{},step=schema.step_mm,rotation=schema.rotation_deg;
    $('parameter-help').textContent=(validParameter(step)?'移动范围 '+step.minimum+'–'+step.maximum+' mm；':'')+(validParameter(rotation)?'旋转范围 '+rotation.minimum+'–'+rotation.maximum+'°。':'')+' 轴方向属于公开任务坐标系，相机中的投影方向可能不同。';
  }
  function renderControls() {
    if(busy||terminal.has(state.status))clearOverlays();
    document.body.setAttribute('aria-busy',String(busy));
    document.body.dataset.episodeStatus=Object.hasOwn(statusLabels,state.status)?state.status:'unconnected';
    const tokens=availableTokens(),active=isActive(),schema=state.action_schema||{};
    for(const side of ['left','right']) {
      const panel=$(side+'-actions');
      if(panel.dataset.tokens!==JSON.stringify(tokens)) {
        panel.replaceChildren();panel.dataset.tokens=JSON.stringify(tokens);
        for(const value of tokens) {
          const button=document.createElement('button');button.type='button';button.className='action-button';button.dataset.token=value;
          button.textContent=labels[value.replace(/^MV_/,'')]||value;
          button.setAttribute('aria-label',(side==='left'?'左臂 Left: ':'右臂 Right: ')+button.textContent+' ('+value+')');
          button.addEventListener('click',()=>{selected[side]=value;renderControls();});panel.append(button);
        }
      }
      if(!tokens.includes(selected[side])) selected[side]=tokens.includes('STILL')?'STILL':tokens[0];
      $(side+'-selected').textContent=labels[(selected[side]||'').replace(/^MV_/,'')]||selected[side]||'未分配动作';
      for(const button of panel.children) { button.setAttribute('aria-pressed',String(button.dataset.token===selected[side]));button.disabled=busy||!active||frameId===null; }
    }
    $('commit').disabled=busy||!active||frameId===null||!tokens.length||!validParameter(schema.step_mm)||!validParameter(schema.rotation_deg);
    for(const [id,bounds] of [['step-mm',schema.step_mm],['rotation-deg',schema.rotation_deg]]) $(id).disabled=busy||!active||!validParameter(bounds);
    const recordLocked=reported()||(Number.isInteger(state.steps)&&state.steps>0);
    $('report-rule').disabled=busy||!active||recordLocked;
    $('inferred-rule').disabled=busy||!active||recordLocked;
    $('evidence-seconds').disabled=busy||!active||recordLocked;
    $('done').disabled=busy||!active||frameId===null;$('giveup').disabled=busy||!active||frameId===null;$('stop-reason').disabled=busy||!active;
    $('refresh').disabled=busy||!token;
    $('action-gate').textContent=terminal.has(state.status)?'本次运行已停止接收动作。':'每次 Commit 计为一次双臂物理动作。';
    $('rule-status').textContent=reported()?'已记录':'可选记录，不影响操作';
    $('rule-status').className='small-status'+(reported()?' recorded':'');
    renderGuide(tokens);
    if($('depth-download'))$('depth-download').disabled=busy||!active||!frameId;
    if($('depth-query'))$('depth-query').disabled=busy||!active||!frameId;
  }
  function configureParameter(id,schema) {
    const input=$(id);if(!validParameter(schema)){input.disabled=true;input.value='';return;}
    const old=Number(input.value);input.min=String(schema.minimum);input.max=String(schema.maximum);
    if(!input.value||!Number.isFinite(old)||old<schema.minimum||old>schema.maximum) input.value=String(number(schema.default)?schema.default:schema.minimum);
    input.title=schema.minimum+' – '+schema.maximum;
  }
  function appendLine(host,label,value,kind='') {
    const line=document.createElement('p');line.className='feedback-line'+(kind?' '+kind:'');
    const name=document.createElement('span');name.className='feedback-label';name.textContent=label;
    const detail=document.createElement('span');detail.textContent=value;line.append(name,detail);host.append(line);
  }
  function vector(value,count) { return Array.isArray(value)&&value.length===count&&value.every(number)?value.map(fmt).join(', '):'—'; }
  function renderFeedback() {
    const host=$('robot-feedback'),feedback=state.robot_feedback;host.replaceChildren();
    if(!feedback||typeof feedback!=='object'||Array.isArray(feedback)){appendLine(host,'状态','等待公开机器人状态。');return;}
    const full=document.createElement('details'),fullSummary=document.createElement('summary');fullSummary.textContent='机器人状态';full.append(fullSummary);host.append(full);
    appendLine(full,'坐标系',text(feedback.coordinate_frame)||'未提供');
    const units=feedback.units;
    const unitText=typeof units==='string'?text(units):units&&typeof units==='object'?['position','tcp_position','rotation','joints','joint_positions','gripper'].filter(k=>typeof units[k]==='string').map(k=>k+': '+text(units[k],24)).join(' · '):'';
    if(unitText) appendLine(full,'单位',unitText);
    for(const side of ['left','right']) {
      const arm=feedback.arms&&feedback.arms[side],section=document.createElement('section');section.className='arm-feedback';
      const heading=document.createElement('h3');heading.textContent=side==='left'?'左臂 Left':'右臂 Right';section.append(heading);
      if(!arm||typeof arm!=='object'){appendLine(section,'状态','未提供');full.append(section);continue;}
      appendLine(section,'TCP xyz',vector(arm.tcp_position,3),'numeric');
      appendLine(section,'TCP q(wxyz)',vector(arm.tcp_quaternion_wxyz,4),'numeric');
      if(arm.tcp_position_world_m)appendLine(section,'TCP world xyz (m)',vector(arm.tcp_position_world_m,3),'numeric');
      if(arm.tcp_quaternion_world_wxyz)appendLine(section,'TCP world q(wxyz)',vector(arm.tcp_quaternion_world_wxyz,4),'numeric');
      if(arm.finger_joint_position_units==='m')appendLine(section,'双指关节位置 (m)',vector(arm.finger_joint_positions,2),'numeric');
      appendLine(section,'接触 / 持物','接触 '+(arm.contact_status==='not_measured'?'未测量':text(arm.contact_status)||'未提供')+'；持物 '+(arm.holding_status==='not_measured'?'未测量':text(arm.holding_status)||'未提供')+'。夹爪闭合不等于抓取成功。');
      if(arm.measured_sensors&&typeof arm.measured_sensors==='object'){
        const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='速度与关节限位（实测）';details.append(summary);
        for(const [key,label] of Object.entries({joint_velocities_rad_s:'关节速度 rad/s',finger_joint_velocities_m_s:'指关节速度 m/s',joint_soft_limits_rad:'关节软限位 rad',tcp_linear_velocity_task_m_s:'TCP 速度 task m/s'})){
          const sensor=arm.measured_sensors[key];
          appendLine(details,label,sensor&&sensor.available===true&&Array.isArray(sensor.value)?JSON.stringify(sensor.value):'未测量 / 不可用');
        }
        section.append(details);
      }

      const opening=arm.gripper_open_fraction;
      appendLine(section,'夹爪开度',number(opening)&&opening>=0&&opening<=1?(opening*100).toFixed(1)+'%':'—');
      if(Array.isArray(arm.joint_names)&&Array.isArray(arm.joint_positions_rad)&&arm.joint_names.length===arm.joint_positions_rad.length&&arm.joint_names.length<=64&&arm.joint_positions_rad.every(number)) {
        const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='关节状态（rad）';details.append(summary);
        for(let i=0;i<arm.joint_names.length;i++) if(typeof arm.joint_names[i]==='string') appendLine(details,text(arm.joint_names[i],64),fmt(arm.joint_positions_rad[i]),'numeric');
        section.append(details);
      }
      full.append(section);
    }
    const action=feedback.last_action;
    if(action&&typeof action==='object') {
      const section=document.createElement('section');section.className='last-action-feedback';const heading=document.createElement('h3');heading.textContent='最近动作';section.append(heading);
      appendLine(section,'双臂',text(action.left,32)+' / '+text(action.right,32));
      appendLine(section,'参数',fmt(action.step_mm)+' mm · '+fmt(action.rotation_deg)+'°');
      const error=action.tracking_error_m;
      if(number(error))appendLine(section,'跟踪误差',fmt(error)+' m');
      else if(error&&typeof error==='object')appendLine(section,'跟踪误差','左 '+fmt(error.left)+' m / 右 '+fmt(error.right)+' m');
      const more=document.createElement('details'),summary=document.createElement('summary');summary.textContent='位移与跟踪详情';more.append(summary);
      for(const side of ['left','right']){
        const diagnostic=(action.control_feedback||{})[side];if(!diagnostic)continue;
        const label=side==='left'?'左臂':'右臂';
        appendLine(section,label+'执行状态',({blocked:'受限，未达到目标',partial:'未达到目标',reached:'已达到目标'})[diagnostic.status]||'未确认');
        appendLine(more,label+'期望位移 m',vector(diagnostic.requested_delta_m,3));
        appendLine(more,label+'实际位移 m',vector(diagnostic.actual_delta_m,3));
        appendLine(more,label+'原因',text(diagnostic.reason,160)||'未提供；不能仅凭受限推断碰撞');
        if(Array.isArray(diagnostic.joint_limit_names)&&diagnostic.joint_limit_names.length)appendLine(more,label+'触及限位',diagnostic.joint_limit_names.map(x=>text(x,40)).join(', '));
      }
      section.append(more);host.prepend(section);
    }else appendLine(host,'动作','尚无动作回执');
  }
  function renderState(update) {
    for(const key of ['run_id','task_id','title','instruction','status','steps','max_actions','condition','action_schema','text_rule','demo_available','rule_reported','diagnostics_enabled','robot_feedback','observation_contract']) if(Object.hasOwn(update,key))state[key]=update[key];
    if(Object.hasOwn(update,'frame_id')){if(update.frame_id!==frameId){invalidatePublicObservation();clearMeasurement('观察已更新，请重新测点。');}frameId=update.frame_id;}
    $('task-title').textContent=state.title||'任务环境';$('instruction').textContent=state.instruction||'请根据分配的示范完成当前任务。';$('task-id').textContent=state.task_id||'任务';
    $('run-id').textContent=typeof state.run_id==='string'?'运行 '+state.run_id.slice(0,12):'独立运行';
    $('status').textContent=statusLabels[state.status]||'等待环境';$('status-dot').className='status-dot'+(terminal.has(state.status)?' stopped':connected?' connected':'');
    $('budget').textContent=(Number.isInteger(state.steps)?state.steps:'—')+' / '+(Number.isInteger(state.max_actions)?state.max_actions:'—')+' 次物理动作';
    $('condition').textContent=conditionLabels[state.condition]||'待分配';$('reference-title').textContent=isText()?'任务说明':'任务示范';
    $('text-reference').hidden=!isText();$('video-reference').hidden=isText()||!state.demo_available;$('reference-empty').hidden=isText()||state.demo_available===true;
    $('reference-empty').textContent='当前运行尚未提供可用示范。';$('rule-panel').hidden=isText()||state.diagnostics_enabled!==true;
    $('evidence-field').hidden=isText();$('evidence-seconds').required=!isText();$('text-rule').textContent=isText()&&typeof state.text_rule==='string'?state.text_rule:'';
    renderFeedback();renderControls();configureParameter('step-mm',(state.action_schema||{}).step_mm);configureParameter('rotation-deg',(state.action_schema||{}).rotation_deg);
    if(frameId!==null)$('frame-label').textContent='观察 '+String(frameId);
    if($('camera-calibration'))$('camera-calibration').textContent=JSON.stringify((state.robot_feedback||{}).camera_calibration||{},null,2);
  }
  async function request(path,body,raw=false) {
    const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'omit',cache:'no-store',headers:{Authorization:'Bearer '+token,...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
    if(!response.ok){let data={};try{data=await response.json();}catch(_){}const code=typeof data.error==='string'?data.error:data.error&&data.error.code;
      const error=new Error(safeErrors[code]||(response.status===401?safeErrors.unauthorized:response.status===409?safeErrors.stale_frame:response.status===503?safeErrors.not_ready:'请求未完成。请刷新观察确认当前状态。'));error.status=response.status;error.code=code;throw error;}
    return raw?response.blob():response.json();
  }
  async function loadDemo(){if(demoAttempted||isText()||!state.demo_available)return;demoAttempted=true;try{demoUrl=URL.createObjectURL(await request('/demo.mp4',undefined,true));$('demo').src=demoUrl;}catch(_){$('video-note').textContent='示范暂时无法载入。可刷新观察后重试连接。';demoAttempted=false;}}
  function renderObservation(observation){invalidatePublicObservation();clearMeasurement('观察已更新，请重新测点。');if(observation.state)renderState(observation.state);if(Object.hasOwn(observation,'frame_id')){frameId=observation.frame_id;$('frame-label').textContent='观察 '+String(frameId);}const images=observation.images||{};
    for(const name of ['head','left_wrist','right_wrist']){const value=images[name],image=$('camera-'+name);if(typeof value==='string'&&value.length&&/^[A-Za-z0-9+/=\s]+$/.test(value)){const renderedFrame=frameId;image.dataset.measurementFrame='';image.onload=()=>{if(frameId===renderedFrame)image.dataset.measurementFrame=renderedFrame;};image.src='data:image/jpeg;base64,'+value;image.hidden=false;image.previousElementSibling.hidden=true;} else{image.dataset.measurementFrame='';image.hidden=true;image.previousElementSibling.hidden=false;image.previousElementSibling.textContent='本次观察未提供该视角，可继续使用其他视角。';}}
    if($('depth-sensor-status'))$('depth-sensor-status').textContent=JSON.stringify((state.robot_feedback||{}).depth_sensors||{available:false,reason:'未提供仿真深度'},null,2);
    bindPublicObservation(observation);renderControls();}
  async function observe(){renderObservation(await request('/api/observe'));}
  async function refresh(){invalidatePublicObservation();if(!token){notice('缺少本次运行的会话授权，请从分配的会话链接重新打开。','error');return;}busy=true;renderControls();try{connected=true;renderState(await request('/api/state'));await observe();notice(terminal.has(state.status)?'本次操作已经结束。':'观察已更新。请查看分配的方法和当前环境。',terminal.has(state.status)?'neutral':'');await loadDemo();}catch(error){clearMeasurement('观察未确认，请刷新后重新测点。');if(error.code!=='operation_pending')connected=false;notice(error.message||'无法连接环境，请刷新查看状态。','error');}finally{busy=false;renderControls();}}
  async function mutate(path,body,success){invalidatePublicObservation();busy=true;renderControls();notice('正在处理，请等待返回观察。');try{const result=await request(path,body);if(result.state)renderState(result.state);if(result.frame_id!==undefined||result.images)renderObservation(result);if(path==='/api/report-inferred-rule')state.rule_reported=true;
      const ending=path==='/api/done'||path==='/api/giveup';if(ending){if(!terminal.has(state.status))state.status=path==='/api/done'?'done':'give_up';renderState(state);}else await observe();
      const feedback=state.robot_feedback?.last_action?.control_feedback||{};
      const limited=path==='/api/action'&&Object.values(feedback).some(item=>item&&['blocked','partial'].includes(item.status));
      notice(limited?'动作已返回，但未达到目标。请查看期望与实际位移及关节限位反馈。':success,limited?'error':ending?'neutral':'');
    }catch(error){frameId=null;clearMeasurement('操作状态未确认，请刷新后重新测点。');if(error.status===undefined||error.status>=500||[401,403,410].includes(error.status))connected=false;notice(error.message||'连接中断。请刷新观察确认状态；不要重复提交同一动作。','error');}finally{busy=false;renderControls();}}
  // Sensor queries read the current RGB-D capture; they never move the robot.
  const measurementPanel=document.createElement('details');measurementPanel.className='panel measurement-panel';
  measurementPanel.innerHTML='<summary class="panel-heading">仿真深度</summary><div class="measurement-body"><div id="sensor-controls"><p>同帧光轴深度 Z（m）。点击图像，或输入原图 row / col。</p><label>相机 <select id="depth-camera"><option value="head">head</option><option value="left_wrist">left_wrist</option><option value="right_wrist">right_wrist</option></select></label><label>row <input id="depth-row" type="number" min="0" step="1" value="0"></label><label>col <input id="depth-col" type="number" min="0" step="1" value="0"></label><button type="button" id="depth-query">读取深度</button><button type="button" id="depth-download">下载深度与标定 JSON</button><details><summary>传感器状态</summary><pre id="depth-sensor-status"></pre></details></div><output id="measure-result">尚未读取</output><details><summary>相机内外参</summary><pre id="camera-calibration"></pre></details><details><summary>测点 JSON</summary><pre id="measurement-json">null</pre></details></div>';
  document.querySelector('.context-column').append(measurementPanel);
  $('depth-query').addEventListener('click',()=>{
    const name=$('depth-camera').value,image=$('camera-'+name),row=Number($('depth-row').value),col=Number($('depth-col').value);
    if(!Number.isInteger(row)||!Number.isInteger(col)||!$('depth-row').value||!$('depth-col').value){clearMeasurement('请输入原图整数 row/col。');return;}
    measureClick(name,image,null,{row,col});
  });
  $('depth-download').addEventListener('click',async()=>{
    if(busy||!frameId)return;
    const body={frame_id:frameId,camera:$('depth-camera').value};busy=true;renderControls();
    try{
      const result=await request('/api/depth-map',body);
      if(!result.valid||result.frame_id!==frameId||result.camera!==body.camera||result.measurement_source!=='simulator_depth'||result.physical_action!==false)throw new Error('没有可下载的同帧仿真深度。');
      const blob=new Blob([JSON.stringify(result)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');
      a.href=url;a.download='depth-'+body.camera+'-'+String(frameId).replace(/[^a-zA-Z0-9_-]/g,'_')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      notice('已下载当前观察的深度与标定，未执行物理动作。');
    }catch(error){notice(error.message,'error');}finally{busy=false;renderControls();}
  });
  function clearMeasurementJSON(){if($('measurement-json'))$('measurement-json').textContent='null';}
  function clearMeasurement(message) {
    clearOverlays();clearMeasurementJSON();
    if($('measure-result')&&message)$('measure-result').textContent=message;
  }
  function clearOverlays(){document.querySelectorAll('.measurement-overlay').forEach(e=>e.remove());}
  function overlay(name){
    const im=$('camera-'+name);if(!im||im.hidden||im.dataset.measurementFrame!==frameId)return null;
    const rect=im.getBoundingClientRect(),figure=im.closest('figure'),fr=figure.getBoundingClientRect();
    const scale=Math.min(rect.width/im.naturalWidth,rect.height/im.naturalHeight);
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('measurement-overlay');svg.dataset.camera=name;
    svg.setAttribute('viewBox','0 0 '+im.naturalWidth+' '+im.naturalHeight);
    Object.assign(svg.style,{position:'absolute',pointerEvents:'none',left:(rect.left-fr.left+(rect.width-im.naturalWidth*scale)/2)+'px',top:(rect.top-fr.top+(rect.height-im.naturalHeight*scale)/2)+'px',width:(im.naturalWidth*scale)+'px',height:(im.naturalHeight*scale)+'px',zIndex:'2'});
    figure.append(svg);return svg;
  }
  function overlayPoint(name,p,label){
    const im=$('camera-'+name);if(!im||!Array.isArray(p)||!p.every(Number.isFinite)||p[0]<0||p[1]<0||p[0]>=im.naturalHeight||p[1]>=im.naturalWidth)return;
    const svg=overlay(name);if(!svg)return;
    const circle=document.createElementNS(svg.namespaceURI,'circle');for(const [k,v] of Object.entries({cx:p[1]+.5,cy:p[0]+.5,r:5,fill:'none',stroke:'#f000ce','stroke-width':2}))circle.setAttribute(k,v);svg.append(circle);
    const text=document.createElementNS(svg.namespaceURI,'text');text.setAttribute('x',p[1]+8);text.setAttribute('y',p[0]-5);text.setAttribute('fill','#f000ce');text.setAttribute('font-size','15');text.textContent=label;svg.append(text);
  }
  // BEGIN SENSOR DEPTH ENVELOPE
  function sensorDepthEnvelope(result,body,imageSize,currentFrame) {
    const invalid=reason=>({calibration:null,measurement:{valid:false,reason,physical_action:false}});
    const finite=v=>typeof v==='number'&&Number.isFinite(v);
    const matrix=(m,n)=>Array.isArray(m)&&m.length===n&&m.every(r=>Array.isArray(r)&&r.length===n&&r.every(finite));
    if(!result||body.frame_id!==currentFrame||result.frame_id!==currentFrame)return invalid('frame_mismatch');
    if(result.valid!==true)return invalid(typeof result.reason==='string'?result.reason:'depth_unavailable');
    if(result.camera!==body.camera||!Array.isArray(result.pixel)||result.pixel[0]!==body.row||result.pixel[1]!==body.col)return invalid('camera_or_pixel_mismatch');
    if(result.measurement_source!=='simulator_depth'||result.physical_action!==false||result.estimated!==false||result.method!=='simulator_axial_depth'||result.units!=='m'||result.depth_convention!=='optical_axis_m'||result.sensor_source!=='isaac_camera_distance_to_image_plane'||result.target_frame!=='world')return invalid('unsupported_measurement_provenance');
    const c=result.camera_calibration;
    if(!c||c.available!==true||c.convention!=='opengl'||c.units!=='m'||!matrix(c.K,3)||!matrix(c.T_task_from_camera,4)||!matrix(c.T_world_from_camera_optical,4)||!matrix(c.T_world_from_camera,4))return invalid('calibration_unavailable');
    if(c.width!==imageSize.width||c.height!==imageSize.height||result.width!==c.width||result.height!==c.height)return invalid('image_calibration_size_mismatch');
    if(!Number.isInteger(body.row)||!Number.isInteger(body.col)||body.row<0||body.col<0||body.row>=c.height||body.col>=c.width||!finite(result.depth_m)||result.depth_m<=0)return invalid('invalid_pixel_or_depth');
    const measurement={valid:true,estimated:false,frame_id:currentFrame,camera:body.camera,pixel:[body.row,body.col],depth_m:result.depth_m,width:c.width,height:c.height,sensor_source:'isaac_camera_distance_to_image_plane',target_frame:'world',units:'m',depth_convention:'optical_axis_m',measurement_source:'simulator_depth',method:'simulator_axial_depth',physical_action:false,pixel_order:'row_col',pixel_space:'native_image'};
    if(Number.isInteger(result.observation_tick))measurement.observation_tick=result.observation_tick;
    return {calibration:c,measurement};
  }
  // END SENSOR DEPTH ENVELOPE
  function nativePixel(image,event){
    const rect=image.getBoundingClientRect(),w=image.naturalWidth,h=image.naturalHeight;
    const scale=Math.min(rect.width/w,rect.height/h),left=rect.left+(rect.width-w*scale)/2,top=rect.top+(rect.height-h*scale)/2;
    const col=(event.clientX-left)/scale-.5,row=(event.clientY-top)/scale-.5;
    if(!Number.isFinite(row)||!Number.isFinite(col)||row<0||col<0||row>=h||col>=w)return null;
    return {row:Math.round(Math.min(h-1,row)),col:Math.round(Math.min(w-1,col))};
  }
  async function measureClick(name,image,event,explicitPoint=null){
    if(busy||!frameId||!connected)return;
    if(image.hidden||image.dataset.measurementFrame!==frameId){clearMeasurement('图像尚未加载，请等待或刷新。');return;}
    const point=explicitPoint||nativePixel(image,event);clearMeasurementJSON();
    if(!point){$('measure-result').textContent='请点击图像内容，避开留白。';return;}
    const body={frame_id:frameId,camera:name,...point},imageSize={width:image.naturalWidth,height:image.naturalHeight};
    measurementPanel.open=true;$('depth-camera').value=name;$('depth-row').value=String(point.row);$('depth-col').value=String(point.col);
    busy=true;renderControls();$('measure-result').textContent='读取同帧深度…';
    try{
      const result=await request('/api/depth-point',body),envelope=sensorDepthEnvelope(result,body,imageSize,frameId);
      $('measurement-json').textContent=JSON.stringify(envelope,null,2);
      if(!envelope.measurement.valid){$('measure-result').textContent='深度不可用：'+envelope.measurement.reason;return;}
      clearOverlays();overlayPoint(body.camera,[body.row,body.col],'Z');
      $('measure-result').textContent=body.camera+' [row '+body.row+', col '+body.col+'] · Z = '+result.depth_m.toFixed(6)+' m';
      $('camera-calibration').textContent=JSON.stringify(envelope.calibration,null,2);
    }catch(error){clearMeasurement(error.message||'深度读取失败');}finally{busy=false;renderControls();}
  }
  for(const name of ['head','left_wrist','right_wrist']){
    const image=$('camera-'+name);image.addEventListener('load',()=>{clearOverlays();});new ResizeObserver(()=>{clearOverlays();}).observe(image);image.addEventListener('click',event=>measureClick(name,image,event));
    const zoom=document.createElement('button');zoom.type='button';zoom.className='camera-zoom';zoom.textContent='放大/还原';zoom.addEventListener('click',()=>{clearOverlays();image.closest('figure').classList.toggle('camera-enlarged');});image.closest('figure').querySelector('figcaption').append(zoom);
  }
  $('refresh').addEventListener('click',refresh);
  $('action-form').addEventListener('submit',event=>{event.preventDefault();if($('commit').disabled||!$('action-form').reportValidity())return;mutate('/api/action',{frame_id:frameId,left:selected.left,right:selected.right,step_mm:Number($('step-mm').value),rotation_deg:Number($('rotation-deg').value)},'动作已执行。请查看更新后的环境。');});
  $('rule-form').addEventListener('submit',event=>{event.preventDefault();if($('report-rule').disabled||!$('rule-form').reportValidity())return;const seconds=isText()?[]:$('evidence-seconds').value.split(/[,，\s]+/).filter(Boolean).map(Number);if(seconds.some(value=>!Number.isFinite(value)||value<0)||(!isText()&&!seconds.length)){notice('请填写有效的视频时间点。','error');return;}mutate('/api/report-inferred-rule',{rule:$('inferred-rule').value.trim(),evidence_seconds:seconds},'可选方法记录已保存；不提供正确性反馈。');});
  $('done').addEventListener('click',()=>{if(!$('done').disabled)mutate('/api/done',{frame_id:frameId,summary:$('stop-reason').value.trim()},'已声明完成，停止接收动作。');});
  $('giveup').addEventListener('click',()=>{if(!$('giveup').disabled)mutate('/api/giveup',{frame_id:frameId,reason:$('stop-reason').value.trim()},'已放弃本次尝试，停止接收动作。');});
  // Status polling never cancels an in-flight request or overwrites an edit.
  // The server can finish a budget while the agent is thinking elsewhere.
  let pollingStatus=false;
  const statusTimer=setInterval(async()=>{
    if(!token||!connected||busy||pollingStatus||terminal.has(state.status))return;
    pollingStatus=true;
    try {
      const update=await request('/api/state');
      if(busy||terminal.has(state.status)||!Object.hasOwn(statusLabels,update.status)||update.status===state.status)return;
      invalidatePublicObservation();state.status=update.status;
      if(Number.isInteger(update.steps))state.steps=update.steps;
      $('status').textContent=statusLabels[state.status];
      $('status-dot').className='status-dot'+(terminal.has(state.status)?' stopped':' connected');
      $('budget').textContent=(Number.isInteger(state.steps)?state.steps:'—')+' / '+(Number.isInteger(state.max_actions)?state.max_actions:'—')+' 次物理动作';
      renderControls();
      if(terminal.has(state.status))notice('本次操作已经结束。','neutral');
    } catch (_) {
      // A background read failure must not turn a still-running action into a
      // terminal fault. Foreground interaction remains the authoritative path.
    } finally {pollingStatus=false;}
  },1000);
  window.addEventListener('beforeunload',()=>clearInterval(statusTimer));
  window.addEventListener('beforeunload',()=>{if(demoUrl)URL.revokeObjectURL(demoUrl);});
  refresh();
})();
