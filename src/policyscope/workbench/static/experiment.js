const $ = (s) => document.querySelector(s);
let state, selected = '', timer;
function el(tag, text) {const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n;}
async function post(path, value) {const r = await fetch('/api/experiment/' + path, {method:'POST',headers:{'Content-Type':'application/json','X-Study-Token':state.token},body:JSON.stringify(value)}); const v = await r.json(); if (!r.ok) throw Error(v.error); return v;}
async function load() {const r = await fetch('/api/experiment'); if (!r.ok) throw Error('Could not load study.'); state = await r.json(); if (!selected) selected = state.cases[0]?.id; render(); clearTimeout(timer); if (state.job?.status === 'running') timer = setTimeout(() => load().catch(fail), 800);}
function fail(error) {$('#error').textContent = error.message || 'Study operation failed.';}
function render() {
  const nav = $('#cases'); nav.replaceChildren();
  for (const item of state.cases) {const b = el('button', item.id.replaceAll('-', ' ')); b.setAttribute('aria-pressed', String(selected === item.id)); b.addEventListener('click', () => {selected = item.id; render();}); nav.append(b);}
  const current = state.cases.find((x) => x.id === selected); if (!current) return;
  $('#case-title').textContent = current.id.replaceAll('-', ' '); $('#task').textContent = current.task; $('#expected').textContent = current.expected;
  $('#run').disabled = state.job?.status === 'running';
  $('#job-status').textContent = state.job ? state.job.caseId + ' · ' + state.job.status : '';
  const output = $('#results'); output.replaceChildren();
  const records = state.records.filter((r) => r.caseId === selected);
  if (!records.length) {output.append(el('p', 'Run this case to collect paired evidence.')); return;}
  const table = el('table'), header = el('tr'); for (const title of ['App','Completed','Runs with findings','Policies','Trajectory']) header.append(el('th', title)); table.append(header);
  for (const [mode, name] of [['baseline','Original'],['protected','Translated']]) {
    const runs = records.filter((r) => r.mode === mode).sort((a,b) => a.repetition-b.repetition); if (!runs.length) continue;
    const row = el('tr'); row.append(el('td',name),el('td',runs.filter((r) => r.taskCompleted).length+'/'+runs.length),el('td',runs.filter((r) => r.violations.length).length+'/'+runs.length));
    const policies = [...new Set(runs.flatMap((r) => r.violations.map((v) => v[1])))].sort(); const cell = el('td',policies.join(', ') || '—'); cell.className = policies.length ? 'findings' : 'good'; row.append(cell);
    const actions = el('td'), wrap = el('div'); wrap.className = 'run-choice';
    const choice = el('select'); choice.setAttribute('aria-label', name + ' repetition'); for (const r of runs) choice.append(new Option(String(r.repetition),r.id));
    const open = el('button','Inspect '+name.toLowerCase()); open.addEventListener('click', async () => {
      const windowRef = window.open('about:blank','_blank'); if (windowRef) windowRef.opener = null;
      try {const result = await post('inspect',{id:choice.value}); if (windowRef) windowRef.location.href = result.url; else location.href = result.url;} catch (error) {windowRef?.close(); fail(error);}
    }); wrap.append(choice,open); actions.append(wrap); row.append(actions); table.append(row);
  }
  output.append(table);
}
$('#run').addEventListener('click', async () => {$('#error').textContent = ''; $('#run').disabled = true; try {await post('run',{caseId:selected,repetitions:Number($('#repetitions').value)}); await load();} catch(error) {fail(error); $('#run').disabled = false;}});
load().catch(fail);
