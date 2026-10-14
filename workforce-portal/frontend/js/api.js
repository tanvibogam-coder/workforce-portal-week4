/* Single place that talks to the Flask REST API (same origin, so no CORS or hard-coded host). */
const API = '/api';
const Session = {
  tok: () => localStorage.getItem('wp_token'),
  user: () => JSON.parse(localStorage.getItem('wp_user') || 'null'),
  set: (t, u) => { localStorage.setItem('wp_token', t); localStorage.setItem('wp_user', JSON.stringify(u)); },
  clear: () => { localStorage.removeItem('wp_token'); localStorage.removeItem('wp_user'); },
};
async function api(path, { method = 'GET', body, form } = {}) {
  const headers = {}; if (Session.tok()) headers.Authorization = 'Bearer ' + Session.tok();
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try { res = await fetch(API + path, { method, headers, body: form || (body !== undefined ? JSON.stringify(body) : undefined) }); }
  catch (e) { throw new Error('Cannot reach the server. Is the Flask backend running?'); }
  const data = (res.headers.get('content-type') || '').includes('json') ? await res.json() : null;
  if (res.status === 401 && !location.pathname.endsWith('index.html') && location.pathname !== '/') { Session.clear(); location.href = 'index.html?expired=1'; }
  if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
  return data;
}
async function download(path, name) {
  const res = await fetch(API + path, { headers: { Authorization: 'Bearer ' + Session.tok() } });
  if (!res.ok) throw new Error('Download failed.');
  const a = document.createElement('a'); a.href = URL.createObjectURL(await res.blob()); a.download = name; a.click(); URL.revokeObjectURL(a.href);
}
const qs = (o) => '?' + Object.entries(o).filter(([, v]) => v !== '' && v != null).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
