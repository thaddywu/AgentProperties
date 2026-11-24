const $ = (selector) => document.querySelector(selector);
const names = {message: 'Message', tool_call: 'Tool call', tool_result: 'Tool result', llm_call: 'LLM call', llm_result: 'LLM output', llm_output: 'LLM output', state: 'State', decision: 'Event'};
let log = null, token = '', activeRole = '', selected = '', ticket = 0;
let callTicket = 0, callTemplate = '';
let capabilities = {}, view = 'details', phase = 'before', inspection = null, inspectionTicket = 0;

function setTheme(theme) {
  document.documentElement.dataset.theme=theme;
  $('#theme').setAttribute('aria-pressed',String(theme==='dark'));
  try {localStorage.setItem('policyweave-inspector-theme',theme);} catch {}
}
try {
  const saved=localStorage.getItem('policyweave-inspector-theme');
  setTheme(saved==='dark' || saved==='light' ? saved : (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
} catch {setTheme('light');}
$('#theme').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark' ? 'light' : 'dark'));

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (cls) node.className = cls;
  return node;
}
function name(id) { return log.roles.find((r) => r.id === id)?.name ?? id; }
function participantKind(id) {return log.roles.find((role)=>role.id===id)?.kind || 'agent';}
function messageLabel(event) {
  const phase=event.messagePhase || event.data?.phase || ({message_sent:'sent',message_received:'received'}[event.data?.nativeKind]);
  return phase==='sent' ? 'Message send' : phase==='received' ? 'Message receipt' : 'Message';
}
function route(event) {
  if (event.kind === 'message') return event.recipients.length ? event.recipients.map(name).join(', ') : 'Recipient not recorded';
  return event.tool || event.data?.request?.action || '';
}
async function post(operation, value) {
  const raw=operation==='import' && value instanceof Blob;
  const response = await fetch('/api/analysis/' + operation, {method: 'POST', headers: {'Content-Type': raw ? 'application/octet-stream' : 'application/json', 'X-Study-Token': token}, body: raw ? value : JSON.stringify(value), ...(operation==='explain' ? {signal:AbortSignal.timeout(15000)} : {})});
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Could not read this trajectory.');
  return data;
}
function fail(error) { $('#status').textContent = error.message || 'Could not read this trajectory.'; }
function activityKind(event) {return event.category==='tool' ? 'tool_call' : event.category==='model' ? 'llm_output' : event.kind;}
function primary(event) {return event.primary!==false && (participantKind(event.actor)==='agent' || (event.kind==='message' && participantKind(event.actor)==='user'));}
function renderKinds() {
  const current=$('#kind').value, all=$('#all-events').checked;
  $('#kind').replaceChildren(new Option('All activity',''));
  for(const kind of new Set(log.events.filter((event)=>all || primary(event)).map((event)=>all ? event.kind : activityKind(event))))$('#kind').append(new Option(names[kind],kind));
  if([...$('#kind').options].some((option)=>option.value===current))$('#kind').value=current;
}
function visible() {
  const kind = $('#kind').value, search = $('#search-events').value.toLocaleLowerCase();
  const all=$('#all-events').checked;
  return log.events.filter((e) => (all || primary(e)) && (!activeRole || e.actor === activeRole || (e.recipients || []).includes(activeRole)) && (!kind || (all ? e.kind : activityKind(e))===kind) && (!search || [e.id,e.actor,e.title,e.preview,e.tool].join(' ').toLocaleLowerCase().includes(search)));
}
function badge(value) {
  const labels={blocked:'Blocked',applied:'Checked',not_applied:'Not applied',unknown:'Execution uncertain',failed:'Failed',allowed:'Allowed'};
  const node = el('span', labels[value] || value, 'badge');
  if (['applied', 'blocked', 'unknown', 'not_applied', 'failed'].includes(value)) node.classList.add(value);
  return node;
}
function renderRoles() {
  const roles = $('#roles'); roles.replaceChildren();
  $('.sidebar-label').textContent=$('#all-events').checked ? 'Participants' : 'Agents';
  for (const role of [{id: '', name: 'All agents'}, ...log.roles.filter((role)=>$('#all-events').checked || !role.kind || role.kind==='agent')]) {
    const button = el('button', undefined, 'role');
    button.type = 'button'; button.setAttribute('aria-pressed', String(role.id === activeRole));
    button.setAttribute('aria-label', (role.kind && role.kind!=='agent' ? 'Filter participant ' : 'Filter agent ') + role.name);
    button.append(el('span', role.id ? role.name.slice(0, 2).toUpperCase() : '∗', 'avatar'));
    const label = el('span', role.name);
    if (role.role || (role.kind && role.kind!=='agent')) label.append(el('small', role.role || role.kind));
    button.append(label);
    button.addEventListener('click', () => {activeRole = role.id; renderRoles(); renderEvents();});
    roles.append(button);
  }
}
function renderEvents(preferred) {
  if (!log) return;
  const events = visible(), container = $('#events'); container.replaceChildren();
  $('#no-events').hidden = events.length > 0;
  $('#position').max = String(Math.max(0, events.length - 1));
  $('#position').disabled = events.length === 0;
  for (const event of events) {
    const button = el('button', undefined, 'event');
    button.type = 'button'; button.dataset.eventId = event.id;
    button.setAttribute('aria-label', 'Event ' + event.sequence + ' ' + name(event.actor) + ' ' + names[event.kind]);
    button.append(el('span', name(event.actor).slice(0,2).toUpperCase(), 'avatar'));
    const body = el('div', undefined, 'event-body'), meta = el('div', undefined, 'event-meta');
    meta.append(el('strong', name(event.actor)), el('span', '#' + event.sequence));
    if (event.outcome) meta.append(badge(event.outcome));
    body.append(meta);
    const path = el('div', undefined, 'event-path');
    if (event.category === 'model') path.append(badge('LLM'), el('span', (event.title || 'LLM call').replace(/^LLM · /, '')));
    else if (event.category === 'tool') path.append(badge('Tool'), el('span', event.title || event.tool, 'tool-name'));
    else if (event.kind === 'message') path.append(badge(messageLabel(event)),el('span', '→', 'arrow'), el('span', route(event)));
    else path.append(badge(names[event.kind]));
    body.append(path);
    if (event.preview && !(event.category === 'tool' && event.preview === event.title)) body.append(el('p', event.preview, 'preview'));
    button.append(body);
    button.addEventListener('click', () => select(event.id)); container.append(button);
  }
  const id = events.find((e) => e.id === preferred)?.id || events.find((e) => e.id === selected)?.id || events[0]?.id;
  if (id) {
    select(id);
    if (preferred) requestAnimationFrame(()=>{
      if (selected===id) for (const button of container.children) if (button.dataset.eventId===id) button.scrollIntoView({block:'center'});
    });
  }
  else {selected = ''; ticket++; inspection=null;inspectionTicket++;resetCallAnalysis('');$('#facts').replaceChildren();$('#fact-status').textContent='No event selected.';$('#position-value').textContent = '—'; $('#detail').replaceChildren(el('p', 'No event selected.', 'subtle'));}
}
async function select(id) {
  const changed=id!==selected;
  if (changed) {inspection = null; inspectionTicket++; resetCallAnalysis(id);}
  selected = id; const current = ++ticket, identity = log.id;
  for (const button of $('#events').children) button.setAttribute('aria-current', String(button.dataset.eventId === id));
  const events = visible(), event = events.find((e) => e.id === id);
  $('#position').value = String(Math.max(0, events.findIndex((e) => e.id === id)));
  $('#position-value').textContent = event ? '#' + event.sequence : '—';
  $('#detail').setAttribute('aria-busy', 'true');
  try {
    const result = await post('event', {trajectoryId: identity, eventId: id});
    if (current !== ticket || log.id !== result.trajectoryId) return;
    renderDetail(result.result, result.enforcement); $('#status').textContent = '';
    if(changed || !callTemplate)renderCallQuestions(result.callQuestions || []);
    if (view==='evidence') loadInspection();
  } catch (error) { if (current === ticket) fail(error); }
  finally {if (current === ticket) $('#detail').setAttribute('aria-busy', 'false');}
}
function fields(value, depth = 0) {
  if (value === null || value === undefined) return el('span', '—', 'subtle');
  if (typeof value !== 'object') return el('span', typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value), 'data-value');
  if (depth > 6) return el('span', 'Further nested values are available in the export.', 'subtle');
  if (Array.isArray(value)) {
    if (!value.length) return el('span', 'None', 'subtle');
    if (value.every((v) => typeof v !== 'object')) return el('span', value.join(', '), 'data-value');
    const list = el('ol', undefined, 'data-list');
    for (const item of value.slice(0,30)) {const li = el('li'); li.append(fields(item, depth+1)); list.append(li);}
    if (value.length > 30) list.append(el('li', (value.length-30) + ' more values in the export.', 'subtle'));
    return list;
  }
  const dl = el('dl', undefined, 'data-fields');
  const entries=Object.entries(value);
  for (const [key,item] of entries.slice(0,40)) {
    const row = el('div', undefined, 'data-field'), dd = el('dd');
    row.append(el('dt', key.replace(/_/g,' ').replace(/([a-z])([A-Z])/g,'$1 $2')));
    if (item && typeof item === 'object') row.classList.add('data-nested');
    if (item && typeof item === 'object' && (depth>=1 || Object.keys(item).length > 6)) {
      const details = el('details', undefined, 'data-object'); details.append(el('summary', Array.isArray(item) ? item.length + ' values' : Object.keys(item).length + ' fields'), fields(item,depth+1)); dd.append(details);
    } else dd.append(fields(item,depth+1));
    row.append(dd); dl.append(row);
  }
  if (entries.length>40) dl.append(el('p',(entries.length-40)+' more fields in the export.','subtle'));
  return dl;
}
function labeled(parent, title, value) {parent.append(el('div', title, 'section-label'), fields(value));}
function resultDetails(parent, value) {
  const details=el('details',undefined,'detail-section');details.append(el('summary','Result'),fields(value));parent.append(details);
}
function jump(id) {
  activeRole = ''; $('#kind').value = ''; $('#search-events').value = '';
  if (log.events.find((e) => e.id === id)?.primary === false) $('#all-events').checked = true;
  renderKinds();
  renderRoles(); renderEvents(id); setTab('details');
  for (const button of $('#events').children) if (button.dataset.eventId === id) button.scrollIntoView({block: 'nearest'});
}
function gateDetails(parent, data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return;
  const decision=data.decision && typeof data.decision==='object' ? data.decision : data;
  const outcome=data.outcome || (decision.allowed===true ? 'allowed' : decision.allowed===false ? 'blocked' : 'Not recorded');
  const status=el('div',undefined,'call-outcome'),mark=badge(outcome);
  if(decision.allowed===true && ['not_applied','unknown','failed'].includes(outcome))mark.textContent='Allowed · '+mark.textContent.toLocaleLowerCase();
  status.append(mark);parent.append(status);
  for (const reason of Array.isArray(decision.reasons) ? decision.reasons : []) parent.append(el('p',reason,'reason'));
}
function contentValue(value) {
  if (typeof value !== 'string') return fields(value);
  try {const parsed=JSON.parse(value);if(parsed && typeof parsed==='object')return fields(parsed,1);}catch{}
  return el('div',value,'content');
}
function renderDetail(event, enforcement) {
  const detail=$('#detail');detail.replaceChildren();
  const meta=log.events.find((e)=>e.id===event.id),data=event.data && typeof event.data==='object' ? event.data : {};
  const model=meta.category==='model',response=event.kind.endsWith('_result') || event.kind==='llm_output' || data.nativeKind==='decision_summary';
  const head=el('div',undefined,'detail-head');head.append(badge(model ? 'LLM output' : meta.category==='tool' ? 'Tool call' : event.kind==='message' ? messageLabel(event) : names[event.kind]),el('span','#'+event.sequence));detail.append(head);
  detail.append(el('div',name(event.actor)+(model && data.inputs?.stage ? ' · '+data.inputs.stage : route(event) ? ' → '+route(event) : ''),'detail-title'));
  if(event.kind==='message') {
    if(data.inputs?.message_type)labeled(detail,'Message type',data.inputs.message_type);
    detail.append(contentValue(event.content));
  } else if(model) {
    const output=['llm_result','llm_output'].includes(event.kind) ? event.result : data.outputs?.assistant ?? data.outputs?.decision;
    if(output!==undefined)labeled(detail,'Model output',output);
    if(data.outputs?.backend_metadata) {const metadata=data.outputs.backend_metadata; labeled(detail,'Model',metadata.response_model || metadata.requested_model || 'Not recorded');if(metadata.provider_reported_tokens!==undefined)labeled(detail,'Reported tokens',metadata.provider_reported_tokens);}
  } else {
    if(data.request?.parameters)labeled(detail,'Arguments',data.request.parameters);
    if(enforcement)gateDetails(detail,enforcement);
    else if(log.format==='policyscope-trajectory')gateDetails(detail,data);
    else if(Array.isArray(data.gates))for(const gate of data.gates)gateDetails(detail,gate);
    else if(typeof data.allowed==='boolean')gateDetails(detail,data);
    if('arguments' in event)labeled(detail,'Arguments',event.arguments);
    if('result' in event)resultDetails(detail,event.result);
    else if(data.request && 'result' in data)resultDetails(detail,data.result);
    if(event.kind==='state' || event.kind==='decision') {
      if(!data.request && data.inputs && Object.keys(data.inputs).length)labeled(detail,'Observed input',data.inputs);
      if(data.outputs && Object.keys(data.outputs).length)labeled(detail,'Observation',data.outputs);
      else if(data.state)labeled(detail,data.observation==='final_state' ? 'Final state' : 'State',data.state);
      else if(meta.category!=='tool' && !data.request && !data.inputs && !data.outputs) {
        const values=Object.fromEntries(Object.entries(data).filter(([key])=>!['gates','parents','sourceRefs','nativeSequence','visibility','origin'].includes(key)));
        if(Object.keys(values).length)labeled(detail,'Observation',values);
      }
    }
  }
  const related=meta.relatedEventId || log.events.find((e)=>e.callId && e.callId===event.callId && e.kind!==event.kind)?.id;
  if(related) {
    const output=el('div');detail.append(output);const identity=log.id;
    if(!response)post('event',{trajectoryId:identity,eventId:related}).then(({result})=>{
      if(selected!==event.id || log.id!==identity)return;
      const value='result' in result ? result.result : result.data?.outputs?.assistant ?? result.data?.outputs?.decision;
      if(model)labeled(output,'Model output',value===undefined ? 'Not recorded' : value);
      else if(value!==undefined)resultDetails(output,value);
      const metadata=result.data?.outputs?.backend_metadata;
      if(model && metadata) {labeled(output,'Model',metadata.response_model || metadata.requested_model || 'Not recorded');if(metadata.provider_reported_tokens!==undefined)labeled(output,'Reported tokens',metadata.provider_reported_tokens);}
    }).catch(fail);
    if(response && !model) {
      const link=el('button','Jump to call','link');link.addEventListener('click',()=>jump(related));detail.append(link);
    }
  }
  else if(!response && model)labeled(detail,'Model output','Not recorded');
}
function setTab(next) {
  view=next;
  for (const button of document.querySelectorAll('[data-tab]')) button.setAttribute('aria-selected',String(button.dataset.tab===view));
  $('#detail').hidden=view!=='details'; $('#evidence-panel').hidden=view!=='evidence'; $('#analysis-tools').hidden=view!=='qa';
  if (view==='evidence' && selected) loadInspection();
}
for (const button of document.querySelectorAll('[data-tab]')) {
  button.addEventListener('click',()=>setTab(button.dataset.tab));
  button.addEventListener('keydown',(event)=>{
    if (!['ArrowLeft','ArrowRight'].includes(event.key)) return;
    event.preventDefault(); const tabs=[...button.closest('[role=tablist]').querySelectorAll('[role=tab]')].filter((b)=>!b.disabled);
    const next=tabs[(tabs.indexOf(button)+(event.key==='ArrowRight' ? 1 : tabs.length-1))%tabs.length]; next.focus(); setTab(next.dataset.tab);
  });
}
async function loadInspection() {
  const current=++inspectionTicket, identity=log.id, eventId=selected;
  $('#fact-status').textContent='Loading…';
  try {
    if (!inspection) {
      const response=await post('inspect',{trajectoryId:identity,eventId,phase,derive:false});
      if (current!==inspectionTicket || selected!==eventId || log.id!==identity) return;
      inspection=response.result;
    }
    $('#fact-status').textContent=''; renderRelations();
  } catch(error) {if(current===inspectionTicket) {$('#fact-status').textContent=error.message;$('#facts').replaceChildren();}}
}
function renderRelations() {
  const box=$('#facts');box.replaceChildren();
  if (!inspection) return;
  $('#snapshot-phase').hidden=inspection.scope!=='gate';
  if (!inspection.available) {$('#fact-status').textContent=inspection.reason;return;}
  if (inspection.scope!=='gate') {
    $('#fact-status').textContent='No database was recorded for this event.';return;
  }
  const groups=[['edb',inspection.edb || []],['idb',inspection.idb || []]];
  for (const [kind,relations] of groups) for (const group of relations) {
    const rows=group.rows;
    const known=kind==='edb' || inspection.idbStatus==='recomputed' || (inspection.recordedPredicates || []).includes(group.name);
    const details=el('details',undefined,'relation');details.open=Boolean(rows.length && ['Deny','Allow','Field','Event','Request','Parameter'].includes(group.name));
    details.dataset.predicate=group.name;
    const summary=el('summary',group.name);summary.append(el('span',known ? rows.length : 'Not recorded'));details.append(summary);
    if (group.meaning) details.append(el('p',group.meaning,'relation-meaning'));
    if (!rows.length) details.append(el('p',known ? 'No rows' : 'Not recorded','relation-empty'));
    else {
      const scroll=el('div',undefined,'table-scroll'),table=el('table'),thead=el('thead'),tr=el('tr');
      for (const column of group.columns) tr.append(el('th',column));thead.append(tr);table.append(thead);
      const tbody=el('tbody');
      for (const row of rows) {const tr=el('tr');for(const value of row)tr.append(el('td',value));tbody.append(tr);}table.append(tbody);scroll.append(table);details.append(scroll);
    }
    box.append(details);
  }
}
for (const button of document.querySelectorAll('[data-phase]')) button.addEventListener('click',()=>{
  phase=button.dataset.phase;inspection=null;
  for (const other of document.querySelectorAll('[data-phase]')) other.setAttribute('aria-pressed',String(other===button));
  loadInspection();
});
function setLog(value, preferred) {
  log = value; activeRole = ''; selected = ''; ticket++; inspection=null;inspectionTicket++;
  $('#all-events').checked=false;$('#search-events').value='';
  $('#empty').hidden=Boolean(log);$('#workspace').hidden=!log;$('#export').hidden=!log;
  if (!log) return;
  setTab('details');
  $('#tab-qa').disabled=!capabilities.queryAvailable;
  $('#kind').value='';renderKinds();
  renderRoles();renderEvents(preferred || log.events.find((e)=>e.primary!==false && e.outcome==='blocked')?.id);
}
$('#file').addEventListener('change',async()=>{
  const file=$('#file').files[0];if(!file)return;
  try {
    if(file.size>capabilities.maxTrajectoryBytes)throw Error(`Trajectory exceeds ${capabilities.maxTrajectoryBytes/1024/1024} MiB.`);
    const response=await post('import',file);
    $('#status').textContent='';capabilities=response.capabilities || {};history.replaceState({},'','/');$('#export').href='/api/analysis/export';setLog(response.result);
  }catch(error){fail(error);}finally{$('#file').value='';}
});
let serverLogs=[];
function renderLogPicker() {
  const search=$('#log-search').value.toLocaleLowerCase(),box=$('#server-logs');box.replaceChildren();
  for (const item of serverLogs.filter((item)=>item.title.toLocaleLowerCase().includes(search))) {
    const button=el('button',item.title,'server-log');button.type='button';
    button.addEventListener('click',async()=>{
      button.disabled=true;
      try {
        const suffix='?trace='+encodeURIComponent(item.id),response=await fetch('/api/analysis'+suffix),value=await response.json();
        if(!response.ok)throw Error(value.error || 'Could not open this log.');
        capabilities=value;history.replaceState({},'','/'+suffix);$('#export').href='/api/analysis/export'+suffix;
        setLog(value.trajectory);$('#status').textContent='';$('#log-picker').close();
      }catch(error){$('#picker-status').textContent=error.message;}finally{button.disabled=false;}
    });
    box.append(button);
  }
  $('#picker-status').textContent=box.children.length ? '' : 'No matching server logs.';
}
$('#open-log').addEventListener('click',async()=>{
  $('#log-search').value='';$('#server-logs').replaceChildren();$('#picker-status').textContent='Loading…';$('#log-picker').showModal();
  try {
    const response=await fetch('/api/analysis/logs'),value=await response.json();
    if(!response.ok)throw Error(value.error || 'Could not list server logs.');
    serverLogs=value.logs;renderLogPicker();
  }catch(error){$('#picker-status').textContent=error.message;}
});
$('#close-picker').addEventListener('click',()=>$('#log-picker').close());
$('#log-search').addEventListener('input',renderLogPicker);
$('#upload-log').addEventListener('click',()=>{$('#log-picker').close();$('#file').click();});
for(const id of ['kind','all-events']) $('#'+id).addEventListener('change',()=>{if(id==='all-events'){renderRoles();renderKinds();}renderEvents();});
$('#search-events').addEventListener('input',()=>renderEvents());
$('#position').addEventListener('input',()=>{const event=visible()[Number($('#position').value)];if(event){select(event.id);for(const button of $('#events').children)if(button.dataset.eventId===event.id)button.scrollIntoView({block:'nearest'});}});
try {
  const params=new URLSearchParams(location.search),trace=params.get('trace'),suffix=trace ? '?trace='+encodeURIComponent(trace) : '';
  $('#export').href='/api/analysis/export'+suffix;
  const response=await fetch('/api/analysis'+suffix);if(!response.ok)throw Error('Could not open the viewer.');
  const value=await response.json();token=value.token;capabilities=value;setLog(value.trajectory,params.get('event'));
}catch(error){fail(error);}

function resetCallAnalysis(id) {
  callTicket++;
  $('#call-answer').replaceChildren();$('#call-status').textContent='';
  const event=log?.events.find((e)=>e.id===id);
  $('#call-context').textContent=event ? name(event.actor)+' · '+(event.tool || event.title || names[event.kind])+' · #'+event.sequence : 'Select a tool call.';
  callTemplate='';$('#call-suggestions').replaceChildren();$('#call-question').textContent='';
  $('#analyze-call').disabled=true;
}
function renderCallQuestions(questions) {
  const box=$('#call-suggestions');box.replaceChildren();
  for(const item of questions) {
    const button=el('button',item.label);button.type='button';button.dataset.templateId=item.id;
    button.setAttribute('aria-pressed',String(item===questions[0]));
    button.addEventListener('click',()=>{
      callTicket++;callTemplate=item.id;$('#call-question').textContent=item.question;
      for(const other of box.children)other.setAttribute('aria-pressed',String(other===button));
      $('#call-answer').replaceChildren();$('#call-status').textContent='';
      $('#analyze-call').disabled=!capabilities.modelAvailable || !capabilities.queryAvailable;
    });box.append(button);
  }
  callTemplate=questions[0]?.id || '';
  $('#call-question').textContent=questions[0]?.question || 'Select a mediated tool call.';
  $('#analyze-call').disabled=!callTemplate || !capabilities.modelAvailable || !capabilities.queryAvailable;
}
async function analyzeCall() {
  if(!selected || !log)return;
  const identity=log.id,eventId=selected,current=++callTicket,output=$('#call-answer');
  output.replaceChildren();$('#call-status').textContent='Analyzing this call…';$('#analyze-call').disabled=true;
  try {
    const {jobId}=await post('explain',{trajectoryId:identity,eventId,templateId:callTemplate,background:true});
    let response;
    while(current===callTicket && log.id===identity && selected===eventId) {
      const request=await fetch('/api/analysis/jobs/'+encodeURIComponent(jobId),{signal:AbortSignal.timeout(15000)});
      const job=await request.json();
      if(!request.ok)throw Error(job.error || 'Could not read this analysis.');
      if(current!==callTicket || log.id!==identity || selected!==eventId)return;
      if(job.status!=='running') {
        response=job.response;
        if(job.status==='failed')throw Error(response.error);
        break;
      }
      $('#call-status').textContent=job.phase==='explanation' ? 'Explaining this call…' : 'Checking recorded evidence…';
      await new Promise(resolve=>setTimeout(resolve,500));
    }
    if(current!==callTicket || log.id!==identity || selected!==eventId)return;
    const result=response.result;$('#call-status').textContent='';
    if(result.status!=='answered') {
      output.append(el('p',result.clarification || result.unsupported || 'This question needs more recorded evidence.','content'));return;
    }
    output.append(el('div',result.answer,'content analysis-answer'));
    const verdict=el('div');gateDetails(verdict,result.decision);output.append(verdict);
    const evidence=el('button','#'+log.events.find(event=>event.id===eventId).sequence,'link');evidence.addEventListener('click',()=>jump(eventId));output.append(evidence);
    if(result.limitations?.length) {const limits=el('details',undefined,'detail-section');limits.append(el('summary','Evidence limits'));const list=el('ul',undefined,'answer-items subtle');for(const value of result.limitations)list.append(el('li',value));limits.append(list);output.append(limits);}
    const translation=el('details',undefined,'detail-section');translation.append(el('summary','Translation and query'),el('p',result.interpretation,'content'),el('pre',result.query));
    for(const support of result.supportingQueries || []) {
      translation.append(el('p',support.explanation,'content'),el('pre',support.query));
      if(support.displayColumns && support.displayColumns.length<support.columns.length) {
        const all=el('details',undefined,'detail-section');all.append(el('summary','All columns'),queryResult({...support,displayColumns:null},support.explanation));translation.append(all);
      }
    }
    translation.append(el('p','Decision replay matched.','subtle'));
    output.append(queryResult(result,'Query result'));
    for(const support of result.supportingQueries || [])output.append(queryResult(support,support.explanation));
    if(result.effects) {
      const effects=result.effects;
      const recorded=el('details',undefined,'detail-section');recorded.open=true;
      recorded.append(el('summary','Recorded effects'),fields({Status:effects.outcome,'Operation started':effects.effectCalled,Result:effects.resultRecorded ? effects.result : 'Not recorded','Added facts':effects.changes?.added ?? 'Unknown','Removed facts':effects.changes?.removed ?? 'Unknown'}));output.append(recorded);
    }
    output.append(translation);
  }catch(error) {if(current===callTicket) {$('#call-status').textContent='';output.replaceChildren(el('p',error.name==='TimeoutError' ? 'Analysis request timed out. Try again.' : error.message,'content'));}}
  finally {if(current===callTicket)$('#analyze-call').disabled=!callTemplate;}
}
function queryResult(result,title) {
    const columns=result.displayColumns || result.columns,indices=columns.map(name=>result.columns.indexOf(name));
    const results=el('section',undefined,'query-results');results.setAttribute('aria-label','Query result');
    const heading=el('div',undefined,'query-results-heading');heading.append(el('h3',title),el('span',result.rows.length+' '+(result.rows.length===1 ? 'row' : 'rows'),'subtle'));results.append(heading);
    const wrapper=el('div',undefined,'query-table'),table=el('table'),thead=el('thead'),head=el('tr'),tbody=el('tbody');
    for(const name of columns) {const cell=el('th',name);cell.scope='col';head.append(cell);}thead.append(head);table.append(thead);
    for(const values of result.rows) {const row=el('tr');for(const index of indices)row.append(el('td',values[index]));tbody.append(row);}
    table.append(tbody);wrapper.append(table);results.append(wrapper);
    if(!result.rows.length)results.append(el('p','No matching rows.','subtle'));
    return results;
}
$('#call-form').addEventListener('submit',(event)=>{event.preventDefault();analyzeCall();});
