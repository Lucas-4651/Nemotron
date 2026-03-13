import sys
import os
# Ajoute le répertoire parent (racine du projet) au path pour pouvoir importer config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, session, render_template, jsonify, request, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime

from config import Config
from web.auth import login_required
from web.models import db, Conversation, Memory
from web.routes_api import api_bp, init_api
from web.routes_ui import ui_bp
from workspace.manager import WorkspaceManager

def create_app():
    # Calcul du chemin absolu vers la racine du projet
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(root_dir, 'templates')
    static_dir = os.path.join(root_dir, 'static')

    app = Flask(__name__,
                template_folder=template_dir,
                static_folder=static_dir)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY

    # Database
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    # Rate limiter
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],
        storage_uri='memory://',
    )

    # Workspace manager
    ws_manager = WorkspaceManager(Config.WORKSPACE_ROOT)
    # Initialiser le workspace par défaut
    ws_manager.switch_workspace('default')

    # Initialiser les routes API avec le workspace manager
    init_api(ws_manager)

    # Register blueprints
    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Auth routes
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        if request.method == 'POST':
            pwd = request.form.get('password', '')
        # Comparaison directe (pas de hash)
            if Config.APP_PASSWORD == pwd:
                session['logged_in'] = True
                return redirect(url_for('ui.index'))
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
    with app.app_context():
        db.create_all()
        # Créer une mémoire par défaut si vide
        if Memory.query.count() == 0:
            db.session.add(Memory(key='bienvenue', value='Assistant prêt.'))
            db.session.commit()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)