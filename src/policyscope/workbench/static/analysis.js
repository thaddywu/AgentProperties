const $ = (selector) => document.querySelector(selector);
const names = {message: 'Message', tool_call: 'Tool call', tool_result: 'Tool result', state: 'State', decision: 'Decision'};
let log = null, token = '', activeRole = '', selected = '', ticket = 0;

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (cls) node.className = cls;
  return node;
}
function name(id) { return log.roles.find((r) => r.id === id)?.name ?? id; }
function stamp(value) { return new Date(value).toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC'); }
function route(event) {
  if (event.kind === 'message') return event.recipients.length ? event.recipients.map(name).join(', ') : 'Recipient not recorded';
  if (event.kind === 'tool_call') return event.tool;
  if (event.kind === 'tool_result') return event.recipients?.length ? event.recipients.map(name).join(', ') : 'Tool result';
  return '';
}
async function post(operation, value) {
  const response = await fetch('/api/analysis/' + operation, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Study-Token': token}, body: JSON.stringify(value)});
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Could not read this trajectory.');
  return data;
}
function fail(error) { $('#status').textContent = error.message || 'Could not read this trajectory.'; }
function clearTime() { $('#from').value = ''; $('#until').value = ''; }
function visible() {
  const kind = $('#kind').value;
  const start = $('#from').value ? Date.parse($('#from').value + 'Z') : null;
  const end = $('#until').value ? Date.parse($('#until').value + 'Z') : null;
  return log.events.filter((e) => (!activeRole || e.actor === activeRole || (e.recipients || []).includes(activeRole)) && (!kind || e.kind === kind) && (start === null || (e.timestamp && Date.parse(e.timestamp) >= start)) && (end === null || (e.timestamp && Date.parse(e.timestamp) <= end)));
}
function badge(value) {
  const allowed = ['applied', 'blocked', 'unknown', 'not_applied', 'failed'];
  return el('span', value, 'badge' + (allowed.includes(value) ? ' ' + value : ''));
}
function renderRoles() {
  const roles = $('#roles'); roles.replaceChildren();
  for (const role of [{id: '', name: 'All participants'}, ...log.roles]) {
    const button = el('button', undefined, 'role');
    button.type = 'button'; button.setAttribute('aria-pressed', String(role.id === activeRole));
    button.setAttribute('aria-label', 'Filter participant ' + role.name);
    button.append(el('span', role.id ? role.name.slice(0, 2).toUpperCase() : '∗', 'avatar'));
    const label = el('span', role.name);
    if (role.role) label.append(el('small', role.role));
    button.append(label);
    button.addEventListener('click', () => {activeRole = role.id; renderRoles(); renderEvents();});
    roles.append(button);
  }
}
function renderEvents(preferred) {
  if (!log) return;
  const events = visible(), container = $('#events'); container.replaceChildren();
  $('#count').textContent = events.length + ' / ' + log.events.length;
  $('#no-events').hidden = events.length > 0;
  $('#position').max = String(Math.max(0, events.length - 1));
  $('#position').disabled = events.length === 0;
  for (const event of events) {
    const button = el('button', undefined, 'event');
    button.type = 'button'; button.dataset.eventId = event.id;
    button.setAttribute('aria-label', 'Event ' + event.sequence + ' ' + name(event.actor) + ' ' + names[event.kind]);
    const meta = el('div', undefined, 'event-meta');
    meta.append(el('span', '#' + event.sequence), el('span', names[event.kind]));
    if (event.outcome) meta.append(badge(event.outcome));
    if (event.timestamp) {const time = el('time', stamp(event.timestamp)); time.dateTime = event.timestamp; meta.append(time);}
    const path = el('div', undefined, 'event-path'); path.append(el('span', name(event.actor)));
    const target = route(event);
    if (target) path.append(el('span', '→', 'arrow'), el('span', target));
    button.append(meta, path);
    if (event.preview) button.append(el('p', event.preview, 'preview'));
    button.addEventListener('click', () => select(event.id)); container.append(button);
  }
  const id = events.find((e) => e.id === preferred)?.id || events.find((e) => e.id === selected)?.id || events[0]?.id;
  if (id) select(id);
  else {selected = ''; ticket++; $('#position-value').textContent = '—'; $('#detail').replaceChildren(el('p', 'No event selected.', 'subtle'));}
}
async function select(id) {
  selected = id; const current = ++ticket, identity = log.id;
  for (const button of $('#events').children) button.setAttribute('aria-current', String(button.dataset.eventId === id));
  const events = visible(), event = events.find((e) => e.id === id);
  $('#position').value = String(Math.max(0, events.findIndex((e) => e.id === id)));
  $('#position-value').textContent = event ? '#' + event.sequence : '—';
  $('#detail').setAttribute('aria-busy', 'true');
  try {
    const result = await post('event', {trajectoryId: identity, eventId: id});
    if (current !== ticket || log.id !== result.trajectoryId) return;
    renderDetail(result.result); $('#status').textContent = '';
  } catch (error) { if (current === ticket) fail(error); }
  finally {if (current === ticket) $('#detail').setAttribute('aria-busy', 'false');}
}
function section(title, value, open = false) {
  const details = el('details', undefined, 'detail-section'); details.open = open;
  details.append(el('summary', title), el('pre', JSON.stringify(value, null, 2))); return details;
}
function jump(id) {
  activeRole = ''; $('#kind').value = ''; clearTime(); renderRoles(); renderEvents(id);
  for (const button of $('#events').children) if (button.dataset.eventId === id) button.scrollIntoView({block: 'nearest'});
}
function renderDetail(event) {
  const detail = $('#detail'); detail.replaceChildren();
  const head = el('div', undefined, 'detail-head'); head.append(badge(names[event.kind]), el('span', '#' + event.sequence, 'subtle'));
  detail.append(head, el('div', name(event.actor) + (route(event) ? ' → ' + route(event) : ''), 'detail-title'));
  if (event.timestamp) detail.append(el('p', stamp(event.timestamp), 'subtle'));
  if (event.content) detail.append(el('div', event.content, 'content'));
  if (event.kind === 'tool_call' || event.kind === 'tool_result') {
    const related = log.events.find((e) => e.callId === event.callId && e.kind === (event.kind === 'tool_call' ? 'tool_result' : 'tool_call'));
    if (related) {const button = el('button', event.kind === 'tool_call' ? 'Jump to result' : 'Jump to call', 'link'); button.addEventListener('click', () => jump(related.id)); detail.append(button);}
    else detail.append(el('p', 'Result not recorded.', 'subtle'));
  }
  if ('arguments' in event) detail.append(section('Arguments', event.arguments, true));
  if ('result' in event) detail.append(section('Result', event.result, true));
  if ('data' in event) {
    const data = event.data;
    if (log.format === 'policyscope-trajectory') {
      const grid = el('div', undefined, 'outcome');
      const values = [['Gate', data.decision ? (data.decision.allowed ? 'Allowed' : 'Blocked') : 'Not recorded'], ['Callback', data.effectCalled === true ? 'Invoked' : data.effectCalled === false ? 'Not invoked' : 'Not recorded'], ['Outcome', data.outcome]];
      for (const [label, value] of values) {const cell = el('div'); cell.append(el('small', label), el('span', value)); grid.append(cell);}
      detail.append(grid);
      if (data.decision?.reasons?.length) detail.append(el('p', data.decision.reasons.join(', '), 'content'));
      if (data.request) detail.append(section('Request', data.request, true));
      if ('result' in data) detail.append(section('Recorded result', data.result));
      for (const [label, field] of [['Inputs', 'inputs'], ['Committed inputs', 'committedInputs']]) {
        if (data[field] === null) detail.append(el('p', label + ': not confirmed.', 'subtle'));
        else if (data[field]) detail.append(section(label + ' · ' + data[field].length, data[field]));
      }
    } else detail.append(section('Recorded data', data, true));
  }
  detail.append(section('Raw event', event));
}
function setLog(value) {
  log = value; activeRole = ''; selected = ''; ticket++; clearTime();
  $('#empty').hidden = Boolean(log); $('#workspace').hidden = !log; $('#export').hidden = !log;
  $('#title').textContent = log?.title || 'Trajectory';
  if (!log) return;
  $('#scope').textContent = log.scope; $('#format').textContent = log.format;
  $('#kind').replaceChildren(new Option('All events', ''));
  for (const kind of [...new Set(log.events.map((e) => e.kind))]) $('#kind').append(new Option(names[kind], kind));
  $('#time-filter').hidden = !log.events.some((e) => e.timestamp);
  renderRoles(); renderEvents();
}
$('#file').addEventListener('change', async () => {
  const file = $('#file').files[0]; if (!file) return;
  try {
    if (file.size > 64 * 1024 * 1024) throw Error('Trajectory exceeds 64 MiB.');
    const value = JSON.parse(await file.text());
    const response = await post('import', {trajectory: value});
    $('#status').textContent = ''; setLog(response.result);
  } catch (error) {fail(error);}
  finally {$('#file').value = '';}
});
for (const id of ['kind', 'from', 'until']) $('#' + id).addEventListener('change', () => renderEvents());
for (const id of ['from', 'until']) $('#' + id).addEventListener('input', () => renderEvents());
$('#position').addEventListener('input', () => {const event = visible()[Number($('#position').value)]; if (event) {select(event.id); for (const button of $('#events').children) if (button.dataset.eventId === event.id) button.scrollIntoView({block: 'nearest'});}});
try {
  const response = await fetch('/api/analysis'); if (!response.ok) throw Error('Could not open the viewer.');
  const value = await response.json(); token = value.token; setLog(value.trajectory);
} catch (error) {fail(error);}
