// ══════════════════════════════════════════════════════════════════════════════
// STATE (conservé de l'original, on ajoute quelques variables)
// ══════════════════════════════════════════════════════════════════════════════
let streaming     = false;
let abortCtrl     = null;
let reasoningOn   = false;
let activeConvId  = null;
let conversations = [];
let currentModel  = 'qwen/qwen3-coder:free';
let toolContainer = null;
let agentBodyEl   = null;
let streamBuf     = '';
let totalCost     = 0;
let uploadedFile  = null;   // { name, content, lines, size }

// Nouvelles variables pour workspace
let workspaces = [];

// ══════════════════════════════════════════════════════════════════════════════
// INIT (modifiée pour charger les workspaces)
// ══════════════════════════════════════════════════════════════════════════════
async function init() {
  try {
    const [sR, cR] = await Promise.all([fetch('/api/status'), fetch('/api/conversations')]);
    const st = await sR.json();
    const cd = await cR.json();

    currentModel   = st.model || currentModel;
    reasoningOn    = st.reasoning_enabled || false;
    activeConvId   = st.active_conv || cd.active;
    totalCost      = st.metrics?.cost_usd || 0;

    document.getElementById('model-select').value = currentModel;
    setReasoningUI(reasoningOn);
    showKeySection(!st.api_key_set);
    setStatus(st.api_key_set ? 'Connecté' : 'Clé manquante', st.api_key_set ? 'ok' : 'off');
    if (st.metrics) updateStats(st.metrics);
    document.getElementById('mem-count').textContent = st.memory_count || 0;
    if (st.timeout) document.getElementById('timeout-badge').textContent = `⏱ ${st.timeout}s`;

    // Workspace
    workspaces = st.workspaces || [];
    const wsSel = document.getElementById('workspace-select');
    wsSel.innerHTML = workspaces.map(w => `<option value="${w}">${w}</option>`).join('');
    wsSel.value = st.workspace || 'default';

    conversations = cd.conversations || [];
    renderConvList();
    if (activeConvId) await loadConvHistory(activeConvId);
  } catch(e) {
    setStatus('Hors ligne', 'off');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// STATUS / STATS / COST (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
function setStatus(text, state) {
  document.getElementById('status-txt').textContent = text;
  document.getElementById('dot').className = 'dot' + (state === 'ok' ? '' : state === 'off' ? ' off' : ' busy');
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
  const str = totalCost === 0 ? '$0.00' : '$' + totalCost.toFixed(8);
  const strShort = totalCost === 0 ? '$0.00' : totalCost < 0.001
    ? '$' + totalCost.toFixed(6)
    : '$' + totalCost.toFixed(4);

  document.getElementById('s-cost').textContent   = str;
  document.getElementById('s-cost').className     = 'cost-val' + (totalCost > 0 ? ' nonzero' : '');
  document.getElementById('cost-badge').textContent = strShort;
  document.getElementById('cost-badge').className   = 'cost-badge' + (totalCost > 0 ? ' nonzero' : '');
}

function fmt(n) {
  if (!n) return '0';
  return n >= 1000 ? (n/1000).toFixed(1)+'k' : String(n);
}

// ══════════════════════════════════════════════════════════════════════════════
// REASONING TOGGLE (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
async function toggleReasoning() {
  try {
    const r = await fetch('/api/reasoning', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({})
    });
    const d = await r.json();
    reasoningOn = d.reasoning_enabled;
    setReasoningUI(reasoningOn);
  } catch(e) { console.error(e); }
}
function setReasoningUI(on) {
  document.getElementById('reasoning-toggle').classList.toggle('active', on);
  document.getElementById('reasoning-chip').style.display = on ? 'flex' : 'none';
}

// ══════════════════════════════════════════════════════════════════════════════
// MODEL (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
async function changeModel(model) {
  try {
    await fetch('/api/model', { method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({model}) });
    currentModel = model;
    // Mise à jour badge timeout
    const r = await fetch('/api/status');
    const d = await r.json();
    if (d.timeout) document.getElementById('timeout-badge').textContent = `⏱ ${d.timeout}s`;
  } catch(e) { console.error(e); }
}

// ══════════════════════════════════════════════════════════════════════════════
// API KEY (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
function showKeySection(show) {
  document.getElementById('key-section').style.display = show ? 'block' : 'none';
}
async function saveKey() {
  const inp = document.getElementById('key-input');
  const key = inp.value.trim();
  if (!key) return;
  const r = await fetch('/api/setkey', { method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({key}) });
  const d = await r.json();
  if (d.ok) {
    inp.value = '';
    const st = document.getElementById('key-status');
    st.textContent = '✓ Clé enregistrée'; st.style.color = 'var(--green)';
    setStatus('Connecté', 'ok');
    setTimeout(() => { showKeySection(false); st.textContent = ''; }, 2000);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// CONVERSATIONS (inchangé, mais on ajoute une fonction loadConvs si besoin)
// ══════════════════════════════════════════════════════════════════════════════
function renderConvList() {
  const list = document.getElementById('conv-list');
  list.innerHTML = '';
  [...conversations].reverse().forEach(c => {
    const div = document.createElement('div');
    div.className = 'conv-item' + (c.id === activeConvId ? ' active' : '');
    div.onclick = (e) => { if (!e.target.closest('input,button')) switchConv(c.id); };
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
  inp.className   = 'conv-rename-input';
  inp.value       = cur;
  nameEl.replaceWith(inp);
  inp.focus(); inp.select();

  const commit = async () => {
    const newName = inp.value.trim() || cur;
    await fetch(`/api/conversations/${cid}/rename`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name: newName}),
    });
    const conv = conversations.find(c => c.id === cid);
    if (conv) conv.name = newName;
    renderConvList();
    if (cid === activeConvId) setConvName(newName);
  };
  inp.addEventListener('blur', commit);
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); inp.blur(); }
    if (e.key === 'Escape') { inp.value = cur; inp.blur(); }
  });
}

async function newChat() {
  const r = await fetch('/api/conversations', { method:'POST',
    headers:{'Content-Type':'application/json'}, body:'{}' });
  const c = await r.json();
  conversations.push(c);
  activeConvId = c.id;
  renderConvList();
  clearMessages();
  setConvName(c.name);
}

async function switchConv(cid) {
  if (cid === activeConvId) return;
  const r = await fetch(`/api/conversations/${cid}`);
  const d = await r.json();
  activeConvId = cid;
  renderConvList();
  clearMessages();
  const conv = conversations.find(c => c.id === cid);
  if (conv) setConvName(conv.name);
  const msgs = (d.history || []).filter(m => m.role === 'user' || m.role === 'assistant');
  let n = 0;
  for (const m of msgs) {
    if (m.role === 'user')      { appendUserMsg(m.content, false); n++; }
    else if (m.content)         { appendFinishedMsg(m.content, ''); }
  }
  document.getElementById('s-msgs').textContent = n;
}

async function loadConvHistory(cid) {
  const r = await fetch(`/api/conversations/${cid}`);
  const d = await r.json();
  const conv = conversations.find(c => c.id === cid);
  if (conv) setConvName(conv.name);
  const msgs = (d.history || []).filter(m => m.role === 'user' || m.role === 'assistant');
  if (!msgs.length) return;
  hideWelcome(); let n = 0;
  for (const m of msgs) {
    if (m.role === 'user')  { appendUserMsg(m.content, false); n++; }
    else if (m.content)     { appendFinishedMsg(m.content, ''); }
  }
  document.getElementById('s-msgs').textContent = n;
}

async function deleteConv(cid, ev) {
  ev.stopPropagation();
  if (!confirm('Supprimer cette conversation ?')) return;
  const r = await fetch(`/api/conversations/${cid}`, { method:'DELETE' });
  const d = await r.json();
  conversations = conversations.filter(c => c.id !== cid);
  activeConvId  = d.active;
  renderConvList();
  clearMessages();
  if (activeConvId) await loadConvHistory(activeConvId);
}

function setConvName(name) {
  document.getElementById('header-conv-name').innerHTML =
    `${escH(name)} <span>· Dev Agent</span>`;
}

// ══════════════════════════════════════════════════════════════════════════════
// MEMORY MODAL (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
async function openMemory() {
  document.getElementById('mem-modal').classList.add('open');
  await refreshMemory();
}
function closeMemory() {
  document.getElementById('mem-modal').classList.remove('open');
}
async function refreshMemory() {
  const r = await fetch('/api/memory');
  const d = await r.json();
  const mem  = d.memory || {};
  const keys = Object.keys(mem);
  document.getElementById('mem-count').textContent = keys.length;
  const list = document.getElementById('mem-list');
  if (!keys.length) {
    list.innerHTML = '<div class="mem-empty">Aucune mémoire. Ajoutes-en pour que l\'agent se souvienne de toi.</div>';
    return;
  }
  list.innerHTML = keys.map(k => `
    <div class="mem-item">
      <div class="mem-key">${escH(k)}</div>
      <div class="mem-val">${escH(mem[k])}</div>
      <button class="mem-del" onclick="delMemory('${escH(k)}')">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>`).join('');
}
async function addMemory() {
  const key = document.getElementById('mem-key').value.trim();
  const val = document.getElementById('mem-val').value.trim();
  if (!key || !val) return;
  await fetch('/api/memory', { method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({key, value:val}) });
  document.getElementById('mem-key').value = '';
  document.getElementById('mem-val').value = '';
  await refreshMemory();
}
async function delMemory(key) {
  await fetch(`/api/memory/${encodeURIComponent(key)}`, { method:'DELETE' });
  await refreshMemory();
}

// ══════════════════════════════════════════════════════════════════════════════
// SLASH COMMANDS (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
const SLASH_CMDS = [
  { cmd:'/clear',     desc:'Efface la conversation courante',   badge:'local',  action:()=>clearChat() },
  { cmd:'/new',       desc:'Nouvelle conversation',             badge:'local',  action:()=>newChat()   },
  { cmd:'/memory',    desc:'Ouvrir la mémoire persistante',     badge:'local',  action:()=>openMemory()},
  { cmd:'/reasoning', desc:'Toggle raisonnement étendu',        badge:'local',  action:()=>toggleReasoning()},
  { cmd:'/model',     desc:'Changer de modèle',                 badge:'nav',    action:()=>document.getElementById('model-select').focus()},
  { cmd:'/export',    desc:'Exporter la conversation en .md',   badge:'local',  action:()=>exportConv()},
  { cmd:'/cost',      desc:'Afficher le coût de la session',    badge:'info',   action:()=>showCostInfo()},
];

let slashSelectedIdx = -1;
let slashVisible     = false;

function buildSlashMenu(filter='') {
  const menu   = document.getElementById('slash-menu');
  const items  = SLASH_CMDS.filter(c => c.cmd.startsWith(filter) || !filter);
  if (!items.length || filter.length > 1 && !items.find(c => c.cmd.startsWith(filter))) {
    closeSlash(); return;
  }
  menu.innerHTML = items.map((c, i) => `
    <div class="slash-item" data-idx="${i}" onclick="runSlash(${i},'${filter}')">
      <span class="slash-cmd">${escH(c.cmd)}</span>
      <span class="slash-desc">${escH(c.desc)}</span>
      <span class="slash-badge">${escH(c.badge)}</span>
    </div>`).join('');
  menu.classList.add('open');
  slashVisible = true;
  slashSelectedIdx = -1;
}

function closeSlash() {
  document.getElementById('slash-menu').classList.remove('open');
  slashVisible = false;
  slashSelectedIdx = -1;
}

function runSlash(idx, filter) {
  const items = SLASH_CMDS.filter(c => c.cmd.startsWith(filter) || !filter);
  const item  = items[idx];
  if (!item) return;
  closeSlash();
  const inp = document.getElementById('input');
  inp.value = '';
  inp.style.height = 'auto';
  item.action();
}

function handleSlashKey(e) {
  if (!slashVisible) return false;
  const menu  = document.getElementById('slash-menu');
  const items = menu.querySelectorAll('.slash-item');
  if (e.key === 'Escape') { closeSlash(); e.preventDefault(); return true; }
  if (e.key === 'ArrowDown') {
    slashSelectedIdx = Math.min(slashSelectedIdx + 1, items.length - 1);
    items.forEach((el, i) => el.classList.toggle('selected', i === slashSelectedIdx));
    e.preventDefault(); return true;
  }
  if (e.key === 'ArrowUp') {
    slashSelectedIdx = Math.max(slashSelectedIdx - 1, 0);
    items.forEach((el, i) => el.classList.toggle('selected', i === slashSelectedIdx));
    e.preventDefault(); return true;
  }
  if (e.key === 'Enter' || e.key === 'Tab') {
    if (slashSelectedIdx >= 0) {
      const inp = document.getElementById('input');
      runSlash(slashSelectedIdx, inp.value);
      e.preventDefault(); return true;
    }
    if (e.key === 'Tab') {
      // Auto-complete avec le premier item
      runSlash(0, document.getElementById('input').value);
      e.preventDefault(); return true;
    }
  }
  return false;
}

// Export conversation
async function exportConv() {
  const r = await fetch(`/api/conversations/${activeConvId}`);
  const d = await r.json();
  let md = `# ${d.name}\n\n`;
  for (const m of d.history || []) {
    if (m.role === 'user')
      md += `## 👤 Vous\n\n${m.content}\n\n`;
    else if (m.role === 'assistant' && m.content && m.content !== '[streamed]')
      md += `## 🤖 Agent\n\n${m.content}\n\n`;
  }
  const blob = new Blob([md], {type:'text/markdown'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${d.name.replace(/[^a-z0-9]/gi,'_')}.md`;
  a.click();
}

function showCostInfo() {
  const c = totalCost;
  const msg = c === 0
    ? 'Coût session : $0.00 (modèles gratuits 🎉)'
    : `Coût session : $${c.toFixed(8)} USD\n(${(c*1000).toFixed(5)} millicents)`;
  alert(msg);
}

// ══════════════════════════════════════════════════════════════════════════════
// MESSAGES DOM (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
function hideWelcome() {
  const w = document.getElementById('welcome');
  if (w) w.remove();
}

function clearMessages() {
  const m = document.getElementById('messages');
  m.innerHTML = `<div class="welcome" id="welcome">
    <div class="welcome-hex">⬡</div>
    <div class="welcome-title">Nouvelle conversation</div>
    <div class="welcome-sub">Pose une question ou donne une tâche.<br>
      Tape <code style="font-size:12px;background:var(--bg3);border:1px solid var(--border2);padding:2px 8px;border-radius:5px">/</code> pour les commandes</div>
  </div>`;
  toolContainer = null; agentBodyEl = null; streamBuf = '';
}

function now() {
  return new Date().toLocaleTimeString('fr',{hour:'2-digit',minute:'2-digit'});
}

function appendUserMsg(text, animate=true) {
  hideWelcome();
  const div = document.createElement('div');
  div.className = 'msg user';
  if (!animate) div.style.animation = 'none';
  div.innerHTML = `
    <div class="msg-row">
      <div class="avatar user">U</div>
      <div class="msg-meta">Vous <span class="msg-time">${now()}</span></div>
    </div>
    <div class="msg-body">${escH(text)}</div>`;
  msgs().appendChild(div);
  scrollBot();
}

// Message agent terminé (historique ou fin de stream)
function appendFinishedMsg(text, model) {
  hideWelcome();
  toolContainer = null;
  const div = document.createElement('div');
  div.className = 'msg agent';
  div.innerHTML = `
    <div class="msg-row">
      <div class="avatar agent">A</div>
      <div class="msg-meta">Agent
        <span class="model-tag">${escH(model||currentModel)}</span>
        <span class="msg-time">${now()}</span>
      </div>
    </div>
    <div class="msg-body">${renderMD(text)}</div>`;
  msgs().appendChild(div);
  // Applique highlight.js sur les blocs code
  div.querySelectorAll('pre code[class]').forEach(el => hljs.highlightElement(el));
  scrollBot();
}

// Démarre un message agent en streaming
function startStreamMsg(model) {
  removeThinking();
  toolContainer = null;
  const div = document.createElement('div');
  div.className = 'msg agent';
  div.innerHTML = `
    <div class="msg-row">
      <div class="avatar agent">A</div>
      <div class="msg-meta">Agent
        <span class="model-tag" id="stream-model-tag">${escH(model||currentModel)}</span>
        <span class="msg-time">${now()}</span>
      </div>
    </div>
    <div class="msg-body stream-cursor" id="stream-body"></div>`;
  msgs().appendChild(div);
  agentBodyEl = div.querySelector('#stream-body');
  streamBuf   = '';
  scrollBot();
}

// Met à jour le contenu pendant le streaming
// Rendu brut pendant le stream (perf), rendu Markdown à la fin
function appendToken(tok) {
  if (!agentBodyEl) startStreamMsg(currentModel);
  streamBuf += tok;
  // Rendu partiel léger : juste le texte brut avec retours à la ligne
  agentBodyEl.textContent = streamBuf;
  scrollBot();
}

// Finalise le rendu après stream terminé
function finalizeStreamMsg(model) {
  if (!agentBodyEl) return;
  agentBodyEl.classList.remove('stream-cursor');
  agentBodyEl.innerHTML = renderMD(streamBuf);
  // Applique highlight.js
  agentBodyEl.querySelectorAll('pre code[class]').forEach(el => hljs.highlightElement(el));
  // Met à jour le model tag
  const mt = document.getElementById('stream-model-tag');
  if (mt && model) mt.textContent = model;
  scrollBot();
  agentBodyEl = null;
  streamBuf   = '';
}

function appendThinking(step, max) {
  let el = document.getElementById('thinking-el');
  if (!el) {
    el = document.createElement('div');
    el.id = 'thinking-el'; el.className = 'thinking';
    el.innerHTML = `<div class="dots"><span></span><span></span><span></span></div><span id="thinking-txt"></span>`;
    msgs().appendChild(el);
  }
  document.getElementById('thinking-txt').textContent = `Étape ${step}/${max}…`;
  scrollBot();
}
function removeThinking() {
  const el = document.getElementById('thinking-el'); if (el) el.remove();
}

function appendToolCall(name, args) {
  if (!toolContainer) {
    toolContainer = document.createElement('div');
    toolContainer.className = 'tool-events';
    msgs().appendChild(toolContainer);
  }
  const el = document.createElement('div');
  el.className = 'tool-event';
  el.innerHTML = `
    <div class="tool-top">
      <span class="tool-ico">⚙</span>
      <span class="tool-name">${escH(name)}</span>
      <span class="tool-args">${escH(trunc(JSON.stringify(args,null,0), 90))}</span>
    </div>`;
  toolContainer.appendChild(el); scrollBot();
}
function appendToolResult(name, result, cached=false) {
  if (!toolContainer) return;
  const last = toolContainer.lastElementChild;
  if (!last) return;
  const pre = document.createElement('div');
  pre.className = 'tool-result';
  pre.textContent = trunc(result, 350);
  if (cached) {
    const badge = document.createElement('span');
    badge.className = 'cache-badge'; badge.textContent = '⚡ cache';
    last.querySelector('.tool-top').appendChild(badge);
  }
  last.appendChild(pre); scrollBot();
}

function msgs()    { return document.getElementById('messages'); }
function scrollBot(){ const m=msgs(); m.scrollTop=m.scrollHeight; }

// ══════════════════════════════════════════════════════════════════════════════
// SEND / STREAM (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
async function sendMsg() {
  if (streaming) return;
  const inp  = document.getElementById('input');
  let   text = inp.value.trim();
  if (!text && !uploadedFile) return;
  if (text.startsWith('/')) return;

  inp.value = ''; inp.style.height = 'auto';
  closeSlash();

  // Injecte le fichier uploadé dans le message
  let fullMsg = text;
  if (uploadedFile) {
    const header = `[Fichier joint : ${uploadedFile.name} — ${uploadedFile.lines} lignes]\n\`\`\`\n`;
    const footer = `\n\`\`\`\n`;
    fullMsg = (text ? text + '\n\n' : '') + header + uploadedFile.content + footer;
    clearUpload();
  }

  appendUserMsg(fullMsg.length > 300
    ? text + (uploadedFile ? ` 📎 ${uploadedFile?.name || ''}` : '')
    : fullMsg);

  const n = parseInt(document.getElementById('s-msgs').textContent||0)+1;
  document.getElementById('s-msgs').textContent = n;
  const conv = conversations.find(c => c.id === activeConvId);
  if (conv) { conv.msg_count = n; renderConvList(); }

  setStreaming(true);
  agentBodyEl = null; toolContainer = null; streamBuf = '';
  abortCtrl   = new AbortController();
  let streamModel = currentModel;

  try {
    const resp = await fetch('/api/chat', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message: fullMsg}), signal:abortCtrl.signal,
    });
    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let   buf     = '';

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream:true});
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const ev = JSON.parse(line.slice(6));
          streamModel = handleEvt(ev, streamModel);
        } catch {}
      }
    }
  } catch(e) {
    if (e.name !== 'AbortError') {
      removeThinking();
      startStreamMsg(currentModel);
      appendToken('Erreur de connexion.');
      finalizeStreamMsg(currentModel);
    }
  } finally {
    setStreaming(false);
    // Finalise si on a du texte non rendu (ex: abort)
    if (streamBuf && agentBodyEl) finalizeStreamMsg(streamModel);
  }
}

function handleEvt(ev, model) {
  switch(ev.type) {
    case 'thinking':
      appendThinking(ev.step, ev.max); break;

    case 'token':
      removeThinking();
      if (!agentBodyEl) startStreamMsg(model);
      appendToken(ev.text); break;

    case 'tool_call':
      removeThinking();
      // Si on avait du texte en cours, on finalise avant les outils
      if (streamBuf && agentBodyEl) { finalizeStreamMsg(model); }
      appendToolCall(ev.name, ev.args||{}); break;

    case 'tool_result':
      appendToolResult(ev.name, ev.result||'', ev.cached||false); break;

    case 'done':
      // Finalise le rendu Markdown complet
      finalizeStreamMsg(ev.model || model);
      if (ev.metrics) updateStats(ev.metrics);
      model = ev.model || model;
      break;

    case 'error':
      removeThinking();
      if (streamBuf && agentBodyEl) finalizeStreamMsg(model);
      else startStreamMsg(model);
      if (!agentBodyEl) startStreamMsg(model);
      appendToken('⚠ ' + (ev.text||'Erreur inconnue'));
      finalizeStreamMsg(model); break;
  }
  return model;
}

function stopStream() { if (abortCtrl) abortCtrl.abort(); }

function setStreaming(val) {
  streaming = val;
  document.getElementById('send-btn').disabled = val;
  document.getElementById('stop-btn').style.display = val ? 'flex' : 'none';
  setStatus(val ? 'En cours…' : 'Connecté', val ? 'busy' : 'ok');
}

async function clearChat() {
  if (!confirm('Effacer cette conversation ?')) return;
  await fetch('/api/clear', {method:'POST'});
  clearMessages();
  document.getElementById('s-msgs').textContent = '0';
  const conv = conversations.find(c => c.id === activeConvId);
  if (conv) { conv.msg_count = 0; renderConvList(); }
}

// ══════════════════════════════════════════════════════════════════════════════
// UPLOAD FICHIER (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
async function handleFileSelect(input) {
  const file = input.files[0];
  if (!file) return;
  input.value = ''; // reset pour re-sélection possible

  const form = new FormData();
  form.append('file', file);

  try {
    const r = await fetch('/api/upload', { method:'POST', body: form });
    const d = await r.json();
    if (!r.ok || d.error) {
      showUploadError(d.error || 'Erreur upload'); return;
    }
    uploadedFile = { name: d.filename, content: d.content,
                     lines: d.lines, size: d.size };
    showUploadPill(d.filename, d.lines, d.size);
    document.getElementById('input').focus();
  } catch(e) {
    showUploadError('Erreur réseau: ' + e.message);
  }
}

function showUploadPill(name, lines, size) {
  const preview = document.getElementById('upload-preview');
  const kb = (size / 1024).toFixed(1);
  preview.innerHTML = `
    <div class="upload-pill">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      <span class="upload-pill-name">${escH(name)}</span>
      <span class="upload-pill-info">${lines} lignes · ${kb} KB</span>
      <button class="upload-pill-del" onclick="clearUpload()" title="Retirer le fichier">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>`;
  preview.style.display = 'block';
}

function clearUpload() {
  uploadedFile = null;
  const preview = document.getElementById('upload-preview');
  preview.innerHTML = ''; preview.style.display = 'none';
}

function showUploadError(msg) {
  const preview = document.getElementById('upload-preview');
  preview.innerHTML = `<div style="padding:8px 16px;font-size:12px;color:var(--red);
    background:rgba(240,124,124,.07);border:1px solid rgba(240,124,124,.2);
    border-radius:var(--r);animation:fadeUp .2s ease">⚠ ${escH(msg)}</div>`;
  preview.style.display = 'block';
  setTimeout(() => { preview.innerHTML=''; preview.style.display='none'; }, 4000);
}

// ══════════════════════════════════════════════════════════════════════════════
// INPUT HANDLING (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
function handleKey(e) {
  // Slash menu navigation
  if (handleSlashKey(e)) return;
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
}

function handleInput(el) {
  // Auto-resize
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 200) + 'px';

  // Slash commands
  const val = el.value;
  if (val.startsWith('/') && !val.includes(' ')) {
    buildSlashMenu(val);
  } else {
    closeSlash();
  }
}

function quick(text) {
  const inp = document.getElementById('input');
  inp.value = text;
  inp.style.height = 'auto';
  inp.style.height = Math.min(inp.scrollHeight, 200) + 'px';
  sendMsg();
}

// ══════════════════════════════════════════════════════════════════════════════
// SIDEBAR MOBILE (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('overlay').classList.toggle('open');
}

// ══════════════════════════════════════════════════════════════════════════════
// COPY CODE (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
function copyCode(id, btn) {
  const el = document.getElementById(id+'-txt');
  if (!el) return;
  const text = el.textContent || el.innerText;
  navigator.clipboard.writeText(text).then(() => {
    btn.classList.add('copied');
    btn.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Copié !`;
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copier`;
    }, 2000);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); ta.remove();
    btn.classList.add('copied'); btn.textContent = '✓';
    setTimeout(() => { btn.classList.remove('copied'); btn.textContent = 'Copier'; }, 2000);
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// MARKDOWN RENDERER  (avec syntax highlight via hljs) (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
function renderMD(text) {
  if (!text) return '';
  const parts = [];
  let last = 0;
  const codeRe = /```(\w*)\n?([\s\S]*?)```/g;
  let m;
  while ((m = codeRe.exec(text)) !== null) {
    if (m.index > last) parts.push({type:'text', val:text.slice(last, m.index)});
    parts.push({type:'code', lang:m[1]||'', val:m[2]});
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({type:'text', val:text.slice(last)});

  return parts.map(p => {
    if (p.type === 'code') {
      const id   = 'cb-' + Math.random().toString(36).slice(2,8);
      const lang = p.lang || 'plaintext';
      // highlight.js sera appelé après insertion dans le DOM
      return `<div class="code-block">
        <div class="code-header">
          <span class="code-lang">${escH(lang)}</span>
          <button class="copy-btn" onclick="copyCode('${id}',this)">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            Copier
          </button>
        </div>
        <pre><code id="${id}-txt" class="language-${escH(lang)}">${escH(p.val.trimEnd())}</code></pre>
      </div>`;
    }
    // Texte inline
    let t = escH(p.val);
    t = t.replace(/`([^`\n]+)`/g,'<code>$1</code>');
    t = t.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
    t = t.replace(/\*(.+?)\*/g,'<em>$1</em>');
    t = t.replace(/^### (.+)$/gm,'<h3>$1</h3>');
    t = t.replace(/^## (.+)$/gm,'<h2>$1</h2>');
    t = t.replace(/^# (.+)$/gm,'<h1>$1</h1>');
    t = t.replace(/^---$/gm,'<hr>');
    t = t.replace(/^&gt; (.+)$/gm,'<blockquote>$1</blockquote>');
    t = t.replace(/^[\-\*] (.+)$/gm,'<li>$1</li>');
    t = t.replace(/(<li>[\s\S]*?<\/li>\n?)+/g, s=>`<ul>${s}</ul>`);
    t = t.replace(/^\d+\. (.+)$/gm,'<li>$1</li>');
    t = t.split(/\n{2,}/).map(para => {
      if (/^<(h[1-3]|ul|ol|li|hr|blockquote)/.test(para.trim())) return para;
      const inner = para.replace(/\n/g,'<br>');
      return inner ? `<p>${inner}</p>` : '';
    }).join('');
    return t;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════════════════
// UTILS (inchangé)
// ══════════════════════════════════════════════════════════════════════════════
function escH(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function trunc(s,n){s=String(s||'');return s.length>n?s.slice(0,n)+'…':s}

// ══════════════════════════════════════════════════════════════════════════════
// NOUVELLES FONCTIONS : Workspace & Recherche sémantique
// ══════════════════════════════════════════════════════════════════════════════
async function switchWorkspace(name) {
  await fetch('/api/workspace/switch', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name})
  });
  // Recharger les conversations
  const r = await fetch('/api/conversations');
  const cd = await r.json();
  conversations = cd.conversations || [];
  activeConvId = cd.active;
  renderConvList();
  if (activeConvId) await loadConvHistory(activeConvId);
  else clearMessages();
}

async function indexWorkspace() {
  const r = await fetch('/api/index', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({})
  });
  const d = await r.json();
}
function openSemanticSearch() {
  document.getElementById('semantic-modal').classList.add('open');
}
function closeSemantic() {
  document.getElementById('semantic-modal').classList.remove('open');
}
async function performSemanticSearch() {
  const q = document.getElementById('semantic-query').value.trim();
  if (!q) return;
  const r = await fetch('/api/search/semantic', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({query:q})
  });
  const results = await r.json();
  const container = document.getElementById('semantic-results');
  if (!results.length) {
    container.innerHTML = '<div class="mem-empty">Aucun résultat.</div>';
    return;
  }
  container.innerHTML = results.map(res => `
    <div style="margin-bottom:12px; padding:10px; background:var(--bg3); border-radius:8px;">
      <div><strong>${escH(res.path)}</strong> (score: ${res.score?.toFixed(2)})</div>
      <pre style="font-size:12px; color:var(--text2); margin-top:6px; white-space:pre-wrap;">${escH(res.content)}</pre>
    </div>
  `).join('');
}

// ══════════════════════════════════════════════════════════════════════════════
// KEYBOARD SHORTCUTS (inchangé, mais on ajoute la fermeture du modal sémantique)
// ══════════════════════════════════════════════════════════════════════════════
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeMemory();
    closeSemantic(); // fermer aussi le modal sémantique
    closeSlash();
  }
  if ((e.ctrlKey||e.metaKey) && e.key==='k') { e.preventDefault(); document.getElementById('input').focus(); }
  if ((e.ctrlKey||e.metaKey) && e.key==='n') { e.preventDefault(); newChat(); }
});
document.getElementById('mem-modal').addEventListener('click', function(e){
  if (e.target===this) closeMemory();
});
document.getElementById('semantic-modal').addEventListener('click', function(e){
  if (e.target===this) closeSemantic();
});

// ══════════════════════════════════════════════════════════════════════════════
// BOOT
// ══════════════════════════════════════════════════════════════════════════════
init();