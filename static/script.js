// ══════════════════════════════════════════════════════════════════════════════
// NEMOTRON v3 - script.js
// ENTER = nouvelle ligne, Shift+Enter = envoyer
// NEW : /api/stop (bouton Stop côté serveur)
// NEW : token budget live dans la sidebar
// NEW : config agent modal (max_steps, timeout...)
// NEW : export JSON + import JSON conversations
// NEW : auto-nommage après 1er échange
// NEW : raccourcis clavier étendus
// ══════════════════════════════════════════════════════════════════════════════

let streaming     = false;
let abortCtrl     = null;
let reasoningOn   = false;
let activeConvId  = null;
let conversations = [];
let currentModel  = '';
let toolContainer = null;
let agentBodyEl   = null;
let streamBuf     = '';
let totalCost     = 0;
let uploadedFile  = null;
let workspaces    = [];
let tokenBudget      = {used: 0, max: 8000};
let reasoningBuf     = '';   // tokens de réflexion accumulés
let reasoningEl      = null; // élément DOM du bloc reasoning

// ══════════════════════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════════════════════
async function init() {
  try {
    const [sR, cR] = await Promise.all([fetch('/api/status'), fetch('/api/conversations')]);
    const st = await sR.json();
    const cd = await cR.json();

    if (st.models) buildModelSelect(st.models, st.model);
    currentModel  = st.model || '';
    reasoningOn   = st.reasoning_enabled || false;
    activeConvId  = st.active_conv || cd.active;
    totalCost     = st.metrics?.cost_usd || 0;
    tokenBudget   = st.token_budget || {used: 0, max: 8000};

    setReasoningUI(reasoningOn);
    showKeySection(!st.api_key_set);
    setStatus(st.api_key_set ? 'Connecté' : 'Clé manquante', st.api_key_set ? 'ok' : 'off');
    if (st.metrics) updateStats(st.metrics);
    updateTokenBudget(tokenBudget);
    document.getElementById('mem-count').textContent = st.memory_count || 0;
    if (st.timeout) document.getElementById('timeout-badge').textContent = `⏱ ${st.timeout}s`;

    workspaces = st.workspaces || [];
    renderWorkspaceSelect(workspaces, st.workspace || 'default');

    conversations = cd.conversations || [];
    renderConvList();
    if (activeConvId) await loadConvHistory(activeConvId);
  } catch(e) {
    setStatus('Hors ligne', 'off');
    console.error('Init:', e);
  }
  // Appliquer les preferences stockees (theme, compact, etc.)
  applyStoredPrefs();
}

function buildModelSelect(modelsDict, currentId) {
  const sel = document.getElementById('model-select');
  sel.innerHTML = Object.entries(modelsDict).map(([id, label]) =>
    `<option value="${escH(id)}" ${id===currentId?'selected':''}>${escH(label)}</option>`
  ).join('');
}

// ══════════════════════════════════════════════════════════════════════════════
// TOKEN BUDGET
// ══════════════════════════════════════════════════════════════════════════════
function updateTokenBudget(budget) {
  tokenBudget = budget || tokenBudget;
  const {used, max} = tokenBudget;
  const pct   = Math.min(100, Math.round((used / max) * 100));
  const bar   = document.getElementById('token-bar');
  const lbl   = document.getElementById('token-lbl');
  if (!bar || !lbl) return;
  bar.style.width = pct + '%';
  bar.className   = 'token-bar' + (pct > 80 ? ' warn' : pct > 95 ? ' crit' : '');
  lbl.textContent = `${fmt(used)} / ${fmt(max)} tokens`;
}

// ══════════════════════════════════════════════════════════════════════════════
// STATUS / STATS
// ══════════════════════════════════════════════════════════════════════════════
function setStatus(text, state) {
  document.getElementById('status-txt').textContent = text;
  document.getElementById('dot').className = 'dot' + (state==='ok' ? '' : state==='off' ? ' off' : ' busy');
}

function updateStats(m) {
  if (!m) return;
  document.getElementById('s-tin').textContent   = fmt(m.tokens_in);
  document.getElementById('s-tout').textContent  = fmt(m.tokens_out);
  document.getElementById('s-tools').textContent = m.tools || 0;
  if (m.cost_usd !== undefined) updateCost(m.cost_usd);
}

function updateCost(usd) {
  totalCost = usd || 0;
  const str = totalCost===0 ? '$0.00' : '$'+totalCost.toFixed(8);
  const sh  = totalCost===0 ? '$0.00' : totalCost<0.001 ? '$'+totalCost.toFixed(6) : '$'+totalCost.toFixed(4);
  document.getElementById('s-cost').textContent     = str;
  document.getElementById('s-cost').className       = 'cost-val' + (totalCost>0?' nonzero':'');
  document.getElementById('cost-badge').textContent = sh;
  document.getElementById('cost-badge').className   = 'cost-badge' + (totalCost>0?' nonzero':'');
}

function fmt(n) { return !n ? '0' : n>=1000 ? (n/1000).toFixed(1)+'k' : String(n); }

// ══════════════════════════════════════════════════════════════════════════════
// REASONING
// ══════════════════════════════════════════════════════════════════════════════
async function toggleReasoning() {
  try {
    const r = await fetch('/api/reasoning', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({enabled: !reasoningOn})
    });
    const d = await r.json();
    if (d.reasoning_enabled !== undefined) { reasoningOn = d.reasoning_enabled; setReasoningUI(reasoningOn); }
  } catch(e) { console.error(e); }
}
function setReasoningUI(on) {
  document.getElementById('reasoning-toggle').classList.toggle('active', on);
  document.getElementById('reasoning-chip').style.display = on ? 'flex' : 'none';
}

// ══════════════════════════════════════════════════════════════════════════════
// MODEL
// ══════════════════════════════════════════════════════════════════════════════
async function changeModel(model) {
  if (!model) return;
  try {
    const r = await fetch('/api/model', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({model})});
    const d = await r.json();
    if (d.error) { showToast(d.error, 'error'); document.getElementById('model-select').value = currentModel; return; }
    currentModel = d.model || model;
    if (d.timeout) document.getElementById('timeout-badge').textContent = `⏱ ${d.timeout}s`;
    document.getElementById('model-select').value = currentModel;
    showToast(`Modèle: ${currentModel}`, 'ok');
  } catch(e) { console.error(e); }
}

// ══════════════════════════════════════════════════════════════════════════════
// API KEY
// ══════════════════════════════════════════════════════════════════════════════
function showKeySection(show) { document.getElementById('key-section').style.display = show?'block':'none'; }
async function saveKey() {
  const inp = document.getElementById('key-input');
  const key = inp.value.trim(); if (!key) return;
  const d = await fetch('/api/setkey', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key})}).then(r=>r.json());
  if (d.ok) {
    inp.value = '';
    const st = document.getElementById('key-status');
    st.textContent = '✓ Clé enregistrée'; st.style.color = 'var(--green)';
    setStatus('Connecté', 'ok');
    setTimeout(() => { showKeySection(false); st.textContent = ''; }, 2000);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// CONFIG AGENT MODAL
// ══════════════════════════════════════════════════════════════════════════════
async function openConfig() {
  document.getElementById('config-modal').classList.add('open');
  // Reset au tab agent
  document.querySelectorAll('.cfg-tab').forEach((b,i) => b.classList.toggle('active', i===0));
  document.querySelectorAll('.cfg-panel').forEach((p,i) => p.style.display = i===0?'flex':'none');
  prefillCfgApi();
  const d = await fetch('/api/config').then(r=>r.json());
  document.getElementById('cfg-max-steps').value   = d.max_steps          || 15;
  document.getElementById('cfg-timeout').value      = d.tool_timeout       || 30;
  document.getElementById('cfg-max-tools').value    = d.max_tools_per_step || 4;
  document.getElementById('cfg-max-htoks').value    = d.max_history_tokens || 8000;
  if (d.bounds) {
    const b = d.bounds;
    if (b.max_steps)          { document.getElementById('cfg-max-steps').min  = b.max_steps[0];          document.getElementById('cfg-max-steps').max  = b.max_steps[1]; }
    if (b.tool_timeout)       { document.getElementById('cfg-timeout').min    = b.tool_timeout[0];       document.getElementById('cfg-timeout').max    = b.tool_timeout[1]; }
    if (b.max_tools_per_step) { document.getElementById('cfg-max-tools').min  = b.max_tools_per_step[0]; document.getElementById('cfg-max-tools').max  = b.max_tools_per_step[1]; }
    if (b.max_history_tokens) { document.getElementById('cfg-max-htoks').min  = b.max_history_tokens[0]; document.getElementById('cfg-max-htoks').max  = b.max_history_tokens[1]; }
  }
}
function closeConfig() { document.getElementById('config-modal').classList.remove('open'); }

async function saveConfig() {
  const payload = {
    max_steps         : parseInt(document.getElementById('cfg-max-steps').value),
    tool_timeout      : parseInt(document.getElementById('cfg-timeout').value),
    max_tools_per_step: parseInt(document.getElementById('cfg-max-tools').value),
    max_history_tokens: parseInt(document.getElementById('cfg-max-htoks').value),
  };
  const d = await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}).then(r=>r.json());
  if (d.ok) { showToast('Config sauvegardée', 'ok'); closeConfig(); }
  else        showToast(d.error || 'Erreur', 'error');
}

// ====================================================================
// CONFIG TABS
// ====================================================================
function switchCfgTab(tab, btn) {
  document.querySelectorAll('.cfg-tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.cfg-panel').forEach(p => p.style.display = 'none');
  btn.classList.add('active');
  document.getElementById('cfg-panel-' + tab).style.display = 'flex';
}

// ====================================================================
// API KEY dans config
// ====================================================================
function toggleApiKeyVisibility() {
  const inp  = document.getElementById('cfg-api-key');
  const icon = document.getElementById('eye-icon');
  if (inp.type === 'password') {
    inp.type = 'text';
    icon.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>';
  } else {
    inp.type = 'password';
    icon.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
  }
}

async function saveCfgApiKey() {
  const keyEl   = document.getElementById('cfg-api-key');
  const braveEl = document.getElementById('cfg-brave-key');
  const status  = document.getElementById('cfg-api-status');
  const key     = keyEl.value.trim();
  const brave   = braveEl ? braveEl.value.trim() : '';

  if (!key && !brave) { status.textContent = 'Saisit au moins une clé.'; status.style.color = 'var(--red)'; return; }

  try {
    if (key) {
      const r = await fetch('/api/setkey', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({key})
      });
      const d = await r.json();
      if (d.ok) {
        keyEl.value = '';
        status.innerHTML = '<span style="color:var(--green)">✓ Clé OpenRouter enregistrée</span>';
        setStatus('Connecte', 'ok');
        showKeySection(false);
      } else {
        status.innerHTML = `<span style="color:var(--red)">✗ ${d.error}</span>`;
        return;
      }
    }
    if (brave) {
      await fetch('/api/setbrave', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({key: brave})
      });
      braveEl.value = '';
      status.innerHTML += ' <span style="color:var(--green)">✓ Brave enregistré</span>';
    }
    setTimeout(() => { status.textContent = ''; }, 3000);
  } catch(e) {
    status.innerHTML = `<span style="color:var(--red)">Erreur réseau: ${e.message}</span>`;
  }
}

// Précharger la clé actuelle (masquée) dans le champ
async function prefillCfgApi() {
  const r = await fetch('/api/status').then(r => r.json());
  const status = document.getElementById('cfg-api-status');
  if (r.api_key_set) {
    const inp = document.getElementById('cfg-api-key');
    inp.placeholder = '••••••••••••••• (clé active)';
    if (status) status.innerHTML = '<span style="color:var(--green)">✓ Clé active</span>';
    setTimeout(() => { if(status) status.textContent=''; }, 2500);
  }
}

// ====================================================================
// THEMES
// ====================================================================
let currentTheme = localStorage.getItem('nemo_theme') || 'dark';
let currentFontSize = parseInt(localStorage.getItem('nemo_fontsize') || '13');
let isCompact  = localStorage.getItem('nemo_compact') === 'true';
let isMonoFont = localStorage.getItem('nemo_mono')    === 'true';

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  currentTheme = theme;
  localStorage.setItem('nemo_theme', theme);
  // Mettre a jour l'icone du header
  const icon = document.getElementById('theme-icon');
  if (icon) {
    if (theme === 'light') {
      icon.innerHTML = '<circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>';
    } else {
      icon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
    }
  }
}

function setTheme(theme) {
  applyTheme(theme);
  // Mettre a jour les boutons dans le picker
  document.querySelectorAll('.theme-option').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('theme-' + theme);
  if (btn) btn.classList.add('active');
  showToast('Theme : ' + theme, 'ok');
}

function quickToggleTheme() {
  const themes = ['dark', 'light', 'midnight'];
  const idx    = themes.indexOf(currentTheme);
  setTheme(themes[(idx + 1) % themes.length]);
}

function setFontSize(size) {
  currentFontSize = size;
  localStorage.setItem('nemo_fontsize', size);
  document.querySelectorAll('.msg-body').forEach(el => el.style.fontSize = size + 'px');
  document.querySelectorAll('.font-sz-btn').forEach(b => {
    b.classList.toggle('active', b.textContent.includes(size));
  });
  // Pour les futurs messages
  const root = document.documentElement;
  root.style.setProperty('--msg-font-size', size + 'px');
}

function toggleCompact() {
  isCompact = !isCompact;
  localStorage.setItem('nemo_compact', isCompact);
  document.documentElement.setAttribute('data-compact', isCompact);
  document.getElementById('compact-toggle').classList.toggle('active', isCompact);
}

function toggleMonoFont() {
  isMonoFont = !isMonoFont;
  localStorage.setItem('nemo_mono', isMonoFont);
  document.documentElement.setAttribute('data-monofont', isMonoFont);
  document.getElementById('mono-toggle').classList.toggle('active', isMonoFont);
}

// Appliquer les preferences au chargement
function applyStoredPrefs() {
  applyTheme(currentTheme);
  document.documentElement.setAttribute('data-compact', isCompact);
  document.documentElement.setAttribute('data-monofont', isMonoFont);
  if (isCompact)  document.getElementById('compact-toggle')?.classList.add('active');
  if (isMonoFont) document.getElementById('mono-toggle')?.classList.add('active');
  // Synchroniser le picker
  const btn = document.getElementById('theme-' + currentTheme);
  if (btn) {
    document.querySelectorAll('.theme-option').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }
  // Police
  const root = document.documentElement;
  root.style.setProperty('--msg-font-size', currentFontSize + 'px');
  document.querySelectorAll('.font-sz-btn').forEach(b => {
    b.classList.toggle('active', b.textContent.includes(currentFontSize));
  });
}


// ══════════════════════════════════════════════════════════════════════════════
// WORKSPACES
// ══════════════════════════════════════════════════════════════════════════════
function renderWorkspaceSelect(wsList, current) {
  const sel = document.getElementById('workspace-select');
  sel.innerHTML = wsList.map(w => `<option value="${escH(w)}" ${w===current?'selected':''}>${escH(w)}</option>`).join('');
}
async function switchWorkspace(name) {
  const r = await fetch('/api/workspace/switch', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})});
  if (!r.ok) { showToast('Erreur switch workspace', 'error'); return; }
  const cd = await fetch('/api/conversations').then(r=>r.json());
  conversations = cd.conversations || []; activeConvId = cd.active;
  renderConvList();
  if (activeConvId) await loadConvHistory(activeConvId); else clearMessages();
}
async function createWorkspace() {
  const name = prompt('Nom du nouveau workspace (lettres, chiffres, - _) :');
  if (!name) return;
  const d = await fetch('/api/workspace/create', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(r=>r.json());
  if (d.error) { showToast(d.error, 'error'); return; }
  workspaces = d.workspaces || []; renderWorkspaceSelect(workspaces, d.workspace);
  showToast(`Workspace "${d.workspace}" créé`, 'ok');
  await switchWorkspace(d.workspace);
}
async function deleteCurrentWorkspace() {
  const name = document.getElementById('workspace-select').value;
  if (name==='default') { showToast('Impossible de supprimer "default"', 'error'); return; }
  if (!confirm(`Supprimer le workspace "${name}" ?`)) return;
  const d = await fetch(`/api/workspace/${encodeURIComponent(name)}`, {method:'DELETE'}).then(r=>r.json());
  if (d.error) { showToast(d.error, 'error'); return; }
  workspaces = d.workspaces || []; renderWorkspaceSelect(workspaces, 'default');
  showToast(`"${name}" supprimé`, 'ok'); await switchWorkspace('default');
}
async function indexWorkspace() {
  const btn = document.querySelector('[onclick="indexWorkspace()"]');
  const orig = btn ? btn.innerHTML : '';
  if (btn) { btn.innerHTML = '⏳'; btn.disabled = true; }
  try {
    const d = await fetch('/api/index', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}).then(r=>r.json());
    if (d.error) showToast(d.error, 'error'); else showToast(d.message || `${d.indexed} fichiers indexés`, 'ok');
  } catch(e) { showToast('Erreur réseau', 'error'); }
  finally { if (btn) { btn.innerHTML = orig; btn.disabled = false; } }
}

// ══════════════════════════════════════════════════════════════════════════════
// IMPORT / EXPORT JSON CONVERSATIONS
// ══════════════════════════════════════════════════════════════════════════════
async function exportConvJson() {
  if (!activeConvId) { showToast('Aucune conversation active', 'error'); return; }
  window.open(`/api/conversations/${activeConvId}/export-json`, '_blank');
}

async function handleConvJsonImport(input) {
  const file = input.files[0]; if (!file) return;
  input.value = '';
  const form = new FormData(); form.append('file', file);
  try {
    const r = await fetch('/api/conversations/import-json', {method:'POST', body: form});
    const d = await r.json();
    if (!r.ok || d.error) { showToast(d.error || 'Erreur import', 'error'); return; }
    conversations.push({id: d.id, name: d.name, msg_count: d.msg_count});
    activeConvId = d.id; renderConvList(); clearMessages();
    await loadConvHistory(d.id);
    showToast(`Conversation "${d.name}" importée`, 'ok');
  } catch(e) { showToast('Erreur réseau: '+e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════════════════
// STOP STREAM (serveur)
// ══════════════════════════════════════════════════════════════════════════════
async function stopStream() {
  if (abortCtrl) abortCtrl.abort();  // coupe le fetch client
  try {
    await fetch('/api/stop', {method:'POST'});  // signal serveur
  } catch(e) {}
}

// ══════════════════════════════════════════════════════════════════════════════
// ZIP IMPORT
// ══════════════════════════════════════════════════════════════════════════════
async function handleZipSelect(input) {
  const file = input.files[0]; if (!file) return; input.value = '';
  if (!file.name.toLowerCase().endsWith('.zip')) { showToast('Seuls les .zip sont acceptés', 'error'); return; }
  showToast('Import ZIP en cours...', 'info');
  const form = new FormData(); form.append('file', file);
  try {
    const r = await fetch('/api/upload/zip', {method:'POST', body: form});
    const d = await r.json();
    if (!r.ok || d.error) { showToast(d.error || 'Erreur import ZIP', 'error'); return; }
    workspaces = d.workspaces || []; renderWorkspaceSelect(workspaces, d.workspace);
    showToast(`✓ ${d.files} fichiers → workspace "${d.workspace}"`, 'ok');
    await switchWorkspace(d.workspace); closeZipModal();
  } catch(e) { showToast('Erreur réseau: '+e.message, 'error'); }
}
function openZipModal()  { document.getElementById('zip-modal').classList.add('open'); }
function closeZipModal() { document.getElementById('zip-modal').classList.remove('open'); }

// ══════════════════════════════════════════════════════════════════════════════
// TOAST
// ══════════════════════════════════════════════════════════════════════════════
function showToast(msg, type='ok') {
  const c = {ok:'var(--green)', error:'var(--red)', info:'var(--cyan)'};
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:80px;right:20px;z-index:9999;padding:10px 18px;
    border-radius:8px;font-size:13px;background:var(--bg3);border:1px solid ${c[type]||c.ok};
    color:var(--text1);box-shadow:0 4px 16px rgba(0,0,0,.4);animation:fadeUp .2s ease;
    pointer-events:none;max-width:340px;`;
  t.textContent = msg; document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ══════════════════════════════════════════════════════════════════════════════
// CONVERSATIONS
// ══════════════════════════════════════════════════════════════════════════════
function renderConvList() {
  const list = document.getElementById('conv-list'); list.innerHTML = '';
  [...conversations].reverse().forEach(c => {
    const div = document.createElement('div');
    div.className = 'conv-item' + (c.id===activeConvId?' active':'');
    div.onclick = e => { if (!e.target.closest('input,button')) switchConv(c.id); };
    div.innerHTML = `
      <div class="conv-dot"></div>
      <div class="conv-name" title="${escH(c.name)}" ondblclick="startRename('${c.id}',this)">${escH(c.name)}</div>
      <div class="conv-count" id="cc-${c.id}">${c.msg_count}</div>
      <button class="conv-del" onclick="deleteConv('${c.id}',event)">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>`;
    list.appendChild(div);
  });
}
function startRename(cid, nameEl) {
  const cur = nameEl.textContent;
  const inp = document.createElement('input');
  inp.className = 'conv-rename-input'; inp.value = cur;
  nameEl.replaceWith(inp); inp.focus(); inp.select();
  const commit = async () => {
    const newName = inp.value.trim() || cur;
    await fetch(`/api/conversations/${cid}/rename`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:newName})});
    const conv = conversations.find(c=>c.id===cid);
    if (conv) conv.name = newName;
    renderConvList();
    if (cid===activeConvId) setConvName(newName);
  };
  inp.addEventListener('blur', commit);
  inp.addEventListener('keydown', e => { if (e.key==='Enter'){e.preventDefault();inp.blur();} if(e.key==='Escape'){inp.value=cur;inp.blur();} });
}
async function newChat() {
  const r = await fetch('/api/conversations', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
  const c = await r.json();
  conversations.push(c); activeConvId = c.id; renderConvList(); clearMessages(); setConvName(c.name);
}
async function switchConv(cid) {
  if (cid===activeConvId) return;
  const d = await fetch(`/api/conversations/${cid}`).then(r=>r.json());
  activeConvId = cid; renderConvList(); clearMessages();
  const conv = conversations.find(c=>c.id===cid); if (conv) setConvName(conv.name);
  const ms = (d.history||[]).filter(m=>m.role==='user'||m.role==='assistant');
  let n=0; for(const m of ms) {
    if (m.role==='user') { appendUserMsg(m.content,false); n++; }
    else if (m.content)  { appendFinishedMsg(m.content,''); }
  }
  document.getElementById('s-msgs').textContent = n;
}
async function loadConvHistory(cid) {
  const d = await fetch(`/api/conversations/${cid}`).then(r=>r.json());
  const conv = conversations.find(c=>c.id===cid); if (conv) setConvName(conv.name);
  const ms = (d.history||[]).filter(m=>m.role==='user'||m.role==='assistant');
  if (!ms.length) return;
  hideWelcome(); let n=0;
  for(const m of ms) {
    if(m.role==='user'){appendUserMsg(m.content,false);n++;}
    else if(m.content){appendFinishedMsg(m.content,'');}
  }
  document.getElementById('s-msgs').textContent = n;
}
async function deleteConv(cid,ev) {
  ev.stopPropagation();
  if (!confirm('Supprimer cette conversation ?')) return;
  const d = await fetch(`/api/conversations/${cid}`, {method:'DELETE'}).then(r=>r.json());
  conversations = conversations.filter(c=>c.id!==cid); activeConvId = d.active;
  renderConvList(); clearMessages();
  if (activeConvId) await loadConvHistory(activeConvId);
}
function setConvName(name) {
  const el = document.getElementById('header-title');
  if (el) el.innerHTML = `${escH(name)} <span>· Nemotron</span>`;
}

// ══════════════════════════════════════════════════════════════════════════════
// MEMORY MODAL
// ══════════════════════════════════════════════════════════════════════════════
async function openMemory() { document.getElementById('mem-modal').classList.add('open'); await refreshMemory(); }
function closeMemory() { document.getElementById('mem-modal').classList.remove('open'); }
async function refreshMemory() {
  const d = await fetch('/api/memory').then(r=>r.json());
  const mem = d.memory||{}, keys = Object.keys(mem);
  document.getElementById('mem-count').textContent = keys.length;
  const list = document.getElementById('mem-list');
  if (!keys.length) { list.innerHTML='<div class="mem-empty">Aucune mémoire. L\'agent peut en créer automatiquement.</div>'; return; }
  list.innerHTML = keys.map(k=>`
    <div class="mem-item">
      <div class="mem-key">${escH(k)}</div>
      <div class="mem-val">${escH(mem[k])}</div>
      <button class="mem-del" onclick="delMemory('${escH(k)}')"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
    </div>`).join('');
}
async function addMemory() {
  const key=document.getElementById('mem-key').value.trim(), val=document.getElementById('mem-val').value.trim();
  if (!key||!val) return;
  await fetch('/api/memory', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key,value:val})});
  document.getElementById('mem-key').value=''; document.getElementById('mem-val').value='';
  await refreshMemory();
}
async function delMemory(key) {
  await fetch(`/api/memory/${encodeURIComponent(key)}`, {method:'DELETE'}); await refreshMemory();
}

// ══════════════════════════════════════════════════════════════════════════════
// SLASH COMMANDS
// ══════════════════════════════════════════════════════════════════════════════
const SLASH_CMDS = [
  {cmd:'/new',       desc:'Nouvelle conversation',                badge:'local', action:()=>newChat()},
  {cmd:'/clear',     desc:'Effacer la conversation',              badge:'local', action:()=>clearChat()},
  {cmd:'/memory',    desc:'Mémoire persistante',                  badge:'local', action:()=>openMemory()},
  {cmd:'/config',    desc:'Config agent (steps, timeout...)',       badge:'local', action:()=>openConfig()},
  {cmd:'/reasoning', desc:'Toggle raisonnement étendu',           badge:'local', action:()=>toggleReasoning()},
  {cmd:'/model',     desc:'Changer de modèle',                    badge:'nav',   action:()=>document.getElementById('model-select').focus()},
  {cmd:'/export',    desc:'Exporter conversation (.md)',          badge:'local', action:()=>exportConvMd()},
  {cmd:'/exportjson',desc:'Exporter conversation (.json)',        badge:'local', action:()=>exportConvJson()},
  {cmd:'/import',    desc:'Importer projet ZIP',                  badge:'zip',   action:()=>openZipModal()},
  {cmd:'/workspace', desc:'Créer un workspace',                   badge:'ws',    action:()=>createWorkspace()},
  {cmd:'/index',     desc:'Indexer le workspace',                 badge:'local', action:()=>indexWorkspace()},
  {cmd:'/search',    desc:'Recherche sémantique',                 badge:'local', action:()=>openSemanticSearch()},
  {cmd:'/cost',      desc:'Coût de la session',                   badge:'info',  action:()=>showCostInfo()},
  {cmd:'/stop',      desc:'Arrêter le stream',                    badge:'local', action:()=>stopStream()},
  {cmd:'/keys',      desc:'Raccourcis clavier',                   badge:'info',  action:()=>openShortcuts()},
];
let slashIdx=-1, slashVisible=false;
function buildSlashMenu(filter='') {
  const menu=document.getElementById('slash-menu');
  const items=SLASH_CMDS.filter(c=>c.cmd.startsWith(filter)||!filter);
  if (!items.length){closeSlash();return;}
  menu.innerHTML=items.map((c,i)=>`<div class="slash-item" data-idx="${i}" onclick="runSlash(${i},'${filter}')">
    <span class="slash-cmd">${escH(c.cmd)}</span><span class="slash-desc">${escH(c.desc)}</span><span class="slash-badge">${escH(c.badge)}</span></div>`).join('');
  menu.classList.add('open'); slashVisible=true; slashIdx=-1;
}
function closeSlash(){document.getElementById('slash-menu').classList.remove('open');slashVisible=false;slashIdx=-1;}
function runSlash(idx,filter){
  const items=SLASH_CMDS.filter(c=>c.cmd.startsWith(filter)||!filter);
  const item=items[idx]; if(!item) return;
  closeSlash(); document.getElementById('input').value=''; document.getElementById('input').style.height='auto';
  item.action();
}
function handleSlashKey(e){
  if(!slashVisible) return false;
  const menu=document.getElementById('slash-menu'), items=menu.querySelectorAll('.slash-item');
  if(e.key==='Escape'){closeSlash();e.preventDefault();return true;}
  if(e.key==='ArrowDown'){slashIdx=Math.min(slashIdx+1,items.length-1);items.forEach((el,i)=>el.classList.toggle('selected',i===slashIdx));e.preventDefault();return true;}
  if(e.key==='ArrowUp'){slashIdx=Math.max(slashIdx-1,0);items.forEach((el,i)=>el.classList.toggle('selected',i===slashIdx));e.preventDefault();return true;}
  if(e.key==='Enter'||e.key==='Tab'){
    if(slashIdx>=0){runSlash(slashIdx,document.getElementById('input').value);e.preventDefault();return true;}
    if(e.key==='Tab'){runSlash(0,document.getElementById('input').value);e.preventDefault();return true;}
  }
  return false;
}

async function exportConvMd() {
  if (!activeConvId) return;
  const d = await fetch(`/api/conversations/${activeConvId}`).then(r=>r.json());
  let md = `# ${d.name}\n\n`;
  for(const m of d.history||[]) {
    if(m.role==='user') md+=`## 👤 Vous\n\n${m.content}\n\n`;
    else if(m.role==='assistant'&&m.content) md+=`## 🤖 Nemotron\n\n${m.content}\n\n`;
  }
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([md],{type:'text/markdown'}));
  a.download=`${d.name.replace(/[^a-z0-9]/gi,'_')}.md`; a.click();
}
function showCostInfo(){showToast(`Coût session: ${totalCost===0?'$0.00':'$'+totalCost.toFixed(8)}`,'info');}

// ══════════════════════════════════════════════════════════════════════════════
// RACCOURCIS CLAVIER MODAL
// ══════════════════════════════════════════════════════════════════════════════
function openShortcuts()  { document.getElementById('shortcuts-modal').classList.add('open'); }
function closeShortcuts() { document.getElementById('shortcuts-modal').classList.remove('open'); }

// ══════════════════════════════════════════════════════════════════════════════
// MESSAGES - DOM helpers
// ══════════════════════════════════════════════════════════════════════════════
function hideWelcome(){const w=document.getElementById('welcome');if(w)w.style.display='none';}
function clearMessages(){
  document.getElementById('messages').innerHTML='<div class="welcome" id="welcome" style="display:none"></div>';
  agentBodyEl=null;toolContainer=null;streamBuf='';
}
function appendUserMsg(text,scroll=true){
  hideWelcome();
  const now=new Date().toLocaleTimeString('fr',{hour:'2-digit',minute:'2-digit'});
  const div=document.createElement('div'); div.className='msg user-msg';
  div.innerHTML=`
    <div class="msg-header">
      <div class="msg-avatar" style="background:var(--s5);color:var(--t2)">V</div>
      <span class="msg-who" style="color:var(--t2)">Vous</span>
      <span class="msg-time">${now}</span>
    </div>
    <div class="msg-body">${renderMD(text)}</div>`;
  msgs().appendChild(div); if(scroll) scrollBot();
}
function startStreamMsg(model){
  hideWelcome();
  const wrap=document.createElement('div'); wrap.className='msg agent-msg';
  const hdr=document.createElement('div'); hdr.className='msg-header';
  const now=new Date().toLocaleTimeString('fr',{hour:'2-digit',minute:'2-digit'});
  hdr.innerHTML=`
    <div class="msg-avatar">N</div>
    <span class="msg-who">Nemotron</span>
    <span class="msg-model">${escH(model)}</span>
    <span class="msg-time">${now}</span>`;
  const body=document.createElement('div'); body.className='msg-body streaming';
  wrap.appendChild(hdr); wrap.appendChild(body); msgs().appendChild(wrap);
  agentBodyEl=body; toolContainer=null; scrollBot();
}
function appendToken(text){
  if(!agentBodyEl) return; streamBuf+=text; agentBodyEl.innerHTML=renderMD(streamBuf); scrollBot();
}
function finalizeStreamMsg(model){
  if(!agentBodyEl) return;
  agentBodyEl.classList.remove('streaming'); agentBodyEl.innerHTML=renderMD(streamBuf);
  agentBodyEl.querySelectorAll('pre code').forEach(el=>{try{hljs.highlightElement(el);}catch{}});
  streamBuf=''; agentBodyEl=null;
  // Fermer le bloc outils une fois la reponse finalisee
  if (toolContainer) { toolContainer.open = false; toolContainer = null; }
  scrollBot();
}
function appendFinishedMsg(text,model){
  hideWelcome();
  const wrap=document.createElement('div'); wrap.className='msg agent-msg';
  const hdr=document.createElement('div'); hdr.className='msg-header';
  hdr.innerHTML=`<div class="msg-avatar">N</div><span class="msg-who">Nemotron</span>${model?`<span class="msg-model">${escH(model)}</span>`:''}`;
  const body=document.createElement('div'); body.className='msg-body';
  body.innerHTML=renderMD(text);
  body.querySelectorAll('pre code').forEach(el=>{try{hljs.highlightElement(el);}catch{}});
  wrap.appendChild(hdr); wrap.appendChild(body); msgs().appendChild(wrap); scrollBot();
}
function appendThinking(step,max){
  removeThinking();
  const div=document.createElement('div'); div.id='thinking-indicator'; div.className='thinking-msg';
  div.innerHTML=`<div class="thinking-dots"><span></span><span></span><span></span></div>
    <span style="font-size:11px;color:var(--text3);margin-left:8px">Étape ${step}/${max}</span>`;
  msgs().appendChild(div); scrollBot();
}
function removeThinking(){const t=document.getElementById('thinking-indicator');if(t)t.remove();}

function appendReasoningToken(text) {
  // Crée un bloc "réflexion" dépliable la première fois
  if (!reasoningEl) {
    removeThinking();
    const wrap  = document.createElement('details');
    wrap.className = 'reasoning-block';
    const summ  = document.createElement('summary');
    summ.className = 'reasoning-summary';
    summ.textContent = '⚡ Raisonnement interne';
    const body  = document.createElement('div');
    body.className = 'reasoning-body';
    wrap.appendChild(summ); wrap.appendChild(body);
    msgs().appendChild(wrap);
    reasoningEl = body;
    scrollBot();
  }
  reasoningBuf += text;
  reasoningEl.textContent = reasoningBuf;
  scrollBot();
}
function appendSkillBadges(skills){
  if(!skills||!skills.length) return;
  const div=document.createElement('div'); div.className='skill-badges';
  div.innerHTML=skills.map(s=>`<span class="skill-badge">📚 ${escH(s)}</span>`).join('');
  msgs().appendChild(div); scrollBot();
}
function appendToolCall(name, args) {
  removeThinking();

  // Creer le bloc <details> au premier outil du step
  if (!toolContainer) {
    const details  = document.createElement('details');
    details.className = 'tools-block';
    details.open    = true;   // ouvert pendant le stream

    const summary  = document.createElement('summary');
    summary.className = 'tools-summary';
    summary.innerHTML = '<span class="tools-icon">⚙</span> <span class="tools-label">Outils</span> <span class="tools-count">0</span>';

    const body     = document.createElement('div');
    body.className = 'tools-body';

    details.appendChild(summary);
    details.appendChild(body);
    msgs().appendChild(details);
    toolContainer = details;
  }

  // Mettre a jour le compteur dans le summary
  const body    = toolContainer.querySelector('.tools-body');
  const counter = toolContainer.querySelector('.tools-count');
  const count   = body.querySelectorAll('.tool-row').length + 1;
  if (counter) counter.textContent = count;

  // Construire la ligne outil
  const argsStr = Object.keys(args).length
    ? Object.entries(args).map(([k,v]) => `${k}: ${trunc(String(v), 100)}`).join('  ·  ')
    : '';

  const row = document.createElement('div');
  row.className = 'tool-row';
  row.innerHTML = `
    <div class="tool-row-head">
      <span class="tool-name">${escH(name)}</span>
      ${argsStr ? `<span class="tool-args">${escH(argsStr)}</span>` : ''}
      <span class="tool-status running">•••</span>
    </div>`;
  body.appendChild(row);
  scrollBot();
}

function appendToolResult(name, result, cached) {
  if (!toolContainer) return;
  const body  = toolContainer.querySelector('.tools-body');
  if (!body) return;
  const rows  = [...body.querySelectorAll('.tool-row')];
  let last = null;
  for (let i = rows.length - 1; i >= 0; i--) {
    if (rows[i].querySelector('.tool-status.running')) { last = rows[i]; break; }
  }
  if (!last) last = rows[rows.length - 1];
  if (!last) return;

  const st = last.querySelector('.tool-status');
  if (st) {
    st.className   = 'tool-status done';
    st.textContent = cached ? '⚡' : '✓';
  }

  const pre = document.createElement('div');
  pre.className   = 'tool-result';
  pre.textContent = trunc(result, 400);
  last.appendChild(pre);

  // Mettre a jour le label du summary avec les noms d outils
  const summary = toolContainer.querySelector('.tools-summary');
  const allNames = [...body.querySelectorAll('.tool-name')].map(el => el.textContent);
  const unique   = [...new Set(allNames)];
  const label    = toolContainer.querySelector('.tools-label');
  if (label) label.textContent = unique.slice(0, 3).join(', ') + (unique.length > 3 ? '...' : '');

  scrollBot();
}
function msgs(){return document.getElementById('messages');}
function scrollBot(){const m=msgs();m.scrollTop=m.scrollHeight;}

// ══════════════════════════════════════════════════════════════════════════════
// SEND / STREAM
// ══════════════════════════════════════════════════════════════════════════════
async function sendMsg() {
  if (streaming) return;
  const inp = document.getElementById('input');
  let text  = inp.value.trim();
  if (!text && !uploadedFile) return;
  if (text.startsWith('/')) return;
  inp.value=''; inp.style.height='auto'; closeSlash();

  let fullMsg = text;
  if (uploadedFile) {
    fullMsg = (text?text+'\n\n':'')+`[Fichier joint : ${uploadedFile.name} - ${uploadedFile.lines} lignes]\n\`\`\`\n${uploadedFile.content}\n\`\`\`\n`;
    clearUpload();
  }
  appendUserMsg(fullMsg.length>300?text+(uploadedFile?` 📎 ${uploadedFile?.name||''}`:''): fullMsg);
  const n=parseInt(document.getElementById('s-msgs').textContent||0)+1;
  document.getElementById('s-msgs').textContent=n;
  const conv=conversations.find(c=>c.id===activeConvId);
  if(conv){conv.msg_count=n;renderConvList();}

  setStreaming(true);
  agentBodyEl=null; toolContainer=null; streamBuf=''; reasoningBuf=''; reasoningEl=null;
  abortCtrl=new AbortController(); let streamModel=currentModel;

  try {
    const resp=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:fullMsg}),signal:abortCtrl.signal});
    const reader=resp.body.getReader(), decoder=new TextDecoder(); let buf='';
    while(true){
      const {done,value}=await reader.read(); if(done) break;
      buf+=decoder.decode(value,{stream:true});
      const lines=buf.split('\n'); buf=lines.pop();
      for(const line of lines){
        if(!line.startsWith('data: ')) continue;
        try{const ev=JSON.parse(line.slice(6)); streamModel=handleEvt(ev,streamModel);}catch{}
      }
    }
  } catch(e) {
    if(e.name!=='AbortError'){removeThinking();startStreamMsg(currentModel);appendToken('Erreur de connexion.');finalizeStreamMsg(currentModel);}
  } finally {
    setStreaming(false);
    if(streamBuf&&agentBodyEl) finalizeStreamMsg(streamModel);
    // Rafraîchir le token budget
    fetch('/api/status').then(r=>r.json()).then(st=>{
      if(st.token_budget) updateTokenBudget(st.token_budget);
      // Mettre à jour le nom de la conv si auto-nommée
      if (activeConvId) {
        fetch(`/api/conversations`).then(r=>r.json()).then(cd=>{
          const updated = (cd.conversations||[]).find(c=>c.id===activeConvId);
          if (updated && updated.name !== conversations.find(c=>c.id===activeConvId)?.name) {
            conversations = cd.conversations || [];
            renderConvList(); setConvName(updated.name);
          }
        }).catch(()=>{});
      }
    }).catch(()=>{});
  }
}

function handleEvt(ev, model) {
  switch(ev.type) {
    case 'thinking': appendThinking(ev.step, ev.max); break;
    case 'reasoning_token': appendReasoningToken(ev.text); break;
    case 'skill':    appendSkillBadges(ev.skills); break;
    case 'info':     /* info contextuelle silencieuse */ break;
    case 'token':    removeThinking(); if(!agentBodyEl) startStreamMsg(model); appendToken(ev.text); break;
    case 'tool_call':removeThinking(); if(streamBuf&&agentBodyEl) finalizeStreamMsg(model); appendToolCall(ev.name,ev.args||{}); break;
    case 'tool_result': appendToolResult(ev.name,ev.result||'',ev.cached||false); break;
    case 'stopped':  removeThinking(); if(streamBuf&&agentBodyEl) finalizeStreamMsg(model);
                     startStreamMsg(model); appendToken('⏹ Stream arrêté.'); finalizeStreamMsg(model); break;
    case 'done':     finalizeStreamMsg(ev.model||model); if(ev.metrics) updateStats(ev.metrics); model=ev.model||model; break;
    case 'error':    removeThinking(); if(streamBuf&&agentBodyEl) finalizeStreamMsg(model);
                     else startStreamMsg(model); appendToken('⚠ '+(ev.text||'Erreur inconnue')); finalizeStreamMsg(model); break;
  }
  return model;
}

function setStreaming(val){
  streaming=val;
  document.getElementById('send-btn').disabled=val;
  document.getElementById('stop-btn').style.display=val?'flex':'none';
  setStatus(val?'En cours...':'Connecté',val?'busy':'ok');
}
async function clearChat(){
  if(!confirm('Effacer cette conversation ?')) return;
  await fetch('/api/clear',{method:'POST'});
  clearMessages(); document.getElementById('s-msgs').textContent='0';
  updateTokenBudget({used:0, max:tokenBudget.max});
  const conv=conversations.find(c=>c.id===activeConvId);
  if(conv){conv.msg_count=0;renderConvList();}
}

// ══════════════════════════════════════════════════════════════════════════════
// UPLOAD FICHIER TEXTE
// ══════════════════════════════════════════════════════════════════════════════
async function handleFileSelect(input){
  const file=input.files[0]; if(!file) return; input.value='';
  if(file.name.toLowerCase().endsWith('.zip')){
    showToast('Fichier ZIP → utilise /import ou le bouton Import ZIP','info');
    openZipModal(); return;
  }
  const form=new FormData(); form.append('file',file);
  try{
    const r=await fetch('/api/upload',{method:'POST',body:form});
    const d=await r.json();
    if(!r.ok||d.error){showToast(d.error||'Erreur upload','error');return;}
    uploadedFile={name:d.filename,content:d.content,lines:d.lines,size:d.size};
    showUploadPill(d.filename,d.lines,d.size); document.getElementById('input').focus();
  }catch(e){showToast('Erreur réseau: '+e.message,'error');}
}
function showUploadPill(name,lines,size){
  const p=document.getElementById('upload-preview'), kb=(size/1024).toFixed(1);
  p.innerHTML=`<div class="upload-pill">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
    <span class="upload-pill-name">${escH(name)}</span>
    <span class="upload-pill-info">${lines} lignes · ${kb} KB</span>
    <button class="upload-pill-del" onclick="clearUpload()"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
  </div>`;
  p.style.display='block';
}
function clearUpload(){uploadedFile=null;const p=document.getElementById('upload-preview');p.innerHTML='';p.style.display='none';}

// ══════════════════════════════════════════════════════════════════════════════
// INPUT - ENTER = nouvelle ligne, Shift+Enter = envoyer
// ══════════════════════════════════════════════════════════════════════════════
function handleKey(e) {
  if (handleSlashKey(e)) return;
  // Shift+Enter → envoyer
  if (e.key === 'Enter' && e.shiftKey) {
    e.preventDefault();
    sendMsg();
    return;
  }
  // Enter seul → nouvelle ligne (comportement naturel du textarea)
  // On ne fait RIEN → le navigateur insère un \n comme prévu
}

function handleInput(el){
  el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,200)+'px';
  const val=el.value;
  if(val.startsWith('/')&&!val.includes(' ')) buildSlashMenu(val); else closeSlash();
}
function quick(text){const inp=document.getElementById('input');inp.value=text;inp.style.height='auto';inp.style.height=Math.min(inp.scrollHeight,200)+'px';sendMsg();}

// ══════════════════════════════════════════════════════════════════════════════
// SIDEBAR / SEMANTIC SEARCH
// ══════════════════════════════════════════════════════════════════════════════
function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open');document.getElementById('overlay').classList.toggle('open');}
function openSemanticSearch(){document.getElementById('semantic-modal').classList.add('open');}
function closeSemantic(){document.getElementById('semantic-modal').classList.remove('open');}
async function performSemanticSearch(){
  const q=document.getElementById('semantic-query').value.trim(); if(!q) return;
  const btn=document.querySelector('[onclick="performSemanticSearch()"]');
  if(btn){btn.textContent='Recherche...';btn.disabled=true;}
  try{
    const r=await fetch('/api/search/semantic',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})});
    const results=await r.json();
    const container=document.getElementById('semantic-results');
    if(r.status===400&&results.error){container.innerHTML=`<div class="mem-empty" style="color:var(--red)">${escH(results.error)}</div>`;return;}
    if(!results.length){container.innerHTML='<div class="mem-empty">Aucun résultat.</div>';return;}
    container.innerHTML=results.map(res=>`<div class="search-result"><div class="search-result-path">${escH(res.path)}<span class="search-score">score: ${res.score?.toFixed(3)}</span></div><pre class="search-result-content">${escH(res.content)}</pre></div>`).join('');
  }catch(e){showToast('Erreur: '+e.message,'error');}
  finally{if(btn){btn.textContent='Rechercher';btn.disabled=false;}}
}

// ══════════════════════════════════════════════════════════════════════════════
// COPY CODE / MARKDOWN / UTILS
// ══════════════════════════════════════════════════════════════════════════════
function copyCode(id,btn){
  const el=document.getElementById(id+'-txt'); if(!el) return;
  navigator.clipboard.writeText(el.textContent||el.innerText).then(()=>{
    btn.classList.add('copied');
    btn.innerHTML=`<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Copié !`;
    setTimeout(()=>{btn.classList.remove('copied');btn.innerHTML=`<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copier`;},2000);
  }).catch(()=>{const ta=document.createElement('textarea');ta.value=el.textContent;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();btn.textContent='✓';setTimeout(()=>btn.textContent='Copier',2000);});
}
function renderMD(text) {
  if (!text) return '';

  const placeholders = [];
  const ph = (html) => { placeholders.push(html); return `%%PH_${placeholders.length-1}%%`; };

  // 1. Extraire blocs de code
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const id = 'cb-' + Math.random().toString(36).slice(2, 8);
    const l  = lang || 'plaintext';
    return ph(`<div class="code-block">
      <div class="code-header">
        <span class="code-lang">${escH(l)}</span>
        <button class="copy-btn" onclick="copyCode('${id}',this)">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          Copier
        </button>
      </div>
      <pre><code id="${id}-txt" class="language-${escH(l)}">${escH(code.trimEnd())}</code></pre>
    </div>`);
  });

  // 2. Tableaux GFM - traiter AVANT escH
  text = text.replace(/((?:^\|.+\|\s*\n)+)/gm, (block) => {
    const rows = block.trim().split('\n').filter(r => r.trim());
    const dataRows = rows.filter(r => !/^\|[-:| ]+\|/.test(r));
    if (dataRows.length < 1) return block;

    const headerCells = dataRows[0]
      .split('|').slice(1, -1)
      .map(c => `<th>${escH(c.trim())}</th>`).join('');
    const bodyRows = dataRows.slice(1).map(row => {
      const cells = row.split('|').slice(1, -1)
        .map(c => `<td>${inlineMD(c.trim())}</td>`).join('');
      return `<tr>${cells}</tr>`;
    }).join('');

    return ph(`<div class="md-table-wrap"><table>
      <thead><tr>${headerCells}</tr></thead>
      <tbody>${bodyRows}</tbody>
    </table></div>`);
  });

  // 3. Maintenant on peut escaper le reste sans toucher aux placeholders
  let t = escH(text);

  // 4. Titres
  t = t.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  t = t.replace(/^## (.+)$/gm,  '<h2>$1</h2>');
  t = t.replace(/^# (.+)$/gm,   '<h1>$1</h1>');

  // 5. HR
  t = t.replace(/^---$/gm, '<hr>');

  // 6. Blockquote
  t = t.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

  // 7. Listes
  t = t.replace(/^[*-] (.+)$/gm, '<li>$1</li>');
  t = t.replace(/(<li>[\s\S]*?<\/li>\n?)+/g, s => `<ul>${s}</ul>`);
  t = t.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

  // 8. Inline
  t = t.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  t = t.replace(/\*\*(.+?)\*\*/g,     '<strong>$1</strong>');
  t = t.replace(/\*(.+?)\*/g,         '<em>$1</em>');
  t = t.replace(/`([^`\n]+)`/g,       '<code>$1</code>');
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // 9. Paragraphes
  t = t.split(/\n{2,}/).map(para => {
    const tr = para.trim();
    if (!tr) return '';
    if (/^<(h[1-3]|ul|ol|li|hr|blockquote|div|%%PH_)/.test(tr)) return para;
    return `<p>${para.replace(/\n/g,'<br>')}</p>`;
  }).join('');

  // 10. Restaurer les placeholders
  t = t.replace(/%%PH_(\d+)%%/g, (_, i) => placeholders[parseInt(i)] || '');

  return t;
}

function inlineMD(raw) {
  // Inline markdown sur texte brut (pour cellules de tableau)
  let t = escH(raw);
  return inlineMDEscaped(t);
}

function inlineMDEscaped(t) {
  // bold & italic (sur texte déjà HTML-escapé)
  t = t.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  t = t.replace(/\*\*(.+?)\*\*/g,       '<strong>$1</strong>');
  t = t.replace(/\*(.+?)\*/g,             '<em>$1</em>');
  t = t.replace(/`([^`\n]+)`/g,            '<code>$1</code>');
  // liens [text](url)
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return t;
}
function escH(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function trunc(s,n){s=String(s||'');return s.length>n?s.slice(0,n)+'...':s;}

// ══════════════════════════════════════════════════════════════════════════════
// RACCOURCIS CLAVIER GLOBAUX
// ══════════════════════════════════════════════════════════════════════════════
document.addEventListener('keydown', e => {
  // Fermer les modaux
  if(e.key==='Escape'){ closeMemory(); closeSemantic(); closeSlash(); closeZipModal(); closeConfig(); closeShortcuts(); return; }
  // Ne pas intercepter si on tape dans un champ
  const tag = e.target.tagName;
  if(tag==='INPUT'||tag==='TEXTAREA') return;

  if((e.ctrlKey||e.metaKey)&&e.key==='k'){ e.preventDefault(); document.getElementById('input').focus(); return; }
  if((e.ctrlKey||e.metaKey)&&e.key==='n'){ e.preventDefault(); newChat(); return; }
  if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key==='M'){ e.preventDefault(); openMemory(); return; }
  if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key==='S'){ e.preventDefault(); openSemanticSearch(); return; }
  if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key==='C'){ e.preventDefault(); openConfig(); return; }
  if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key==='E'){ e.preventDefault(); exportConvMd(); return; }
  if(e.key==='?'){ openShortcuts(); return; }
});

document.getElementById('mem-modal').addEventListener('click',function(e){if(e.target===this)closeMemory();});
document.getElementById('semantic-modal').addEventListener('click',function(e){if(e.target===this)closeSemantic();});

// ══════════════════════════════════════════════════════════════════════════════
// BOOT
// ══════════════════════════════════════════════════════════════════════════════
init();
