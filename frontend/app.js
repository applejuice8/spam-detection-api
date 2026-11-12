// Demo client for the spam detection API.
// Flow: sign up / log in -> create an API key -> call /predict with that key.


// ---------- Helpers ----------

// Shortcut for document.getElementById
const $ = id => document.getElementById(id);

// Credentials kept in memory only, so a page refresh logs you out
const state = {
  accessToken: null,   // JWT from /auth/login, used for /auth/* routes
  apiKey: null,        // Raw key from /auth/api-keys, used for /predict
};

// API URL from the input box, without any trailing slash
const base = () => $('base').value.replace(/\/+$/, '');

// Show a message in one of the .msg elements. kind is '', 'ok' or 'error'.
function say(id, text, kind = '') {
  const el = $(id);
  el.textContent = text;
  el.className = 'msg ' + kind;
}

// Turn a FastAPI error body into readable text.
// Shapes: {detail: "text"} or {detail: [{msg, loc}, ...]} for validation errors.
function errorText(data, res) {
  if (!data || !data.detail) return `Request failed (${res.status})`;
  if (typeof data.detail === 'string') return data.detail;

  // loc looks like ['body', 'password']; drop 'body' and keep the field name
  return data.detail.map(d => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ');
}

// Call the API and return the parsed JSON (null for 204 responses).
// Throws an Error with a readable message on network or HTTP errors.
async function api(path, { method = 'GET', headers = {}, body } = {}) {
  let res;
  try {
    res = await fetch(base() + path, { method, headers, body });
  } catch {
    // fetch only rejects on network failures, including CORS blocks
    throw new Error('Cannot reach the API. Check the URL, that the server is running, and that CORS allows this page.');
  }

  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new Error(errorText(data, res));
  return data;
}

// Disable a button while its request runs, so it can't be double-clicked
async function withBusy(button, fn) {
  button.disabled = true;
  try {
    await fn();
  } finally {
    button.disabled = false;
  }
}


// ---------- API URL / health check ----------

// GET /health and show whether the API is reachable
async function checkHealth() {
  try {
    const data = await api('/health');
    say('health', `Connected (status: ${data.status})`, 'ok');
  } catch (e) {
    say('health', e.message, 'error');
  }
}

// Re-check whenever the URL is edited
$('base').addEventListener('change', checkHealth);


// ---------- Step 1: account ----------

// POST /auth/signup (JSON body)
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

// POST /auth/login, then GET /auth/me to confirm the token works
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

    // Unlock step 2
    $('keySec').classList.remove('locked');
  } catch (err) {
    say('authMsg', err.message, 'error');
  }
});


// ---------- Step 2: API key ----------

// POST /auth/api-keys (needs the login token)
$('createKey').onclick = e => withBusy(e.target, async () => {
  try {
    const created = await api('/auth/api-keys', {
      method: 'POST',
      headers: { Authorization: `Bearer ${state.accessToken}` },
    });

    // The raw key is only returned once, at creation
    state.apiKey = created.api_key || created.key;
    if (!state.apiKey) throw new Error('The response did not include an API key.');

    // Build the message with DOM nodes (not innerHTML) so the key is never parsed as HTML
    $('keyMsg').textContent = '';
    $('keyMsg').className = 'msg ok';
    $('keyMsg').append('Key created (shown once): ', Object.assign(document.createElement('code'), { textContent: state.apiKey }));

    // Unlock step 3
    $('predictSec').classList.remove('locked');
  } catch (err) {
    say('keyMsg', err.message, 'error');
  }
});


// ---------- Step 3: predict ----------

// POST /predict (authenticated with the X-API-Key header, not the login token)
$('predict').onclick = e => withBusy(e.target, async () => {
  // Hide the previous result while the new request runs
  $('result').style.display = 'none';

  try {
    const r = await api('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': state.apiKey },
      body: JSON.stringify({ text: $('text').value }),
    });

    const pct = (r.spam_probability * 100).toFixed(1);
    const isSpam = r.label.toLowerCase() === 'spam';

    // The class (spam or ham) sets the label color
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


// ---------- Start ----------

// Check the default API URL on page load
checkHealth();
