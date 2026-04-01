import sys
import os
import hmac
import logging
import logging.handlers
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, session, render_template, jsonify, request, redirect, url_for

from config import Config
from web.auth import login_required
from web.models import db, Conversation, Memory, ProjectContext
from web.routes_api import api_bp, init_api
from web.routes_ui import ui_bp
from web.limiter import limiter
from workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)


def setup_logging(app: Flask):
    os.makedirs(Config.LOG_DIR, exist_ok=True)
    level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    fmt   = logging.Formatter(
        '%(asctime)s %(levelname)-8s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Fichier rotatif (5 MB × 3 fichiers)
    fh = logging.handlers.RotatingFileHandler(
        os.path.join(Config.LOG_DIR, 'nemotron.log'),
        maxBytes=5_000_000, backupCount=3, encoding='utf-8'
    )
    fh.setFormatter(fmt)
    fh.setLevel(level)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    ch.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(fh)
    root.addHandler(ch)
    logger.info('Logging initialisé → %s/nemotron.log', Config.LOG_DIR)


def create_app():
    root_dir     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(root_dir, 'templates')
    static_dir   = os.path.join(root_dir, 'static')

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY

    # Sessions permanentes
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(seconds=Config.SESSION_LIFETIME)

    # Database
    app.config['SQLALCHEMY_DATABASE_URI']        = Config.DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

    # BUG-FIX #7 : la config rate limiter DOIT être définie AVANT limiter.init_app(app)
    # Avant : config définie après init_app → ignorée → limites non appliquées
    app.config['RATELIMIT_DEFAULT']     = '200 per minute'
    app.config['RATELIMIT_STORAGE_URI'] = 'memory://'
    limiter.init_app(app)

    # Logging
    setup_logging(app)

    # Workspace
    ws_manager = WorkspaceManager(Config.WORKSPACE_ROOT)
    ws_manager.switch_workspace('default')
    init_api(ws_manager)

    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    # ── Auth ──────────────────────────────────────────────────────────────────
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        if request.method == 'POST':
            pwd    = request.form.get('password', '')
            pwd_ok = hmac.compare_digest(Config.APP_PASSWORD.encode(), pwd.encode())
            if pwd_ok:
                session['logged_in'] = True
                return redirect(url_for('ui.index'))
            error = 'Mot de passe incorrect.'
        return render_template('login.html', error=error)

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    # ── Health check ──────────────────────────────────────────────────────────
    @app.route('/health')
    def health():
        checks  = {}
        overall = 'ok'

        # DB
        try:
            db.session.execute(db.text('SELECT 1'))
            checks['db'] = 'ok'
        except Exception as e:
            checks['db'] = f'error: {e}'
            overall = 'degraded'

        # API key
        checks['api_key'] = 'set' if (
            Config.OPENROUTER_API_KEY or
            getattr(app, '_runtime_api_key', '')
        ) else 'missing'

        # Workspace
        try:
            checks['workspace'] = 'ok' if os.path.isdir(Config.WORKSPACE_ROOT) else 'missing'
        except Exception:
            checks['workspace'] = 'error'

        # Logs dir
        checks['logs'] = 'ok' if os.path.isdir(Config.LOG_DIR) else 'missing'

        status_code = 200 if overall == 'ok' else 503
        return jsonify({'status': overall, 'checks': checks}), status_code

    return app


if __name__ == '__main__':
    app  = create_app()
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
