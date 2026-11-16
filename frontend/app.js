// WaitWise v0.1 — deliberately dependency-free: edit HTML templates and CSS live.
const app = document.querySelector('#app');
const toastEl = document.querySelector('#toast');
const state = {
  dashboard: null, ticket: null, route: location.pathname === '/staff' ? 'staff' : 'customer',
  filter: 'all', pin: sessionStorage.getItem('waitwise_admin_pin') || '',
  ticketId: Number(localStorage.getItem('waitwise_ticket_id')) || null,
  busy: false, editingArrival: false,
  draft: { name: '', party: 2, phone: '', arrival: initialArrival(), pin: '' }
};

function initialArrival(){
  const d = new Date(Date.now()+70*60000);
  return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);
}
function esc(x){return String(x ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmt(iso){return iso ? new Date(iso).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}) : '--:--';}
function fmtDate(iso){return iso ? new Date(iso).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric'})+' '+fmt(iso) : '--';}
function localInput(iso){const d = new Date(iso);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}
function ago(iso){const now=state.dashboard?.now ? new Date(state.dashboard.now) : new Date();const diff=Math.round((now-new Date(iso))/60000);return diff<=0?'刚刚':diff<60?`${diff} 分钟前`:`${Math.round(diff/60)} 小时前`;}
const activeStatus = ['WAITING','DEFERRED','CALLED','SEATED'];
function stateChip(t){const map={WAITING:['排队中','wait'],DEFERRED:['暂缓候位','warn'],CALLED:['正在叫号','call'],SEATED:['已入座','wait'],COMPLETED:['已完成','dark'],CANCELLED:['已取消','bad'],EXPIRED:['已过期','bad']};let [txt,cls]=map[t.status]||['未知状态','dark'];if(t.status==='WAITING'&&t.checked_in_at)txt=t.priority?'已到店 · 优先':'已到店';return `<span class="status ${cls}">${txt}</span>`;}
function icon(name,size=18){const p={
  plate:'<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="5.3"/><path d="M3 3v7M1 4v4M5 4v4M21 3v18"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  check:'<path d="m4 12 5 5L20 6"/>',
  bell:'<path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  spark:'<path d="m12 3 1.9 6.1L20 11l-6.1 1.9L12 19l-1.9-6.1L4 11l6.1-1.9L12 3Z"/>',
  wifi:'<path d="M2 9a15 15 0 0 1 20 0M5 13a10 10 0 0 1 14 0M8.5 16.5a5 5 0 0 1 7 0M12 20h.01"/>',
  table:'<rect x="3" y="6" width="18" height="5" rx="1"/><path d="M6 11v9m12-9v9"/>',
  phone:'<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3-8.7A2 2 0 0 1 4.2 2h3a2 2 0 0 1 2 1.7c.13.95.36 1.88.7 2.78a2 2 0 0 1-.45 2.11L8.2 9.8a16 16 0 0 0 6 6l1.2-1.25a2 2 0 0 1 2.11-.45c.9.34 1.83.57 2.78.7A2 2 0 0 1 22 16.9Z"/>',
  chevron:'<path d="m9 18 6-6-6-6"/>',
  refresh:'<path d="M20 11a8 8 0 0 0-14-5L3 9m0-6v6h6M4 13a8 8 0 0 0 14 5l3-3m0 6v-6h-6"/>',
  edit:'<path d="m15 5 4 4M4 20l4.5-1 11-11a2.8 2.8 0 0 0-4-4l-11 11L4 20Z"/>',
 }[name]||'<circle cx="12" cy="12" r="8"/>';
 return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;}
function brand(){return `<a class="brand" href="/" data-nav="customer"><span class="brand-logo">${icon('plate',22)}</span>候一会 <small>WAITWISE</small></a>`;}
function shell(body){return `<div class="app-shell"><header class="topbar"><div class="wrap nav-inner">${brand()}<nav class="nav-right" aria-label="主导航"><button data-nav="customer" class="nav-link ${state.route==='customer'?'active':''}">顾客取号</button><button data-nav="staff" class="nav-link ${state.route==='staff'?'active':''}">商家工作台</button><span class="nav-badge">DEMO · V0.1</span></nav></div></header>${body}<footer class="footer">候一会 WaitWise © 2026 · 课程设计演示项目 · 非真实餐厅取号平台</footer></div>`;}
function hero(){return `<section class="hero"><div class="hero-copy"><div class="eyebrow">SMART QUEUING, LESS WAITING</div><h1>好饭值得等，<br/><span class="accent">但不必傻等。</span></h1><p class="hero-sub">提前取号，告诉我们你何时到店。就算提前叫到了，也能优雅地继续排队。把时间留给喜欢的事情，把座位留给刚好到店的你。</p><div class="hero-tags"><span class="hero-tag"><i></i>提前线上取号</span><span class="hero-tag"><i></i>到店时间确认</span><span class="hero-tag"><i></i>30 分钟宽限期</span></div></div><div class="hero-art" aria-label="餐厅候位插画"><div class="art-top"><span class="dot"></span> 拾味餐厅 · 今日营业中</div><div class="plate"><div class="plate-label"><span>GOOD FOOD</span><b>候一会</b><span>WAITWISE</span></div></div><div class="float-card float-left"><div class="f-small">当前候位中</div><div class="f-main"><span class="tiny-circ">${icon('users',17)}</span>${state.dashboard?.stats.waiting ?? 6} 桌在等</div></div><div class="float-card float-right"><div class="f-small">温柔提醒</div><div class="f-main"><span class="tiny-circ">${icon('clock',17)}</span> 不用干等</div></div></div></section>`;}
function customerForm(){let t=state.ticket;let active= t && activeStatus.includes(t.status);return `<article class="card take-card"><div class="card-head"><div><h3 class="card-title">先取个号吧 <span style="color:#e7864d">✳</span></h3><div class="card-sub" style="margin-top:6px">简单几步，开启今天的美味之旅</div></div><span class="status wait">当前可取号</span></div><div class="form-row"><div class="field"><p class="mini-label">怎么称呼你？</p><input id="guest-name" class="input" maxlength="24" autocomplete="name" placeholder="例如：林小姐" value="${esc(state.draft.name)}" ${active?'disabled':''}/></div><div class="field"><p class="mini-label">用餐人数</p><div class="counter"><button aria-label="减少人数" class="count-btn" data-action="party-minus" ${active||state.draft.party<=1?'disabled':''}>−</button><span class="count-num">${state.draft.party}<span class="count-suffix">人</span></span><button aria-label="增加人数" class="count-btn" data-action="party-plus" ${active||state.draft.party>=6?'disabled':''}>+</button></div></div></div><div class="field"><p class="mini-label">你预计几点到店？</p><input type="datetime-local" class="input" id="arrival-at" value="${esc(state.draft.arrival)}" ${active?'disabled':''}/><p class="field-hint">这是预计到达时间，并非保证入座时间。请留意实际叫号进度。</p></div><div class="field"><p class="mini-label">联系电话 <span style="font-weight:400;color:#a5b2a9">（演示可不填）</span></p><input id="guest-phone" class="input" type="tel" placeholder="用于未来接入真实电话服务" value="${esc(state.draft.phone)}" ${active?'disabled':''}/></div><button class="primary full" data-action="take" ${active?'disabled':''}>${active?'已有进行中的候位 · 可取消后重新取号':'立即取号　 '+icon('arrow',16)}</button><p class="micro">* 演示版使用模拟电话确认，不会实际拨打电话</p></article>`;}
function ticketSection(){let t=state.ticket;if(!t)return `<article class="card ticket-card"><div class="card-head"><h3 class="card-title">我的候位卡</h3><span class="status dark">尚未取号</span></div><div class="ticket-empty"><div class="ticket-illustration">🎫</div><h3>你的美味，还差一个号码</h3><p>左边填写人数和预计到店时间，取号后就可以在这里实时查看进度。</p></div></article>`;
let statusText=t.status==='DEFERRED'?'已提前轮到你，暂缓候位':t.status==='CALLED'?'正在叫号，请联系服务员':t.status==='SEATED'?'已入座，祝用餐愉快':t.status==='COMPLETED'?'本次用餐已完成':t.status==='EXPIRED'?'到店宽限期已结束':t.status==='CANCELLED'?'本次候位已取消':t.checked_in_at?'已登记到店，等待安排':'已取号，等待叫号';
let phonePrompt=t.phone_requested_at&&!t.phone_response&&!t.checked_in_at&&['WAITING','DEFERRED'].includes(t.status);
let canArrive=['WAITING','DEFERRED'].includes(t.status)&&!t.checked_in_at;
let canCancel=['WAITING','DEFERRED'].includes(t.status);
return `<article class="card ticket-card"><div class="card-head"><div><h3 class="card-title">我的候位卡</h3><div class="card-sub" style="margin-top:6px">${esc(statusText)}</div></div>${stateChip(t)}</div><div class="ticket-display"><div class="ticket-meta">拾味餐厅 · ${t.party_size<=2?'双人桌':t.party_size<=4?'四人桌':'多人桌'}</div><div class="ticket-code">${esc(t.number)}</div><div class="ticket-meta">${esc(t.name)} · ${t.party_size} 位用餐</div><div class="ticket-divider"></div><div class="ticket-detail-grid"><div><span>预计到店</span><strong>${fmtDate(t.arrival_at)}</strong></div><div><span>排队状态</span><strong>${t.status==='WAITING'||t.status==='DEFERRED' ? '前方约 '+(t.ahead??'--')+' 桌' : esc(statusText)}</strong></div><div><span>到店确认</span><strong>${t.checked_in_at?'已确认 · '+fmt(t.checked_in_at):'尚未确认'}</strong></div><div><span>宽限截止</span><strong>${fmt(new Date(new Date(t.arrival_at).getTime()+30*60*1000).toISOString())}</strong></div></div></div>
${phonePrompt?`<div class="notice"><strong>☎ 模拟电话确认</strong><div>已到你的预计到店时间。你能在 10 分钟内赶到餐厅吗？</div><div class="action-row"><button class="primary green" data-action="phone-yes">可以，10 分钟内到</button><button class="ghost" data-action="phone-no">暂时赶不到</button></div></div>`:''}
${t.priority?'<div class="notice"><strong>你已获得优先候位资格</strong><div>此前提前叫号时你还未到店，现已在约定宽限期内到店；系统会在下一张合适的空桌出现时优先安排。</div></div>':''}
<div class="ticket-actions">${canArrive?`<button class="primary green" data-action="arrive">${icon('check',14)} 我已到店</button>`:''}${canCancel?`<button class="ghost danger-ghost" data-action="cancel">取消取号</button>`:''}${!activeStatus.includes(t.status)?`<button class="ghost" data-action="forget-ticket">查看新的取号表单</button>`:''}</div>
${canCancel?`<div class="ticket-actions"><button class="ghost" data-action="edit-arrival">${icon('edit',13)} 修改预计到店时间</button></div>`:''}
${state.editingArrival?`<div class="notice"><strong>调整预计到店时间</strong><input class="input" id="new-arrival" type="datetime-local" value="${localInput(t.arrival_at)}" style="margin-top:8px"/><button data-action="save-arrival" class="primary green" style="margin-top:8px">保存修改</button></div>`:''}
${t.notifications?.length?`<div style="margin-top:16px;padding-top:12px;border-top:1px solid #eef2ec"><div class="mini-label">最近提醒</div>${t.notifications.slice(0,2).map(n=>`<div style="font-size:11px;color:#84978a;margin:8px 0">• ${esc(n.title)} · ${fmt(n.created_at)}</div>`).join('')}</div>`:''}</article>`;}
function customerPage(){let stats=state.dashboard?.stats||{};return shell(`<main class="wrap">${hero()}<div class="section-heading"><div><p class="kicker">YOUR TABLE IS WAITING</p><h2 class="section-title">从这里开始候位</h2></div><span class="section-desc">拾味餐厅 · 演示门店</span></div><section class="main-grid">${customerForm()}${ticketSection()}</section><section class="metrics"><article class="metric"><div class="metric-icon">${icon('users',22)}</div><div><div class="metric-num">${stats.waiting??'--'} <span style="font-size:12px;color:#889b8e">桌</span></div><div class="metric-text">当前排队</div></div></article><article class="metric"><div class="metric-icon">${icon('check',22)}</div><div><div class="metric-num">${stats.free_tables??'--'} <span style="font-size:12px;color:#889b8e">张</span></div><div class="metric-text">当前空桌</div></div></article><article class="metric"><div class="metric-icon">${icon('bell',22)}</div><div><div class="metric-num">${stats.called??'--'} <span style="font-size:12px;color:#889b8e">桌</span></div><div class="metric-text">正在叫号</div></div></article></section><section class="card process-card"><div class="process-top"><h3>你可能想知道 · 怎么候位？</h3><span class="card-sub">从取号到入座，每一步都更从容</span></div><div class="process-steps">${[['01','提前取号','填写人数及预计到店时间'],['02','实时排队','随时了解最新候位进度'],['03','到店确认','预计时间到后模拟电话提醒'],['04','优先入座','提前过号可在宽限期内恢复优先']].map(a=>`<div class="process-step"><div class="step-index">${a[0]}</div><div><b>${a[1]}</b><p>${a[2]}</p></div></div>`).join('')}</div></section></main>`);}
function loginPage(){return shell(`<main class="wrap"><div class="card login-wrap"><div class="avatar">${icon('table',29)}</div><p class="kicker">RESTAURANT WORKSPACE</p><h2>商家工作台</h2><p>输入演示 PIN，查看顾客候位队列、实时叫号和桌位使用情况。</p><div class="field"><div class="mini-label">商家演示 PIN</div><input id="staff-pin" type="password" class="input" placeholder="例如 123456" value="${esc(state.draft.pin)}"/></div><button class="primary green full" data-action="staff-login">进入工作台　${icon('arrow',16)}</button><p class="micro">演示 PIN：123456 · 正式部署需接入独立账户与权限系统</p></div></main>`);}
function ticketsTable(){let rows=(state.dashboard?.tickets||[]).filter(t=>state.filter==='all'?true:state.filter==='arrived'?t.status==='WAITING'&&t.checked_in_at:state.filter==='absent'?['WAITING','DEFERRED'].includes(t.status)&&!t.checked_in_at:t.status==='CALLED');
return `<article class="card staff-panel"><div class="panel-head"><div><h3>实时候位队列</h3><small>按取号顺序排列 · 自动跳过未到店顾客</small></div></div><div class="panel-head"><div class="tabs">${[['all','全部'],['arrived','已到店'],['absent','未到店'],['called','已叫号']].map(([key,label])=>`<button class="tab ${state.filter===key?'active':''}" data-filter="${key}">${label}</button>`).join('')}</div><small>${rows.length} 条记录</small></div><div style="overflow-x:auto"><table class="queue-table"><thead><tr><th>号码 / 顾客</th><th>人数</th><th>预计到店</th><th>取号时间</th><th>当前状态</th></tr></thead><tbody>${rows.map(t=>`<tr><td><strong>${esc(t.number)}</strong><div class="td-sub">${esc(t.name)}</div></td><td>${t.party_size} 位</td><td>${fmt(t.arrival_at)}</td><td>${fmt(t.created_at)}</td><td>${stateChip(t)}</td></tr>`).join('')}</tbody></table>${rows.length?'':'<div class="queue-empty">此分组暂无候位记录</div>'}</div></article>`;}
function tablesPanel(){let tables=state.dashboard?.tables||[];return `<article class="card staff-panel"><div class="panel-head"><h3>餐桌状态</h3><small>按空桌直接叫号</small></div><div class="table-grid">${tables.map(t=>{let label=t.status==='FREE'?'可安排':t.status==='HELD'?'等待入座':'正在用餐';let ticket=t.ticket;return `<div class="table-tile ${t.status.toLowerCase()}"><div class="table-tile-head"><b>${esc(t.name.split(' · ')[0])}</b><span class="status ${t.status==='FREE'?'wait':t.status==='HELD'?'warn':'dark'}">${label}</span></div><div class="meta">${t.capacity} 人桌 · ${ticket?`${esc(ticket.number)} ${esc(ticket.name)}`:'暂无占用'}</div><div class="tile-bottom">${t.status==='FREE'?`<button class="small-btn" data-action="call-next" data-id="${t.id}">智能叫号 →</button>`:t.status==='HELD'?`<button class="small-btn" data-action="seat" data-id="${ticket.id}">确认入座</button><button class="small-btn neutral" data-action="skip" data-id="${ticket.id}">未到</button>`:`<button class="small-btn orange" data-action="finish" data-id="${t.id}">结束用餐</button>`}</div></div>`;}).join('')}</div></article>`;}
function eventsPanel(){let events=state.dashboard?.events||[];return `<article class="card staff-panel"><div class="panel-head"><h3>事件动态</h3><small>业务事件持久化记录</small></div><div class="event-list">${events.slice(0,7).map(e=>{let message;try{message=JSON.parse(e.payload).message}catch{message=e.type}return `<div class="event"><span class="event-mark"></span><div><div class="event-body">${esc(message)}</div><div class="event-time">${ago(e.created_at)} · ${esc(e.type)}</div></div></div>`}).join('')||'<div class="queue-empty">暂无事件</div>'}</div></article>`;}
function demoPanel(){return `<div class="demo-tools"><h4>◷　演示控制台</h4><p>无需真的等待 30 分钟。在这里快进演示时钟，体验到店电话提醒和宽限期过期。时间快进不修改真实系统时间。</p><div class="demo-buttons"><button class="ghost" data-action="advance" data-minutes="10">+10 分钟</button><button class="ghost" data-action="advance" data-minutes="30">+30 分钟</button><button class="ghost danger-ghost" data-action="reset">重置演示数据</button></div></div>`;}
function staffPage(){if(!state.pin)return loginPage();const s=state.dashboard?.stats||{};return shell(`<main class="wrap staff-page"><div class="staff-titlebar"><div><p class="kicker">RESTAURANT CONTROL CENTER</p><h1>午后好，今天也要高效翻台。</h1><p>拾味餐厅 · 候位调度工作台 · 演示时钟 ${fmt(state.dashboard?.now)} （北京时间）</p></div><div class="staff-tools"><button class="ghost" data-action="refresh">${icon('refresh',14)} 刷新</button><button class="ghost" data-action="staff-logout">退出商家端</button></div></div><section class="staff-summary"><article class="card stat"><span class="hint">当前等待</span><strong>${s.waiting??'--'}</strong><small>位候位顾客</small></article><article class="card stat"><span class="hint">已到店</span><strong>${s.arrived??'--'}</strong><small>待安排入座</small></article><article class="card stat"><span class="hint">空闲餐桌</span><strong>${s.free_tables??'--'}</strong><small>可以立即叫号</small></article><article class="card stat"><span class="hint">正在用餐</span><strong>${s.seated??'--'}</strong><small>桌正在使用</small></article></section><div class="staff-columns">${ticketsTable()}<div class="stack">${tablesPanel()}${eventsPanel()}${demoPanel()}</div></div></main>`);}
function render(){app.innerHTML=state.route==='staff'?staffPage():customerPage();}
async function api(path,method='GET',body=null,admin=false){const headers={};if(body!==null)headers['Content-Type']='application/json';if(admin)headers['X-Admin-Pin']=state.pin;const res=await fetch('/api'+path,{method,headers,body:body===null?undefined:JSON.stringify(body)});let data;try{data=await res.json()}catch{data={}}if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:'网络请求失败');return data;}
async function refresh(){let token=state.route==='staff'&&state.pin;state.dashboard=await api('/dashboard','GET',null,token);if(state.ticketId){try{state.ticket=await api('/tickets/'+state.ticketId)}catch(e){if(e.message.includes('未找到')){state.ticket=null;state.ticketId=null;localStorage.removeItem('waitwise_ticket_id');}}}
  // Form inputs must not lose focus during a background poll.
  if(!['INPUT','TEXTAREA'].includes(document.activeElement?.tagName||''))render();}
let toastTimer;
function toast(text){toastEl.textContent=text;toastEl.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toastEl.classList.remove('show'),3100);}
function setRoute(route){state.route=route;history.pushState({},'',route==='staff'?'/staff':'/');refresh().catch(e=>toast(e.message));render();window.scrollTo({top:0,behavior:'smooth'});}
window.addEventListener('popstate',()=>{state.route=location.pathname==='/staff'?'staff':'customer';refresh().catch(e=>toast(e.message));render()});
document.addEventListener('input',e=>{if(e.target.id==='guest-name')state.draft.name=e.target.value;if(e.target.id==='guest-phone')state.draft.phone=e.target.value;if(e.target.id==='arrival-at')state.draft.arrival=e.target.value;if(e.target.id==='staff-pin')state.draft.pin=e.target.value;});
document.addEventListener('click',async e=>{
  const nav=e.target.closest('[data-nav]');if(nav){e.preventDefault();setRoute(nav.dataset.nav);return;}
  const btn=e.target.closest('[data-action],[data-filter]');if(!btn||state.busy)return;
  if(btn.dataset.filter){state.filter=btn.dataset.filter;render();return;}
  const action=btn.dataset.action; if(action==='party-plus'){state.draft.party=Math.min(6,state.draft.party+1);render();return;}if(action==='party-minus'){state.draft.party=Math.max(1,state.draft.party-1);render();return;}
  if(action==='edit-arrival'){state.editingArrival=!state.editingArrival;render();return;}
  if(action==='forget-ticket'){state.ticket=null;state.ticketId=null;localStorage.removeItem('waitwise_ticket_id');render();return;}
  if(action==='staff-logout'){sessionStorage.removeItem('waitwise_admin_pin');state.pin='';state.dashboard=null;render();return;}
  try{
    state.busy=true;btn.disabled=true;
    const id=Number(btn.dataset.id);
    if(action==='take'){
      if(!state.draft.name.trim())throw new Error('先填写一个称呼吧');
      if(!state.draft.arrival)throw new Error('请选择预计到店时间');
      const ticket=await api('/tickets','POST',{name:state.draft.name.trim(),party_size:state.draft.party,phone:state.draft.phone,arrival_at:new Date(state.draft.arrival).toISOString(),request_id:crypto.randomUUID()});
      state.ticketId=ticket.id;localStorage.setItem('waitwise_ticket_id',ticket.id);toast(`取号成功，你的号码是 ${ticket.number}`);
    } else if(action==='arrive'){await api(`/tickets/${state.ticketId}/arrive`,'POST');toast('到店登记成功！');}
    else if(action==='cancel'){if(!confirm('确定取消这次候位吗？'))return;await api(`/tickets/${state.ticketId}/cancel`,'POST');toast('已取消候位');}
    else if(action==='phone-yes'||action==='phone-no'){await api(`/tickets/${state.ticketId}/phone-reply`,'POST',{response:action==='phone-yes'?'on_way':'cant'});toast('已记录模拟电话回复');}
    else if(action==='save-arrival'){const v=document.querySelector('#new-arrival')?.value;if(!v)throw new Error('请选择时间');await api(`/tickets/${state.ticketId}/arrival`,'POST',{arrival_at:new Date(v).toISOString()});state.editingArrival=false;toast('预计到店时间已更新');}
    else if(action==='staff-login'){
      state.pin=state.draft.pin;
      await api('/admin/verify','POST',null,true);
      sessionStorage.setItem('waitwise_admin_pin',state.pin);toast('已进入商家演示工作台');
    }
    else if(action==='refresh'){toast('候位状态已刷新');}
    else if(action==='call-next'){let r=await api('/admin/call-next','POST',{table_id:id},true);toast(r.ticket?`已叫号：${r.ticket.number}`:r.message);}
    else if(action==='seat'){let r=await api(`/admin/seat/${id}`,'POST',null,true);toast(`${r.number} 已确认入座`);}
    else if(action==='skip'){await api(`/admin/skip/${id}`,'POST',null,true);toast('已暂缓此顾客并释放桌位');}
    else if(action==='finish'){await api('/admin/finish','POST',{table_id:id},true);toast('已结束用餐，桌位重新开放');}
    else if(action==='advance'){await api('/admin/time-travel','POST',{minutes:Number(btn.dataset.minutes)},true);toast(`演示时钟已快进 ${btn.dataset.minutes} 分钟`);}
    else if(action==='reset'){if(!confirm('重置会清空演示记录，并重新生成样例顾客。确定吗？'))return;await api('/admin/reset-demo','POST',null,true);state.ticketId=null;state.ticket=null;localStorage.removeItem('waitwise_ticket_id');toast('已重置演示数据');}
    await refresh();
  }catch(err){toast(err.message||'操作失败');}
  finally{state.busy=false;render();}
});
refresh().catch(err=>{app.innerHTML=`<div class="boot">无法连接后端：${esc(err.message)}<br>请确认已启动 <code>./start.sh</code></div>`;});
setInterval(()=>{if(!state.busy)refresh().catch(()=>{})},5000);
