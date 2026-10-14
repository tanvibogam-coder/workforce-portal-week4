/* Shared UI: auth guard, sidebar shell, notification bell, tables, modal forms, toasts, charts. */
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (d) => (d ? String(d).replace('T', ' ').slice(0, 16) : '—');
const day = (d) => (d ? String(d).slice(0, 10) : '—');
const iso = (d = new Date()) => new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
const TONE = { good: ['Active', 'Approved', 'Completed', 'Present', 'Outstanding', 'Good', 'Yes', 'Done'], warn: ['Pending', 'Pending HR', 'Onboarding', 'In Progress', 'Under Review', 'Late', 'Medium', 'Half Day', 'Needs Improvement', 'Initiated', 'Planned'], bad: ['Rejected', 'Missing Checkout', 'At Risk', 'Exited', 'Inactive', 'High', 'Overdue'], mute: ['Not Started', 'On Hold', 'Low', 'No'] };
const badge = (t) => { const k = Object.keys(TONE).find((k) => TONE[k].includes(t)); return `<span class="badge${k ? ' b-' + k : ''}">${esc(t)}</span>`; };
const bar = (n) => `<div class="prog" title="${n}%"><i style="width:${Math.min(100, n || 0)}%"></i></div>`;
const HOME = { super_admin: 'hr-dashboard.html', hr_admin: 'hr-dashboard.html', manager: 'hr-dashboard.html', employee: 'employee-dashboard.html' };
const ALL = ['super_admin', 'hr_admin', 'manager', 'employee'], HRR = ['super_admin', 'hr_admin'], MGR = ['super_admin', 'hr_admin', 'manager'];
const NAV = [['hr-dashboard.html', 'Dashboard', MGR], ['employee-dashboard.html', 'My Dashboard', ALL], ['employees.html', 'Employee Directory', MGR], ['employee-profile.html', 'My Profile', ALL],
  ['attendance.html', 'Attendance', ALL], ['leave.html', 'Leave', ALL], ['performance.html', 'Performance', ALL], ['projects.html', 'Projects', ALL], ['tasks.html', 'Tasks', ALL],
  ['onboarding.html', 'Onboarding', HRR], ['offboarding.html', 'Offboarding', MGR], ['reports.html', 'Reports & Analytics', MGR], ['users.html', 'User & Role Management', ['super_admin']], ['settings.html', 'System Settings', HRR]];
const ROLE = { super_admin: 'Super Administrator', hr_admin: 'HR Administrator', manager: 'Department Manager', employee: 'Employee' };

function toast(msg, type = 'good') { const t = $('#toast'), d = document.createElement('div'); d.className = type; d.textContent = msg; t.append(d); setTimeout(() => d.remove(), 3500); }
async function logout() { try { await api('/auth/logout', { method: 'POST' }); } catch (e) {} Session.clear(); location.href = 'index.html'; }

/* Guard + layout. Returns the user, or null if the page must not render. */
function shell(title, roles) {
  const u = Session.user();
  if (!u || !Session.tok()) { location.href = 'index.html'; return null; }
  const page = location.pathname.split('/').pop() || 'index.html';
  const links = NAV.filter((n) => n[2].includes(u.role)).map((n) => `<a href="${n[0]}" class="${n[0] === page ? 'on' : ''}">${n[1]}</a>`).join('');
  $('#root').innerHTML = `<div class="app"><aside id="side"><div class="logo">Workforce Portal<small>Performance &amp; Operations</small></div>${links}</aside>
    <div class="main"><header><button id="menu" aria-label="Menu">☰</button><strong>${esc(title)}</strong><span class="sp"></span>
    <div class="bell"><button id="bell" aria-label="Notifications">🔔<span id="bellN">0</span></button><div id="notes"></div></div>
    <div class="who"><strong>${esc(u.name)}</strong><br><small>${ROLE[u.role]}</small></div><button id="out">Logout</button></header>
    <main id="view"></main></div></div><dialog id="dlg"></dialog><div id="toast"></div>`;
  $('#out').onclick = logout; $('#menu').onclick = () => $('#side').classList.toggle('open');
  $('#bell').onclick = () => $('#notes').classList.toggle('open');
  loadNotes();
  if (roles && !roles.includes(u.role)) { $('#view').innerHTML = '<div class="panel"><h2>Access denied</h2><p>Your role does not have permission to open this page.</p><a class="btn" href="' + HOME[u.role] + '">Go to my dashboard</a></div>'; return null; }
  return u;
}
async function loadNotes() {
  try {
    const r = await api('/notifications'); $('#bellN').textContent = r.unread;
    $('#notes').innerHTML = (r.items.length ? `<div><button class="sm" id="readAll">Mark all read</button></div>` : '') + (r.items.map((n) => `<div class="${n.is_read ? '' : 'un'}">${esc(n.message)}<small>${fmt(n.created_at)}</small></div>`).join('') || '<div>No notifications yet.</div>');
    const b = $('#readAll'); if (b) b.onclick = async () => { await api('/notifications/read-all', { method: 'POST' }); loadNotes(); };
  } catch (e) {}
}

/* table(cols, rows): cols = [{l:'Label', k:'key', f:(row)=>html}] */
function table(cols, rows, empty = 'No records found.') {
  if (!rows || !rows.length) return `<div class="empty">${empty}</div>`;
  return `<div class="tw"><table><thead><tr>${cols.map((c) => `<th>${c.l}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${cols.map((c) => `<td>${c.f ? c.f(r) : esc(r[c.k] ?? '—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

/* modal(title, fields, init, onSubmit): builds a validated form. field = {name,label,type,options:[[value,label]],required} */
function modal(title, fields, init, onSubmit, submitLabel = 'Save') {
  const d = $('#dlg');
  d.innerHTML = `<form class="f" novalidate><h2>${esc(title)}</h2>${fields.map((f) => {
    const v = init?.[f.name] ?? ''; const id = 'f_' + f.name;
    const input = f.type === 'select' ? `<select id="${id}" name="${f.name}"><option value="">Select…</option>${f.options.map(([val, lab]) => `<option value="${esc(val)}" ${String(v) === String(val) ? 'selected' : ''}>${esc(lab)}</option>`).join('')}</select>`
      : f.type === 'textarea' ? `<textarea id="${id}" name="${f.name}">${esc(v)}</textarea>` : `<input id="${id}" name="${f.name}" type="${f.type || 'text'}" value="${esc(v)}" ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''}>`;
    return `<label for="${id}">${f.label}${f.required ? ' *' : ''}</label>${input}<span class="err" data-for="${f.name}"></span>`;
  }).join('')}<span class="err" id="formErr"></span><div class="acts"><button type="button" id="cancel">Cancel</button><button class="pri">${submitLabel}</button></div></form>`;
  $('#cancel', d).onclick = () => d.close();
  $('form', d).onsubmit = async (e) => {
    e.preventDefault(); const vals = {}; let bad = false;
    d.querySelectorAll('.err').forEach((x) => (x.textContent = ''));
    fields.forEach((f) => {
      let v = $('[name=' + f.name + ']', d).value.trim(); vals[f.name] = v === '' ? null : v; const set = (m) => { $(`[data-for=${f.name}]`, d).textContent = m; bad = true; };
      if (f.required && !v) set(`${f.label} is required.`);
      else if (v && f.type === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) set('Enter a valid email address.');
      else if (v && f.type === 'number' && (isNaN(v) || (f.min != null && +v < f.min) || (f.max != null && +v > f.max))) set(`Enter a number${f.min != null ? ` between ${f.min} and ${f.max}` : ''}.`);
    });
    if (bad) return;
    try { await onSubmit(vals); d.close(); } catch (err) { $('#formErr', d).textContent = err.message; }
  };
  d.showModal();
}
function confirmBox(msg) {
  return new Promise((res) => { const d = $('#dlg'); d.innerHTML = `<h2>Please confirm</h2><p>${esc(msg)}</p><div class="acts"><button id="n">Cancel</button><button class="pri" id="y">Confirm</button></div>`;
    $('#n', d).onclick = () => { d.close(); res(false); }; $('#y', d).onclick = () => { d.close(); res(true); }; d.showModal(); });
}
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, 'bad'); } };

const _charts = {};
function chart(id, type, labels, data, label = '') {
  if (!window.Chart) return; if (_charts[id]) _charts[id].destroy();
  const pal = ['#2E4AE0', '#1D8A5D', '#D6923A', '#8A4FD1', '#C13B3B', '#3AA7C9', '#5B6472'];
  _charts[id] = new Chart($('#' + id), { type, data: { labels, datasets: [{ label, data, backgroundColor: type === 'line' ? '#2E4AE033' : pal, borderColor: '#2E4AE0', fill: type === 'line', tension: .3 }] }, options: { responsive: true, plugins: { legend: { display: type === 'doughnut' || type === 'pie' } }, scales: type === 'doughnut' ? {} : { y: { beginAtZero: true } } } });
}
const lookup = async () => (await api('/employees/lookup')).map((e) => [e.id, `${e.full_name} (${e.emp_code})`]);
const deptOpts = async () => (await api('/meta/departments')).map((d) => [d.id, d.name]);
