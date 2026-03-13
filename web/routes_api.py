from flask import Blueprint, request, jsonify, Response, session, current_app
from werkzeug.utils import secure_filename
import os
import json
import uuid
from datetime import datetime

from config import Config
from web.auth import login_required_api
from web.models import db, Conversation, Memory
from workspace.manager import WorkspaceManager
from workspace.indexer import CodeIndexer
from core.agent import DevAgent

api_bp = Blueprint('api', __name__)

# Gestionnaire de workspace global (à initialiser dans app.py)
workspace_manager = None
indexers = {}  # workspace_name -> CodeIndexer
agents = {}    # workspace_name -> DevAgent (attention à la gestion mémoire)

def init_api(ws_manager):
    global workspace_manager
    workspace_manager = ws_manager

@api_bp.route('/chat', methods=['POST'])
@login_required_api
def chat():
    data = request.get_json() or {}
    msg = data.get('message', '').strip()
    workspace = data.get('workspace', session.get('current_workspace', 'default'))
    if not msg:
        return jsonify({'error': 'Message vide'}), 400

    # Récupérer ou créer l'agent pour ce workspace
    if workspace not in agents:
        path = workspace_manager.switch_workspace(workspace)
        agent = DevAgent(str(path))
        # Associer l'indexeur s'il existe
        if workspace in indexers:
            agent.tool_mgr.search_tools.set_indexer(indexers[workspace])
        agents[workspace] = agent
    else:
        agent = agents[workspace]

    # Charger l'historique depuis la BD
    conv_id = session.get('active_conv')
    if conv_id:
        conv = Conversation.query.get(conv_id)
        if conv:
            agent.history = conv.get_history()
    else:
        # nouvelle conversation
        conv = Conversation(
            id=str(uuid.uuid4())[:8],
            name=f"Chat {datetime.now().strftime('%H:%M')}",
            workspace=workspace
        )
        db.session.add(conv)
        db.session.commit()
        session['active_conv'] = conv.id
        agent.history = []

    def generate():
        final_history = None
        try:
            for event in agent.stream_task(msg):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get('type') == 'done':
                    final_history = agent.history.copy()
        finally:
            if final_history is not None:
                with current_app.app_context():
                    conv_id = session.get('active_conv')
                    if conv_id:
                        conv = Conversation.query.get(conv_id)
                        if conv:
                            conv.set_history(final_history)
                            db.session.commit()

    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })

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
    # Créer l'indexeur si nécessaire
    if name not in indexers:
        indexers[name] = CodeIndexer(path)
    # Mettre à jour l'agent si existant
    if name in agents:
        agents[name].tool_mgr.search_tools.set_indexer(indexers[name])
    return jsonify({'workspace': name, 'path': str(path)})

@api_bp.route('/index', methods=['POST'])
@login_required_api
def index_workspace():
    workspace = request.json.get('workspace', session.get('current_workspace', 'default'))
    if workspace not in indexers:
        return jsonify({'error': 'Workspace inconnu ou non initialisé'}), 400
    try:
        indexers[workspace].index_directory()
        return jsonify({'status': 'indexation terminée'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/search/semantic', methods=['POST'])
@login_required_api
def semantic_search():
    data = request.get_json() or {}
    query = data.get('query')
    workspace = data.get('workspace', session.get('current_workspace', 'default'))
    if not query:
        return jsonify({'error': 'Query requise'}), 400
    if workspace not in indexers:
        return jsonify({'error': 'Workspace non indexé'}), 400
    results = indexers[workspace].search(query, n_results=10)
    return jsonify(results)

@api_bp.route('/conversations', methods=['GET'])
@login_required_api
def list_convs():
    workspace = session.get('current_workspace', 'default')
    convs = Conversation.query.filter_by(workspace=workspace).order_by(Conversation.created_at.desc()).all()
    return jsonify({
        'conversations': [{
            'id': c.id,
            'name': c.name,
            'created_at': c.created_at.isoformat(),
            'msg_count': len(c.get_history())
        } for c in convs],
        'active': session.get('active_conv')
    })

@api_bp.route('/conversations', methods=['POST'])
@login_required_api
def create_conv():
    data = request.get_json() or {}
    name = data.get('name', '').strip() or None
    workspace = session.get('current_workspace', 'default')
    conv = Conversation(
        id=str(uuid.uuid4())[:8],
        name=name or f"Chat {datetime.now().strftime('%H:%M')}",
        workspace=workspace
    )
    db.session.add(conv)
    db.session.commit()
    session['active_conv'] = conv.id
    # Réinitialiser l'agent pour ce workspace
    if workspace in agents:
        agents[workspace].history = []
    return jsonify({'id': conv.id, 'name': conv.name, 'created_at': conv.created_at.isoformat(), 'msg_count': 0})

@api_bp.route('/conversations/<cid>', methods=['GET'])
@login_required_api
def load_conv(cid):
    conv = Conversation.query.get(cid)
    if not conv:
        return jsonify({'error': 'Introuvable'}), 404
    session['active_conv'] = conv.id
    # Charger l'historique dans l'agent
    workspace = conv.workspace
    if workspace in agents:
        agents[workspace].history = conv.get_history()
    return jsonify({'id': conv.id, 'name': conv.name, 'history': conv.get_history()})

@api_bp.route('/conversations/<cid>', methods=['DELETE'])
@login_required_api
def delete_conv(cid):
    conv = Conversation.query.get(cid)
    if not conv:
        return jsonify({'error': 'Introuvable'}), 404
    db.session.delete(conv)
    db.session.commit()
    if session.get('active_conv') == cid:
        session.pop('active_conv', None)
        # Choisir une autre conversation si elle existe
        other = Conversation.query.filter_by(workspace=conv.workspace).first()
        if other:
            session['active_conv'] = other.id
    return jsonify({'ok': True})

@api_bp.route('/conversations/<cid>/rename', methods=['POST'])
@login_required_api
def rename_conv(cid):
    conv = Conversation.query.get(cid)
    if not conv:
        return jsonify({'error': 'Introuvable'}), 404
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if name:
        conv.name = name
        db.session.commit()
    return jsonify({'ok': True, 'name': conv.name})

@api_bp.route('/memory', methods=['GET'])
@login_required_api
def get_mem():
    mems = Memory.query.all()
    return jsonify({'memory': {m.key: m.value for m in mems}})

@api_bp.route('/memory', methods=['POST'])
@login_required_api
def add_mem():
    data = request.get_json() or {}
    key = data.get('key', '').strip()
    val = data.get('value', '').strip()
    if not key or not val:
        return jsonify({'error': 'key + value requis'}), 400
    mem = Memory.query.filter_by(key=key).first()
    if mem:
        mem.value = val
    else:
        mem = Memory(key=key, value=val)
        db.session.add(mem)
    db.session.commit()
    # Mettre à jour le contexte mémoire de tous les agents
    for agent in agents.values():
        agent.memory_context = '\n'.join(f'- {k}: {v}' for k, v in {m.key: m.value for m in Memory.query.all()}.items())
    return jsonify({'ok': True})

@api_bp.route('/memory/<key>', methods=['DELETE'])
@login_required_api
def del_mem(key):
    Memory.query.filter_by(key=key).delete()
    db.session.commit()
    for agent in agents.values():
        agent.memory_context = '\n'.join(f'- {k}: {v}' for k, v in {m.key: m.value for m in Memory.query.all()}.items())
    return jsonify({'ok': True})

@api_bp.route('/clear', methods=['POST'])
@login_required_api
def clear():
    workspace = session.get('current_workspace', 'default')
    if workspace in agents:
        agents[workspace].history = []
    conv_id = session.get('active_conv')
    if conv_id:
        conv = Conversation.query.get(conv_id)
        if conv:
            conv.set_history([])
            db.session.commit()
    return jsonify({'ok': True})

@api_bp.route('/setkey', methods=['POST'])
@login_required_api
def set_key():
    data = request.get_json() or {}
    key = data.get('key', '').strip()
    if not key:
        return jsonify({'error': 'Clé vide'}), 400
    for agent in agents.values():
        agent.api_key = key
        agent.llm.api_key = key
    return jsonify({'ok': True})

@api_bp.route('/reasoning', methods=['POST'])
@login_required_api
def toggle_reasoning():
    data = request.get_json() or {}
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
    data = request.get_json() or {}
    model = data.get('model', '').strip()
    if not model:
        return jsonify({'error': 'model requis'}), 400
    workspace = session.get('current_workspace', 'default')
    if workspace in agents:
        agents[workspace].model = model
        agents[workspace].llm.model = model
    return jsonify({'model': model})

@api_bp.route('/status', methods=['GET'])
@login_required_api
def status():
    from config import Config
    workspace = session.get('current_workspace', 'default')
    agent = agents.get(workspace)
    metrics = agent.metrics.to_dict() if agent else {}
    return jsonify({
        'model': agent.model if agent else Config.DEFAULT_MODEL,
        'fallbacks': Config.FREE_FALLBACKS,
        'history_len': len(agent.history) if agent else 0,
        'metrics': metrics,
        'api_key_set': bool(agent and agent.api_key),
        'reasoning_enabled': agent.reasoning_enabled if agent else False,
        'active_conv': session.get('active_conv'),
        'memory_count': Memory.query.count(),
        'cache_stats': agent.cache.stats() if agent else {},
        'timeout': Config.MODEL_TIMEOUTS.get(agent.model if agent else '', Config.DEFAULT_TIMEOUT),
        'workspace': workspace,
        'workspaces': workspace_manager.list_workspaces(),
    })

@api_bp.route('/upload', methods=['POST'])
@login_required_api
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier envoyé.'}), 400
    f = request.files['file']
    name = secure_filename(f.filename or 'upload.txt')
    ext = os.path.splitext(name)[1].lower()
    if ext not in Config.ALLOWED_UPLOAD_EXT:
        return jsonify({'error': f'Extension non autorisée: {ext}'}), 400
    content = f.read(Config.UPLOAD_MAX_SIZE + 1)
    if len(content) > Config.UPLOAD_MAX_SIZE:
        return jsonify({'error': 'Fichier trop lourd (max 500KB).'}), 413
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text = content.decode('latin-1')
        except:
            return jsonify({'error': 'Encodage non supporté.'}), 400
    lines = text.count('\n') + 1
    return jsonify({
        'ok': True,
        'filename': name,
        'content': text,
        'lines': lines,
        'size': len(content),
    })