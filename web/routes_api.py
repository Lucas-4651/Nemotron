# web/routes_api.py — v4.0
# BUG-FIX #1  : Route '/workspace/<n>' → paramètre 'n' mais fonction attendait 'name' → 500 systématique
# BUG-FIX #9  : import_conv_json — validation que 'history' est une liste avant insertion
# CLEAN       : imports re/io/zipfile déplacés au niveau module
# CLEAN       : _stop_events nettoyé dans finally (déjà ok, confirmé)
import re
import io
import zipfile
import threading
from flask import Blueprint, request, jsonify, Response, session, current_app
from werkzeug.utils import secure_filename
import os
import json
import uuid
import logging
from collections import OrderedDict
from datetime import datetime

from config import Config
from web.auth import login_required_api
from web.models import db, Conversation, Memory, ProjectContext
from web.limiter import limiter
from workspace.manager import WorkspaceManager
from workspace.indexer import CodeIndexer
from core.agent import DevAgent

logger     = logging.getLogger(__name__)
api_bp     = Blueprint('api', __name__)

workspace_manager: WorkspaceManager = None
indexers: dict     = {}
MAX_AGENTS         = 10
agents: OrderedDict = OrderedDict()

_runtime_api_key   : str  = ''
_runtime_model     : str  = ''
_runtime_reasoning : bool = False

# Drapeaux pour /stop — {workspace: Event}
_stop_events: dict = {}


# ── helpers ───────────────────────────────────────────────────────────────────

def _agent_memory_save(key: str, value: str):
    mem = Memory.query.filter_by(key=key).first()
    if mem:
        mem.value = value
    else:
        mem = Memory(key=key, value=value)
        db.session.add(mem)
    db.session.commit()
    _refresh_memory_context()


def _get_or_create_agent(workspace: str) -> DevAgent:
    if workspace in agents:
        agents.move_to_end(workspace)
        return agents[workspace]
    if len(agents) >= MAX_AGENTS:
        evicted, _ = agents.popitem(last=False)
        logger.info(f'[AGENTS] Éviction LRU: {evicted}')
    path          = workspace_manager.switch_workspace(workspace)
    effective_key = _runtime_api_key or Config.OPENROUTER_API_KEY
    cfg = {
        'api_key'           : effective_key,
        'model'             : _runtime_model or Config.DEFAULT_MODEL,
        'max_steps'         : Config.MAX_STEPS,
        'tool_timeout'      : Config.TOOL_TIMEOUT,
        'max_tools_per_step': Config.MAX_TOOLS_PER_STEP,
    }
    agent = DevAgent(str(path), config=cfg, memory_save_cb=_agent_memory_save)
    agent.reasoning_enabled = _runtime_reasoning
    if workspace in indexers:
        agent.tool_mgr.search_tools.set_indexer(indexers[workspace])
    agents[workspace] = agent
    mems = Memory.query.all()
    if mems:
        agent.memory_context = '\n'.join(f'- {m.key}: {m.value}' for m in mems)
    return agent


def init_api(ws_manager):
    global workspace_manager
    workspace_manager = ws_manager


# ── /chat ─────────────────────────────────────────────────────────────────────

@api_bp.route('/chat', methods=['POST'])
@login_required_api
@limiter.limit('30 per minute')
def chat():
    data      = request.get_json() or {}
    msg       = data.get('message', '').strip()
    workspace = data.get('workspace', session.get('current_workspace', 'default'))
    if not msg:
        return jsonify({'error': 'Message vide'}), 400

    agent = _get_or_create_agent(workspace)

    conv_id = session.get('active_conv')
    if conv_id:
        conv = db.session.get(Conversation, conv_id)
        if conv:
            agent.history = conv.get_history()
    else:
        conv = Conversation(
            id=str(uuid.uuid4())[:8],
            name=f"Chat {datetime.now().strftime('%H:%M')}",
            workspace=workspace,
        )
        db.session.add(conv)
        db.session.commit()
        session['active_conv'] = conv.id
        agent.history = []

    captured_conv_id = session.get('active_conv')
    flask_app        = current_app._get_current_object()

    stop_event = threading.Event()
    _stop_events[workspace] = stop_event

    def generate():
        final_history = None
        try:
            for event in agent.stream_task(msg):
                if stop_event.is_set():
                    yield f"data: {json.dumps({'type': 'stopped'})}\n\n"
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get('type') in ('done', 'error'):
                    final_history = agent.history.copy()
        finally:
            _stop_events.pop(workspace, None)
            if final_history is not None:
                with flask_app.app_context():
                    if captured_conv_id:
                        conv_obj = db.session.get(Conversation, captured_conv_id)
                        if conv_obj:
                            conv_obj.set_history(final_history)
                            db.session.commit()
                        _maybe_autoname_async(flask_app, captured_conv_id, agent)

    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control'    : 'no-cache',
        'X-Accel-Buffering': 'no',
    })


# ── /stop ─────────────────────────────────────────────────────────────────────

@api_bp.route('/stop', methods=['POST'])
@login_required_api
def stop():
    workspace = session.get('current_workspace', 'default')
    ev        = _stop_events.get(workspace)
    if ev:
        ev.set()
        return jsonify({'ok': True, 'stopped': True})
    return jsonify({'ok': True, 'stopped': False})


# ── Auto-nommage ──────────────────────────────────────────────────────────────

def _maybe_autoname_async(app, conv_id: str, agent: DevAgent):
    def _do():
        try:
            with app.app_context():
                conv = db.session.get(Conversation, conv_id)
                # BUG-FIX mineur : null-check sur conv.name avant startswith
                if not conv or not conv.name or not conv.name.startswith('Chat '):
                    return
                hist = conv.get_history()
                user_msgs = [
                    m['content'] for m in hist
                    if m.get('role') == 'user' and isinstance(m.get('content'), str)
                ]
                if not user_msgs:
                    return
                prompt = (
                    "Génère un titre de 3-5 mots maximum (sans guillemets, sans ponctuation finale) "
                    f"pour cette conversation: \"{user_msgs[0][:200]}\""
                )
                name = agent.llm.simple_call(
                    [{'role': 'user', 'content': prompt}],
                    profile='naming'
                )
                if name and len(name.strip()) < 80:
                    conv.name = name.strip()[:60]
                    db.session.commit()
        except Exception as e:
            logger.warning(f'autoname error: {e}')
    threading.Thread(target=_do, daemon=True).start()


@api_bp.route('/conversations/<cid>/autoname', methods=['POST'])
@login_required_api
def autoname_conv(cid):
    conv  = db.session.get(Conversation, cid)
    if not conv:
        return jsonify({'error': 'Introuvable'}), 404
    agent = agents.get(session.get('current_workspace', 'default'))
    if not agent:
        return jsonify({'error': 'Agent non démarré'}), 400
    flask_app = current_app._get_current_object()
    _maybe_autoname_async(flask_app, cid, agent)
    return jsonify({'ok': True})


# ── Workspaces ────────────────────────────────────────────────────────────────

@api_bp.route('/workspaces', methods=['GET'])
@login_required_api
def list_workspaces():
    return jsonify(workspace_manager.list_workspaces())


@api_bp.route('/workspace/switch', methods=['POST'])
@login_required_api
def switch_workspace():
    data = request.get_json() or {}
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Nom requis'}), 400
    path = workspace_manager.switch_workspace(name)
    session['current_workspace'] = name
    if name not in indexers:
        indexers[name] = CodeIndexer(path)
    if name in agents:
        agents[name].tool_mgr.search_tools.set_indexer(indexers[name])
    return jsonify({'workspace': name, 'path': str(path)})


@api_bp.route('/workspace/create', methods=['POST'])
@login_required_api
def create_workspace():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Nom requis'}), 400
    if not re.match(r'^[a-zA-Z0-9_\-]+$', name):
        return jsonify({'error': 'Nom invalide (lettres, chiffres, - _ uniquement)'}), 400
    try:
        path = workspace_manager.create_workspace(name)
        session['current_workspace'] = name
        indexers[name] = CodeIndexer(path)
        return jsonify({'workspace': name, 'path': str(path),
                        'workspaces': workspace_manager.list_workspaces()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# BUG-FIX #1 : route utilisait '<n>' mais la fonction attendait 'name'
# → Flask passait le paramètre sous la clé 'n' → TypeError 500 systématique
# CORRECTION : alignement du nom de paramètre URL et de l'argument de fonction
@api_bp.route('/workspace/<name>', methods=['DELETE'])
@login_required_api
def delete_workspace(name: str):
    if name == 'default':
        return jsonify({'error': 'Impossible de supprimer le workspace default'}), 400
    try:
        workspace_manager.delete_workspace(name)
        agents.pop(name, None)
        indexers.pop(name, None)
        if session.get('current_workspace') == name:
            session['current_workspace'] = 'default'
            workspace_manager.switch_workspace('default')
        return jsonify({'ok': True, 'workspaces': workspace_manager.list_workspaces()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/index', methods=['POST'])
@login_required_api
def index_workspace():
    data      = request.get_json() or {}
    workspace = data.get('workspace', session.get('current_workspace', 'default'))
    session['current_workspace'] = workspace
    if workspace not in indexers:
        try:
            path = workspace_manager.switch_workspace(workspace)
            indexers[workspace] = CodeIndexer(path)
        except Exception as e:
            return jsonify({'error': f'Init workspace impossible: {e}'}), 500
    try:
        count = indexers[workspace].index_directory()
        if workspace in agents:
            agents[workspace].tool_mgr.search_tools.set_indexer(indexers[workspace])
        return jsonify({'status': 'ok', 'workspace': workspace, 'indexed': count,
                        'message': f'{count} fichier(s) indexé(s)'})
    except Exception as e:
        return jsonify({'error': f'Indexation échouée: {e}'}), 500


@api_bp.route('/search/semantic', methods=['POST'])
@login_required_api
def semantic_search():
    data      = request.get_json() or {}
    query     = data.get('query')
    workspace = data.get('workspace', session.get('current_workspace', 'default'))
    if not query:
        return jsonify({'error': 'Query requise'}), 400
    if workspace not in indexers:
        return jsonify({'error': "Workspace non indexé. Clique sur \"Index\" d'abord."}), 400
    results = indexers[workspace].search(query, n_results=10)
    return jsonify(results)


# ── Conversations ─────────────────────────────────────────────────────────────

@api_bp.route('/conversations', methods=['GET'])
@login_required_api
def list_convs():
    workspace = session.get('current_workspace', 'default')
    convs = (Conversation.query.filter_by(workspace=workspace)
             .order_by(Conversation.created_at.desc()).all())
    return jsonify({
        'conversations': [{'id': c.id, 'name': c.name,
                           'created_at': c.created_at.isoformat(),
                           'msg_count': c.msg_count()} for c in convs],
        'active': session.get('active_conv'),
    })


@api_bp.route('/conversations', methods=['POST'])
@login_required_api
def create_conv():
    data      = request.get_json() or {}
    workspace = session.get('current_workspace', 'default')
    conv      = Conversation(
        id=str(uuid.uuid4())[:8],
        name=data.get('name', '').strip() or f"Chat {datetime.now().strftime('%H:%M')}",
        workspace=workspace,
    )
    db.session.add(conv)
    db.session.commit()
    session['active_conv'] = conv.id
    if workspace in agents:
        agents[workspace].history = []
    return jsonify({'id': conv.id, 'name': conv.name,
                    'created_at': conv.created_at.isoformat(), 'msg_count': 0})


@api_bp.route('/conversations/<cid>', methods=['GET'])
@login_required_api
def load_conv(cid):
    conv = db.session.get(Conversation, cid)
    if not conv:
        return jsonify({'error': 'Introuvable'}), 404
    session['active_conv'] = conv.id
    if conv.workspace in agents:
        agents[conv.workspace].history = conv.get_history()
    return jsonify({'id': conv.id, 'name': conv.name, 'history': conv.get_history()})


@api_bp.route('/conversations/<cid>', methods=['DELETE'])
@login_required_api
def delete_conv(cid):
    conv = db.session.get(Conversation, cid)
    if not conv:
        return jsonify({'error': 'Introuvable'}), 404
    db.session.delete(conv)
    db.session.commit()
    if session.get('active_conv') == cid:
        session.pop('active_conv', None)
        other = Conversation.query.filter_by(workspace=conv.workspace).first()
        if other:
            session['active_conv'] = other.id
    return jsonify({'ok': True})


@api_bp.route('/conversations/<cid>/rename', methods=['POST'])
@login_required_api
def rename_conv(cid):
    conv = db.session.get(Conversation, cid)
    if not conv:
        return jsonify({'error': 'Introuvable'}), 404
    name = (request.get_json() or {}).get('name', '').strip()
    if name:
        conv.name = name
        db.session.commit()
    return jsonify({'ok': True, 'name': conv.name})


# ── Export / Import JSON ──────────────────────────────────────────────────────

@api_bp.route('/conversations/<cid>/export-json', methods=['GET'])
@login_required_api
def export_conv_json(cid):
    conv = db.session.get(Conversation, cid)
    if not conv:
        return jsonify({'error': 'Introuvable'}), 404
    payload = {
        'version'    : 4,
        'id'         : conv.id,
        'name'       : conv.name,
        'workspace'  : conv.workspace,
        'created_at' : conv.created_at.isoformat(),
        'history'    : conv.get_history(),
        'exported_at': datetime.utcnow().isoformat(),
    }
    resp = Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        mimetype='application/json',
    )
    resp.headers['Content-Disposition'] = (
        f'attachment; filename="nemotron_{conv.name[:30].replace(" ", "_")}.json"'
    )
    return resp


@api_bp.route('/conversations/import-json', methods=['POST'])
@login_required_api
@limiter.limit('10 per minute')
def import_conv_json():
    if 'file' not in request.files:
        return jsonify({'error': 'Fichier requis'}), 400
    f       = request.files['file']
    content = f.read(2_000_000)   # max 2MB
    try:
        payload = json.loads(content.decode('utf-8'))
    except Exception:
        return jsonify({'error': 'JSON invalide'}), 400

    # BUG-FIX #9 : valider que 'history' est bien une liste avant tout accès
    history = payload.get('history', [])
    if not isinstance(history, list):
        return jsonify({'error': "Le champ 'history' doit être une liste"}), 400

    # Filtrer les messages malformés pour éviter les crashs SQLite
    history = [
        m for m in history
        if isinstance(m, dict) and m.get('role') in ('user', 'assistant', 'tool', 'system')
    ]

    workspace = session.get('current_workspace', 'default')
    name      = payload.get('name', f"Import {datetime.now().strftime('%H:%M')}")
    if not isinstance(name, str):
        name = f"Import {datetime.now().strftime('%H:%M')}"

    conv = Conversation(id=str(uuid.uuid4())[:8], name=name[:200], workspace=workspace)
    conv.set_history(history)
    db.session.add(conv)
    db.session.commit()
    session['active_conv'] = conv.id
    if workspace in agents:
        agents[workspace].history = history
    return jsonify({'ok': True, 'id': conv.id, 'name': conv.name,
                    'msg_count': conv.msg_count()})


# ── Mémoire ───────────────────────────────────────────────────────────────────

def _refresh_memory_context():
    mems = Memory.query.all()
    ctx  = '\n'.join(f'- {m.key}: {m.value}' for m in mems)
    for a in agents.values():
        a.memory_context = ctx


@api_bp.route('/memory', methods=['GET'])
@login_required_api
def get_mem():
    return jsonify({'memory': {m.key: m.value for m in Memory.query.all()}})


@api_bp.route('/memory', methods=['POST'])
@login_required_api
def add_mem():
    data     = request.get_json() or {}
    key, val = data.get('key', '').strip(), data.get('value', '').strip()
    if not key or not val:
        return jsonify({'error': 'key + value requis'}), 400
    mem = Memory.query.filter_by(key=key).first()
    if mem:
        mem.value = val
    else:
        mem = Memory(key=key, value=val)
        db.session.add(mem)
    db.session.commit()
    _refresh_memory_context()
    return jsonify({'ok': True})


@api_bp.route('/memory/<key>', methods=['DELETE'])
@login_required_api
def del_mem(key):
    Memory.query.filter_by(key=key).delete()
    db.session.commit()
    _refresh_memory_context()
    return jsonify({'ok': True})


# ── Config agent ──────────────────────────────────────────────────────────────

@api_bp.route('/config', methods=['GET'])
@login_required_api
def get_config():
    workspace = session.get('current_workspace', 'default')
    agent     = agents.get(workspace)
    return jsonify({
        'max_steps'         : agent.max_steps          if agent else Config.MAX_STEPS,
        'tool_timeout'      : agent.tool_timeout       if agent else Config.TOOL_TIMEOUT,
        'max_tools_per_step': agent.max_tools_per_step if agent else Config.MAX_TOOLS_PER_STEP,
        'max_history_tokens': agent.max_htoks          if agent else Config.MAX_HISTORY_TOKENS,
        'bounds'            : Config.AGENT_CONFIG_BOUNDS,
    })


@api_bp.route('/config', methods=['POST'])
@login_required_api
def update_config():
    data      = request.get_json() or {}
    workspace = session.get('current_workspace', 'default')
    bounds    = Config.AGENT_CONFIG_BOUNDS
    applied   = {}

    def _clamp(key, val):
        lo, hi = bounds.get(key, (1, 9999))
        return max(lo, min(hi, int(val)))

    agent = _get_or_create_agent(workspace)
    if 'max_steps' in data:
        agent.max_steps              = _clamp('max_steps', data['max_steps'])
        applied['max_steps']         = agent.max_steps
    if 'tool_timeout' in data:
        agent.tool_timeout           = _clamp('tool_timeout', data['tool_timeout'])
        applied['tool_timeout']      = agent.tool_timeout
    if 'max_tools_per_step' in data:
        agent.max_tools_per_step     = _clamp('max_tools_per_step', data['max_tools_per_step'])
        applied['max_tools_per_step'] = agent.max_tools_per_step
    if 'max_history_tokens' in data:
        agent.max_htoks              = _clamp('max_history_tokens', data['max_history_tokens'])
        applied['max_history_tokens'] = agent.max_htoks

    return jsonify({'ok': True, 'applied': applied})


# ── Contrôles agent ───────────────────────────────────────────────────────────

@api_bp.route('/clear', methods=['POST'])
@login_required_api
def clear():
    workspace = session.get('current_workspace', 'default')
    if workspace in agents:
        agents[workspace].history               = []
        agents[workspace].history_tokens        = 0
        agents[workspace]._summary_cache        = ''
        agents[workspace]._project_context_loaded = False
    conv_id = session.get('active_conv')
    if conv_id:
        conv = db.session.get(Conversation, conv_id)
        if conv:
            conv.set_history([])
            db.session.commit()
    return jsonify({'ok': True})


@api_bp.route('/setkey', methods=['POST'])
@login_required_api
def set_key():
    global _runtime_api_key
    key = (request.get_json() or {}).get('key', '').strip()
    if not key:
        return jsonify({'error': 'Clé vide'}), 400
    _runtime_api_key = key
    for a in agents.values():
        a.api_key = key
        a.llm.api_key = key
    return jsonify({'ok': True})


@api_bp.route('/setbrave', methods=['POST'])
@login_required_api
def set_brave():
    key = (request.get_json() or {}).get('key', '').strip()
    if not key:
        return jsonify({'error': 'Clé vide'}), 400
    os.environ['BRAVE_SEARCH_API_KEY'] = key
    for a in agents.values():
        a.tool_mgr.web_tools._brave_key = key
    return jsonify({'ok': True})


@api_bp.route('/reasoning', methods=['POST'])
@login_required_api
def toggle_reasoning():
    global _runtime_reasoning
    data      = request.get_json() or {}
    workspace = session.get('current_workspace', 'default')
    agent     = _get_or_create_agent(workspace)
    agent.reasoning_enabled = bool(data['enabled']) if 'enabled' in data else not agent.reasoning_enabled
    _runtime_reasoning = agent.reasoning_enabled
    return jsonify({'reasoning_enabled': agent.reasoning_enabled})


@api_bp.route('/model', methods=['POST'])
@login_required_api
def set_model():
    global _runtime_model
    model = (request.get_json() or {}).get('model', '').strip()
    if not model:
        return jsonify({'error': 'model requis'}), 400
    if model not in Config.AVAILABLE_MODELS:
        return jsonify({'error': f'Modèle inconnu: {model}'}), 400
    _runtime_model    = model
    workspace         = session.get('current_workspace', 'default')
    if workspace in agents:
        agents[workspace].model     = model
        agents[workspace].llm.model = model
    timeout = Config.MODEL_TIMEOUTS.get(model, Config.DEFAULT_TIMEOUT)
    return jsonify({'model': model, 'timeout': timeout})


@api_bp.route('/status', methods=['GET'])
@login_required_api
def status():
    workspace     = session.get('current_workspace', 'default')
    agent         = agents.get(workspace)
    current_model = agent.model if agent else (_runtime_model or Config.DEFAULT_MODEL)
    metrics       = agent.metrics.to_dict() if agent else {}
    htoks         = agent.history_tokens if agent else 0
    max_htoks     = agent.max_htoks if agent else Config.MAX_HISTORY_TOKENS
    return jsonify({
        'model'            : current_model,
        'models'           : Config.AVAILABLE_MODELS,
        'history_len'      : len(agent.history) if agent else 0,
        'metrics'          : metrics,
        'api_key_set'      : bool((agent and agent.api_key) or _runtime_api_key or Config.OPENROUTER_API_KEY),
        'reasoning_enabled': agent.reasoning_enabled if agent else _runtime_reasoning,
        'active_conv'      : session.get('active_conv'),
        'memory_count'     : Memory.query.count(),
        'cache_stats'      : agent.cache.stats() if agent else {},
        'timeout'          : Config.MODEL_TIMEOUTS.get(current_model, Config.DEFAULT_TIMEOUT),
        'workspace'        : workspace,
        'workspaces'       : workspace_manager.list_workspaces(),
        'agents_in_memory' : len(agents),
        'token_budget'     : {'used': htoks, 'max': max_htoks},
    })


# ── Project context ───────────────────────────────────────────────────────────

@api_bp.route('/project', methods=['GET'])
@login_required_api
def get_project():
    workspace = session.get('current_workspace', 'default')
    ctx       = db.session.get(ProjectContext, workspace)
    if not ctx:
        return jsonify({'workspace': workspace, 'stack': None, 'entry_point': None, 'notes': None})
    return jsonify({'workspace': ctx.workspace, 'stack': ctx.stack,
                    'entry_point': ctx.entry_point, 'notes': ctx.notes})


@api_bp.route('/project', methods=['POST'])
@login_required_api
def update_project():
    workspace = session.get('current_workspace', 'default')
    data      = request.get_json() or {}
    ctx       = db.session.get(ProjectContext, workspace)
    if not ctx:
        ctx = ProjectContext(workspace=workspace)
        db.session.add(ctx)
    if 'stack'       in data: ctx.stack       = data['stack']
    if 'entry_point' in data: ctx.entry_point = data['entry_point']
    if 'notes'       in data: ctx.notes       = data['notes']
    db.session.commit()
    return jsonify({'ok': True})


# ── Upload texte ──────────────────────────────────────────────────────────────

@api_bp.route('/upload', methods=['POST'])
@login_required_api
@limiter.limit('10 per minute')
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier'}), 400
    f    = request.files['file']
    name = secure_filename(f.filename or 'upload.txt')
    ext  = os.path.splitext(name)[1].lower()
    if ext == '.zip':
        return jsonify({'error': 'Pour importer un projet ZIP, utilise /import ou le bouton dédié.',
                        'is_zip': True}), 400
    if ext not in Config.ALLOWED_UPLOAD_EXT:
        return jsonify({'error': f'Extension non autorisée: {ext}'}), 400
    content = f.read(Config.UPLOAD_MAX_SIZE + 1)
    if len(content) > Config.UPLOAD_MAX_SIZE:
        return jsonify({'error': 'Fichier trop lourd (max 500 KB)'}), 413
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        text = content.decode('latin-1', errors='replace')
    return jsonify({'ok': True, 'filename': name, 'content': text,
                    'lines': text.count('\n') + 1, 'size': len(content)})


# ── Upload ZIP ────────────────────────────────────────────────────────────────

@api_bp.route('/upload/zip', methods=['POST'])
@login_required_api
@limiter.limit('5 per minute')
def upload_zip():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier'}), 400
    f    = request.files['file']
    name = secure_filename(f.filename or 'project.zip')
    ext  = os.path.splitext(name)[1].lower()
    if ext != '.zip':
        return jsonify({'error': 'Seuls les .zip sont acceptés'}), 400
    content = f.read(Config.ZIP_MAX_SIZE + 1)
    if len(content) > Config.ZIP_MAX_SIZE:
        return jsonify({'error': 'ZIP trop lourd (max 10 MB)'}), 413

    ws_name  = re.sub(r'[^a-zA-Z0-9_\-]', '_', os.path.splitext(name)[0])[:32] or 'imported'
    existing = workspace_manager.list_workspaces()
    base, counter = ws_name, 1
    while ws_name in existing:
        ws_name = f'{base}_{counter}'
        counter += 1

    try:
        ws_path = workspace_manager.create_workspace(ws_name)
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            files_extracted, skipped = [], []
            names    = zf.namelist()
            top_dirs = {n.split('/')[0] for n in names if '/' in n}
            prefix   = ''
            if len(top_dirs) == 1:
                only = list(top_dirs)[0]
                if all(n.startswith(only + '/') or n == only + '/' for n in names):
                    prefix = only + '/'
            for member in zf.infolist():
                rel = member.filename
                if prefix and rel.startswith(prefix):
                    rel = rel[len(prefix):]
                if not rel or rel.startswith('..') or os.path.isabs(rel):
                    skipped.append(rel)
                    continue
                parts = rel.replace('\\', '/').split('/')
                if any(p in ('__pycache__', '.git', 'node_modules', '.DS_Store') for p in parts):
                    skipped.append(rel)
                    continue
                target = os.path.realpath(os.path.join(str(ws_path), rel))
                if not target.startswith(str(ws_path)):
                    skipped.append(rel)
                    continue
                if member.is_dir():
                    os.makedirs(target, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(member) as src, open(target, 'wb') as dst:
                        dst.write(src.read())
                    files_extracted.append(rel)
        indexers[ws_name] = CodeIndexer(ws_path)
        session['current_workspace'] = ws_name
        return jsonify({'ok': True, 'workspace': ws_name, 'path': str(ws_path),
                        'files': len(files_extracted), 'skipped': len(skipped),
                        'workspaces': workspace_manager.list_workspaces()})
    except zipfile.BadZipFile:
        return jsonify({'error': 'ZIP invalide ou corrompu'}), 400
    except Exception as e:
        logger.error(f'ZIP import error: {e}')
        return jsonify({'error': f'Erreur import: {e}'}), 500
