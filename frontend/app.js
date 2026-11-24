// Demo client for the spam detection API.
// Flow: log in to create or list API keys. Classifying only needs an API key, so it works without logging in.


// ---------- Helpers ----------

// Shortcut for document.getElementById
const $ = id => document.getElementById(id);

// Use the local API for local frontend servers and the deployed API on hosted pages.
if (!['localhost', '127.0.0.1'].includes(window.location.hostname)) {
  $('base').value = 'https://spam-detection-api-hpf8.onrender.com';
}

// Login token kept in memory only, so a page refresh logs you out
const state = {
  accessToken: null,   // JWT from /auth/login, used for /auth/* routes
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

// Short date for the key list
const fmtDate = s => new Date(s).toLocaleDateString();

// Status text for a key from GET /auth/api-keys
function keyStatus(k) {
  if (k.revoked) return 'revoked';
  return new Date(k.expires_at) > new Date() ? 'active' : 'expired';
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

// Creating and listing keys need a login. Step 3 does not.
function setLoggedIn(on) {
  $('createKey').disabled = !on;
  $('keyExpiry').disabled = !on;
  $('listKeys').disabled = !on;
}

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

    // Enable key creation and the key list, then load the list
    setLoggedIn(true);
    await loadKeys();
  } catch (err) {
    say('authMsg', err.message, 'error');
  }
});


// ---------- Step 2: API keys ----------

// POST /auth/api-keys (needs the login token). The expiry comes from the fixed options in the select.
$('createKey').onclick = e => withBusy(e.target, async () => {
  try {
    const created = await api('/auth/api-keys', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${state.accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ expires_in_days: Number($('keyExpiry').value) }),
    });

    // The raw key is only returned once, at creation. Show it in its own box for copying. It is not stored.
    const rawKey = created.api_key || created.key;
    if (!rawKey) throw new Error('The response did not include an API key.');

    // textContent (not innerHTML) so the key is never parsed as HTML
    $('newKeyValue').textContent = rawKey;
    $('newKey').hidden = false;
    resetCopyButton();
    say('keyMsg', 'API key created.', 'ok');

    await loadKeys();
  } catch (err) {
    say('keyMsg', err.message, 'error');
  }
});

// Select the whole key text, so it can be copied by hand if the clipboard API is blocked
function selectNewKey() {
  const range = document.createRange();
  range.selectNodeContents($('newKeyValue'));
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
}

// Put the copy button back to its normal state
let copyTimer;
function resetCopyButton() {
  clearTimeout(copyTimer);
  $('copyKey').classList.remove('copied');
  $('copyLabel').textContent = 'Copy';
  $('copyStatus').textContent = '';
}

// Copy the new key to the clipboard. Browsers can block this, so select the key and show a message if it fails.
$('copyKey').onclick = async () => {
  try {
    await navigator.clipboard.writeText($('newKeyValue').textContent);
    resetCopyButton();
    $('copyKey').classList.add('copied');
    $('copyLabel').textContent = 'Copied';
    $('copyStatus').textContent = 'API key copied to clipboard.';
    copyTimer = setTimeout(resetCopyButton, 2000);
  } catch {
    selectNewKey();
    say('keyMsg', 'Could not copy automatically. The key is selected, so press Ctrl+C (Cmd+C on Mac).', 'error');
  }
};

// Hide the key panel and clear the key from the page
$('dismissKey').onclick = () => {
  $('newKeyValue').textContent = '';
  $('newKey').hidden = true;
  resetCopyButton();
};

// GET /auth/api-keys (needs the login token). Shows only the prefix, since raw keys are never returned again.
async function loadKeys() {
  const list = $('keyList');
  list.replaceChildren();

  try {
    const keys = await api('/auth/api-keys', { headers: { Authorization: `Bearer ${state.accessToken}` } });
    if (keys.length === 0) {
      say('listMsg', 'No API keys yet.');
      return;
    }

    for (const k of keys) {
      const li = document.createElement('li');
      const status = keyStatus(k);
      li.append(
        Object.assign(document.createElement('code'), { textContent: `${k.prefix}...` }),
        Object.assign(document.createElement('span'), { className: `pill ${status}`, textContent: status }),
        Object.assign(document.createElement('span'), {
          className: 'key-dates',
          textContent: `Created ${fmtDate(k.created_at)}, expires ${fmtDate(k.expires_at)}`,
        }),
      );

      // Revoked keys stay in the list but can't be revoked again
      if (!k.revoked) {
        const btn = document.createElement('button');
        btn.className = 'danger small';
        btn.textContent = 'Revoke';
        btn.onclick = ev => withBusy(ev.target, () => revokeKey(k.id, k.prefix));
        li.append(btn);
      }
      list.append(li);
    }
    say('listMsg', '');
  } catch (err) {
    say('listMsg', err.message, 'error');
  }
}

// DELETE /auth/api-keys/{id} (needs the login token). Revoking cannot be undone, so ask first.
async function revokeKey(id, prefix) {
  if (!confirm(`Revoke key ${prefix}...? Anything using it will stop working.`)) return;

  try {
    await api(`/auth/api-keys/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${state.accessToken}` },
    });
    await loadKeys();
  } catch (err) {
    say('listMsg', err.message, 'error');
  }
}

$('listKeys').onclick = e => withBusy(e.target, loadKeys);


// ---------- Step 3: predict ----------

// POST /predict (authenticated with the X-API-Key header, not the login token).
// The key comes from the field, and the server checks it.
$('predict').onclick = e => withBusy(e.target, async () => {
  // Hide the previous result while the new request runs
  $('result').style.display = 'none';

  const apiKey = $('apiKey').value.trim();
  if (!apiKey) {
    say('predictMsg', 'Enter an API key first.', 'error');
    return;
  }

  try {
    const r = await api('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
      body: JSON.stringify({ text: $('text').value }),
    });

    const pct = (r.spam_probability * 100).toFixed(1);
    const isSpam = r.label.toLowerCase() === 'spam';

    // The class (spam or ham) sets the label color
    $('result').className = 'result ' + (isSpam ? 'spam' : 'ham');
    $('resLabel').textContent = r.label;
    $('resCache').hidden = !r.from_cache;
    $('resBar').style.width = pct + '%';
    $('resDetail').textContent = `Spam probability: ${pct}%`;
    $('result').style.display = 'block';
    say('predictMsg', '');
  } catch (err) {
    say('predictMsg', err.message, 'error');
  }
});


// ---------- Start ----------

// Key creation and the key list stay off until login
setLoggedIn(false);

// Check the default API URL on page load
checkHealth();
