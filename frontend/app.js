const $ = id => document.getElementById(id);
const state = { accessToken: null, apiKey: null };

const base = () => $('base').value.replace(/\/+$/, '');

function say(id, text, kind = '') {
  const el = $(id);
  el.textContent = text;
  el.className = 'msg ' + kind;
}

// FastAPI errors: {detail: "text"} or {detail: [{msg, loc}, ...]}
function errorText(data, res) {
  if (!data || !data.detail) return `Request failed (${res.status})`;
  if (typeof data.detail === 'string') return data.detail;
  return data.detail.map(d => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ');
}

async function api(path, { method = 'GET', headers = {}, body } = {}) {
  let res;
  try {
    res = await fetch(base() + path, { method, headers, body });
  } catch {
    throw new Error('Cannot reach the API. Check the URL, that the server is running, and that CORS allows this page.');
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new Error(errorText(data, res));
  return data;
}

async function withBusy(button, fn) {
  button.disabled = true;
  try { await fn(); } finally { button.disabled = false; }
}

async function checkHealth() {
  try {
    const data = await api('/health');
    say('health', `Connected (status: ${data.status})`, 'ok');
  } catch (e) {
    say('health', e.message, 'error');
  }
}

$('base').addEventListener('change', checkHealth);

$('signup').onclick = e => withBusy(e.target, async () => {
  try {
    const user = await api('/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: $('username').value,
        password: $('password').value,
        confirm_password: $('confirm').value,
      }),
    });
    say('authMsg', `Account "${user.username}" created. You can log in now.`, 'ok');
  } catch (err) {
    say('authMsg', err.message, 'error');
  }
});

$('login').onclick = e => withBusy(e.target, async () => {
  try {
    // /auth/login expects OAuth2 form data, not JSON
    const tokens = await api('/auth/login', {
      method: 'POST',
      body: new URLSearchParams({ username: $('username').value, password: $('password').value }),
    });
    state.accessToken = tokens.access_token;
    const me = await api('/auth/me', { headers: { Authorization: `Bearer ${state.accessToken}` } });
    say('authMsg', `Logged in as ${me.username}.`, 'ok');
    $('keySec').classList.remove('locked');
  } catch (err) {
    say('authMsg', err.message, 'error');
  }
});

$('createKey').onclick = e => withBusy(e.target, async () => {
  try {
    const created = await api('/auth/api-keys', {
      method: 'POST',
      headers: { Authorization: `Bearer ${state.accessToken}` },
    });
    state.apiKey = created.api_key || created.key;
    if (!state.apiKey) throw new Error('The response did not include an API key.');
    $('keyMsg').textContent = '';
    $('keyMsg').className = 'msg ok';
    $('keyMsg').append('Key created (shown once): ', Object.assign(document.createElement('code'), { textContent: state.apiKey }));
    $('predictSec').classList.remove('locked');
  } catch (err) {
    say('keyMsg', err.message, 'error');
  }
});

$('predict').onclick = e => withBusy(e.target, async () => {
  $('result').style.display = 'none';
  try {
    const r = await api('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': state.apiKey },
      body: JSON.stringify({ text: $('text').value }),
    });
    const pct = (r.spam_probability * 100).toFixed(1);
    const isSpam = r.label.toLowerCase() === 'spam';
    $('result').className = 'result ' + (isSpam ? 'spam' : 'ham');
    $('resLabel').textContent = r.label;
    $('resBar').style.width = pct + '%';
    $('resDetail').textContent = `Spam probability: ${pct}%  |  Model F1: ${r.model_f1.toFixed(3)}`;
    $('result').style.display = 'block';
    say('predictMsg', '');
  } catch (err) {
    say('predictMsg', err.message, 'error');
  }
});

checkHealth();
