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
from web.models import db, Conversation, Memory
from web.limiter import limiter
from workspace.manager import WorkspaceManager
from workspace.indexer import CodeIndexer
from core.agent import DevAgent

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

workspace_manager = None
indexers = {}

MAX_AGENTS = 10
agents: OrderedDict = OrderedDict()

# FIX CLÉ API : clé définie via /api/setkey, persistée en mémoire pour être
# réutilisée à la création de tout nouvel agent (LRU eviction ou nouveau workspace).
# Sans ça, chaque nouvel agent repart sur Config.OPENROUTER_API_KEY (vide si
# l'env n'est pas défini), et la clé saisie dans l'UI est perdue.
_runtime_api_key: str = ''


def _get_or_create_agent(workspace: str) -> DevAgent:
    """Retourne l'agent du workspace, en gérant le LRU et la création."""
    if workspace in agents:
        agents.move_to_end(workspace)
        return agents[workspace]
    if len(agents) >= MAX_AGENTS:
        evicted, _ = agents.popitem(last=False)
        logger.info(f'[AGENTS] Éviction LRU du workspace: {evicted}')
    path = workspace_manager.switch_workspace(workspace)
    # Utilise la clé runtime si disponible, sinon celle de l'env
    effective_key = _runtime_api_key or Config.OPENROUTER_API_KEY
    agent = DevAgent(str(path), config={'api_key': effective_key} if effective_key else {})
    if workspace in indexers:
        agent.tool_mgr.search_tools.set_indexer(indexers[workspace])
    agents[workspace] = agent
    return agent


def init_api(ws_manager):
    global workspace_manager
    workspace_manager = ws_manager


# ---------------------------------------------------------------------------
# /chat
# ---------------------------------------------------------------------------

@api_bp.route('/chat', methods=['POST'])
@login_required_api
# BUG-10 FIX : limite explicite sur la route la plus coûteuse (appel LLM).
# Sans limite, n'importe qui avec un cookie valide peut spammer l'API.
@limiter.limit('30 per minute')
def chat():
    data      = request.get_json() or {}
    msg       = data.get('message', '').strip()
    workspace = data.get('workspace', session.get('current_workspace', 'default'))
    if not msg:
        return jsonify({'error': 'Message vide'}), 400

    agent = _get_or_create_agent(workspace)

    # Charger l'historique depuis la BD
    conv_id = session.get('active_conv')
    if conv_id:
        # BUG-14 FIX : Conversation.query.get() est déprécié en SQLAlchemy 2.x
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

    # Capture tout ce dont le générateur a besoin PENDANT le contexte requête.
    # Après le return Response(), Flask/Gunicorn peut détruire le contexte
    # avant que le générateur finisse de streamer — current_app et session
    # deviennent alors des proxies non liés → RuntimeError.
    captured_conv_id = session.get('active_conv')
    # current_app._get_current_object() retourne l'objet Flask réel (pas le proxy).
    # On peut l'utiliser librement hors contexte requête.
    flask_app = current_app._get_current_object()

    def generate():
        final_history = None
        try:
            for event in agent.stream_task(msg):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get('type') in ('done', 'error'):
                    final_history = agent.history.copy()
        finally:
            if final_history is not None:
                # On utilise flask_app (objet réel capturé) au lieu de
                # current_app (proxy invalide hors contexte requête).
                with flask_app.app_context():
                    if captured_conv_id:
                        conv_obj = db.session.get(Conversation, captured_conv_id)
                        if conv_obj:
                            conv_obj.set_history(final_history)
                            db.session.commit()

    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
    })


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

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


@api_bp.route('/index', methods=['POST'])
@login_required_api
def index_workspace():
    """Indexe un workspace, crée l'indexer si nécessaire."""
    data = request.get_json() or {}
    workspace = data.get('workspace', session.get('current_workspace', 'default'))

    # S'assurer que workspace est bien sélectionné
    session['current_workspace'] = workspace

    # Créer l'indexer si jamais il n'existe pas
    if workspace not in indexers:
        try:
            path = workspace_manager.switch_workspace(workspace)
            indexers[workspace] = CodeIndexer(path)
        except Exception as e:
            return jsonify({'error': f'Impossible d’initialiser le workspace: {e}'}), 500

    try:
        indexers[workspace].index_directory()
        return jsonify({'status': 'Indexation terminée', 'workspace': workspace})
    except Exception as e:
        return jsonify({'error': f'Erreur durant l’indexation: {e}'}), 500

@api_bp.route('/search/semantic', methods=['POST'])
@login_required_api
def semantic_search():
    data      = request.get_json() or {}
    query     = data.get('query')
    workspace = data.get('workspace', session.get('current_workspace', 'default'))
    if not query:
        return jsonify({'error': 'Query requise'}), 400
    if workspace not in indexers:
        return jsonify({'error': 'Workspace non indexé'}), 400
    results = indexers[workspace].search(query, n_results=10)
    return jsonify(results)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

@api_bp.route('/conversations', methods=['GET'])
@login_required_api
def list_convs():
    workspace = session.get('current_workspace', 'default')
    convs = (Conversation.query
             .filter_by(workspace=workspace)
             .order_by(Conversation.created_at.desc())
             .all())
    return jsonify({
        'conversations': [{
            'id': c.id,
            'name': c.name,
            'created_at': c.created_at.isoformat(),
            'msg_count': len(c.get_history()),
        } for c in convs],
        'active': session.get('active_conv'),
    })


@api_bp.route('/conversations', methods=['POST'])
@login_required_api
def create_conv():
    data      = request.get_json() or {}
    name      = data.get('name', '').strip() or None
    workspace = session.get('current_workspace', 'default')
    conv = Conversation(
        id=str(uuid.uuid4())[:8],
        name=name or f"Chat {datetime.now().strftime('%H:%M')}",
        workspace=workspace,
    )
    db.session.add(conv)
    db.session.commit()
    session['active_conv'] = conv.id
    if workspace in agents:
        agents[workspace].history = []
    return jsonify({
        'id': conv.id,
        'name': conv.name,
        'created_at': conv.created_at.isoformat(),
        'msg_count': 0,
    })


@api_bp.route('/conversations/<cid>', methods=['GET'])
@login_required_api
def load_conv(cid):
    # BUG-14 FIX
    conv = db.session.get(Conversation, cid)
    if not conv:
        return jsonify({'error': 'Introuvable'}), 404
    session['active_conv'] = conv.id
    workspace = conv.workspace
    if workspace in agents:
        agents[workspace].history = conv.get_history()
    return jsonify({'id': conv.id, 'name': conv.name, 'history': conv.get_history()})


@api_bp.route('/conversations/<cid>', methods=['DELETE'])
@login_required_api
def delete_conv(cid):
    # BUG-14 FIX
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
    # BUG-14 FIX
    conv = db.session.get(Conversation, cid)
    if not conv:
        return jsonify({'error': 'Introuvable'}), 404
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if name:
        conv.name = name
        db.session.commit()
    return jsonify({'ok': True, 'name': conv.name})


# ---------------------------------------------------------------------------
# Mémoire persistante
# ---------------------------------------------------------------------------

def _refresh_memory_context():
    """Recharge le contexte mémoire de tous les agents actifs."""
    mems = Memory.query.all()
    ctx  = '\n'.join(f'- {m.key}: {m.value}' for m in mems)
    for agent in agents.values():
        agent.memory_context = ctx


@api_bp.route('/memory', methods=['GET'])
@login_required_api
def get_mem():
    mems = Memory.query.all()
    return jsonify({'memory': {m.key: m.value for m in mems}})


@api_bp.route('/memory', methods=['POST'])
@login_required_api
def add_mem():
    data = request.get_json() or {}
    key  = data.get('key', '').strip()
    val  = data.get('value', '').strip()
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


# ---------------------------------------------------------------------------
# Contrôles agent
# ---------------------------------------------------------------------------

@api_bp.route('/clear', methods=['POST'])
@login_required_api
def clear():
    workspace = session.get('current_workspace', 'default')
    if workspace in agents:
        agents[workspace].history = []
    conv_id = session.get('active_conv')
    if conv_id:
        # BUG-14 FIX
        conv = db.session.get(Conversation, conv_id)
        if conv:
            conv.set_history([])
            db.session.commit()
    return jsonify({'ok': True})


@api_bp.route('/setkey', methods=['POST'])
@login_required_api
def set_key():
    global _runtime_api_key
    data = request.get_json() or {}
    key  = data.get('key', '').strip()
    if not key:
        return jsonify({'error': 'Clé vide'}), 400
    # Persiste la clé pour les agents futurs (nouveaux workspaces / après éviction LRU)
    _runtime_api_key = key
    # Met à jour aussi tous les agents déjà en mémoire
    for agent in agents.values():
        agent.api_key     = key
        agent.llm.api_key = key
    return jsonify({'ok': True})


@api_bp.route('/reasoning', methods=['POST'])
@login_required_api
def toggle_reasoning():
    data      = request.get_json() or {}
    workspace = session.get('current_workspace', 'default')
    if workspace in agents:
        if 'enabled' in data:
            agents[workspace].reasoning_enabled = bool(data['enabled'])
        else:
            agents[workspace].reasoning_enabled = not agents[workspace].reasoning_enabled
        return jsonify({'reasoning_enabled': agents[workspace].reasoning_enabled})
    return jsonify({'reasoning_enabled': False})


@api_bp.route('/model', methods=['POST'])
@login_required_api
def set_model():
    data  = request.get_json() or {}
    model = data.get('model', '').strip()
    if not model:
        return jsonify({'error': 'model requis'}), 400
    workspace = session.get('current_workspace', 'default')
    if workspace in agents:
        agents[workspace].model     = model
        agents[workspace].llm.model = model
    return jsonify({'model': model})


@api_bp.route('/status', methods=['GET'])
@login_required_api
def status():
    workspace = session.get('current_workspace', 'default')
    agent     = agents.get(workspace)
    metrics   = agent.metrics.to_dict() if agent else {}
    return jsonify({
        'model'             : agent.model if agent else Config.DEFAULT_MODEL,
        'fallbacks'         : Config.FREE_FALLBACKS,
        'history_len'       : len(agent.history) if agent else 0,
        'metrics'           : metrics,
        'api_key_set'       : bool(agent and agent.api_key),
        'reasoning_enabled' : agent.reasoning_enabled if agent else False,
        'active_conv'       : session.get('active_conv'),
        'memory_count'      : Memory.query.count(),
        'cache_stats'       : agent.cache.stats() if agent else {},
        'timeout'           : Config.MODEL_TIMEOUTS.get(
                                  agent.model if agent else '', Config.DEFAULT_TIMEOUT),
        'workspace'         : workspace,
        'workspaces'        : workspace_manager.list_workspaces(),
        'agents_in_memory'  : len(agents),   # utile pour monitorer le LRU
    })


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@api_bp.route('/upload', methods=['POST'])
@login_required_api
@limiter.limit('10 per minute')
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier envoyé.'}), 400
    f    = request.files['file']
    name = secure_filename(f.filename or 'upload.txt')
    ext  = os.path.splitext(name)[1].lower()
    if ext not in Config.ALLOWED_UPLOAD_EXT:
        return jsonify({'error': f'Extension non autorisée: {ext}'}), 400
    content = f.read(Config.UPLOAD_MAX_SIZE + 1)
    if len(content) > Config.UPLOAD_MAX_SIZE:
        return jsonify({'error': 'Fichier trop lourd (max 500 KB).'}), 413
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text = content.decode('latin-1')
        except Exception:
            return jsonify({'error': 'Encodage non supporté.'}), 400
    lines = text.count('\n') + 1
    return jsonify({
        'ok': True,
        'filename': name,
        'content': text,
        'lines': lines,
        'size': len(content),
    })
