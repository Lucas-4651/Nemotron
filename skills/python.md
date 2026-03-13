
# SKILL: Python / Flask / pip

## Protocole obligatoire
1. `view_file` sur chaque fichier à modifier AVANT tout changement
2. `list_directory` pour la structure complète
3. `view_file requirements.txt` pour les dépendances disponibles
4. `str_replace` pour modifications ciblées
5. `run_python` pour valider la syntaxe et le comportement

---

## Flask production-ready

```python
# app.py — factory pattern (recommandé)
from flask import Flask
from config import Config

def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(config or Config)

    # Extensions
    from web.models import db
    db.init_app(app)

    # Blueprints
    from web.routes_api import api_bp
    from web.routes_ui import ui_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(ui_bp)

    # Health check (obligatoire pour Render)
    @app.route('/health')
    def health():
        return {'status': 'ok'}

    # Gestion d'erreurs centralisée
    @app.errorhandler(404)
    def not_found(e): return {'error': 'Not found'}, 404

    @app.errorhandler(500)
    def server_error(e): return {'error': 'Server error'}, 500

    return app
```

## Config avec validation

```python
# config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24).hex()
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
    # SQLAlchemy — corriger le préfixe postgres:// -> postgresql://
    SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace('postgres://', 'postgresql://')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    PORT = int(os.environ.get('PORT', 5000))
```

## SQLAlchemy — modèles et requêtes

```python
# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    _data = db.Column('data', db.Text)  # JSON stocké en TEXT

    @property
    def data(self):
        return json.loads(self._data) if self._data else {}

    @data.setter
    def data(self, value):
        self._data = json.dumps(value)

    def to_dict(self):
        return {'id': self.id, 'email': self.email, 'data': self.data}
```

## Streaming SSE (Server-Sent Events)

```python
# routes_api.py — pattern SSE pour agents/streaming
import json
from flask import Response, stream_with_context

@api_bp.route('/stream', methods=['POST'])
def stream():
    def generate():
        try:
            for event in some_generator():
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )
```

## Requêtes HTTP robustes

```python
# utils/http.py
import requests
import time

def fetch_with_retry(url, method='GET', max_retries=3, **kwargs):
    kwargs.setdefault('timeout', 30)
    for attempt in range(1, max_retries + 1):
        try:
            r = getattr(requests, method.lower())(url, **kwargs)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.Timeout:
            if attempt == max_retries: raise
            time.sleep(attempt)
        except requests.exceptions.RequestException as e:
            if attempt == max_retries: raise
            time.sleep(attempt)
    return None
```

## wsgi.py — point d'entrée Render/Gunicorn

```python
# wsgi.py
from app import create_app
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=app.config['PORT'])
```

## requirements.txt — dépendances essentielles

```
flask>=3.0
flask-sqlalchemy>=3.1
flask-login>=0.6
gunicorn>=21.0
psycopg2-binary>=2.9
python-dotenv>=1.0
requests>=2.31
```

## Structure recommandée

```
projet/
├── wsgi.py              ← point d'entrée
├── app.py               ← factory create_app()
├── config.py
├── web/
│   ├── models.py        ← SQLAlchemy models
│   ├── routes_api.py    ← Blueprint API
│   ├── routes_ui.py     ← Blueprint UI
│   └── auth.py
├── templates/
├── static/
├── requirements.txt
├── Procfile             ← pour Render
└── .env.example
```

## Render — déploiement

```
# Procfile
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn wsgi:app`
- `postgres://` doit être remplacé par `postgresql://` (voir config.py)
- `PORT` injecté automatiquement par Render
- Workers: 2 sur free tier (1 CPU)
- Timeout 120s recommandé pour les agents avec LLM

## Termux / Proot

```bash
# Installation
pip install -r requirements.txt --break-system-packages

# Ou avec venv (recommandé)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Lancer en dev
python3 wsgi.py
# ou
flask --app app run --debug

# Vérifier syntaxe
python3 -m py_compile fichier.py
```

## Erreurs courantes

- `Application context` → `with app.app_context():`
- `DetachedInstanceError` → session fermée, utiliser `db.session.refresh(obj)`
- `Circular import` → déplacer les imports dans les fonctions
- `postgres:// non reconnu` → remplacer par `postgresql://` dans config
- `gunicorn: command not found` → `pip install gunicorn --break-system-packages`
- `Worker timeout` sur Render → augmenter `--timeout` dans Procfile
