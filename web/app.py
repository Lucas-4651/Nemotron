import sys
import os
import hmac
import logging

# Ajoute le répertoire parent (racine du projet) au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, session, render_template, jsonify, request, redirect, url_for

from config import Config
from web.auth import login_required
from web.models import db, Conversation, Memory
from web.routes_api import api_bp, init_api
from web.routes_ui import ui_bp
from web.limiter import limiter          # BUG-10 : instance partagée
from workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)


def create_app():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(root_dir, 'templates')
    static_dir   = os.path.join(root_dir, 'static')

    app = Flask(__name__,
                template_folder=template_dir,
                static_folder=static_dir)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY

    # Database
    app.config['SQLALCHEMY_DATABASE_URI']        = Config.DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    # BUG-01 FIX : db.create_all() était dans __main__ seulement →
    # jamais exécuté via wsgi.py (Gunicorn / Render) → crash immédiat en prod.
    with app.app_context():
        db.create_all()
        if Memory.query.count() == 0:
            db.session.add(Memory(key='bienvenue', value='Assistant prêt.'))
            db.session.commit()

    # BUG-10 FIX : rate limiter avec des limites réelles.
    # default_limits=[] = aucune protection. On passe une limite globale
    # et des limites spécifiques sur /api/chat dans routes_api.py.
    limiter.init_app(app)
    app.config['RATELIMIT_DEFAULT'] = '200 per minute'
    app.config['RATELIMIT_STORAGE_URI'] = 'memory://'

    # Workspace manager
    ws_manager = WorkspaceManager(Config.WORKSPACE_ROOT)
    ws_manager.switch_workspace('default')

    init_api(ws_manager)

    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # ---------- Auth routes ----------

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        if request.method == 'POST':
            pwd = request.form.get('password', '')
            # BUG-15 FIX : hmac.compare_digest évite les timing attacks.
            # La comparaison directe (==) permet de mesurer le temps de réponse
            # pour deviner le mot de passe caractère par caractère.
            pwd_ok = hmac.compare_digest(
                Config.APP_PASSWORD.encode(),
                pwd.encode()
            )
            if pwd_ok:
                session['logged_in'] = True
                return redirect(url_for('ui.index'))
            # BUG-21 FIX : l'indentation du commentaire et du bloc error
            # était décalée d'un niveau, ce qui rendait la lecture confuse.
            error = 'Mot de passe incorrect.'
        return render_template('login.html', error=error)

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'}), 200

    return app


if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    # BUG-19 FIX : debug=True exposait le debugger Werkzeug interactif en prod.
    # On lit la variable d'env FLASK_DEBUG (défaut False).
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
