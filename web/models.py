# web/models.py — v3
# NEW : index sur workspace + created_at pour performances queries
# NEW : ProjectContext pour persister le contexte projet
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()


class Conversation(db.Model):
    __tablename__ = 'conversation'
    id         = db.Column(db.String(32),  primary_key=True)
    name       = db.Column(db.String(200), nullable=False, default='Nouvelle conversation')
    created_at = db.Column(db.DateTime,    default=datetime.utcnow, index=True)
    workspace  = db.Column(db.String(200), nullable=False, default='default', index=True)
    history    = db.Column(db.Text,        default='[]')

    def set_history(self, hist: list):
        self.history = json.dumps(hist, ensure_ascii=False)

    def get_history(self) -> list:
        try:
            return json.loads(self.history) if self.history else []
        except Exception:
            return []

    def msg_count(self) -> int:
        try:
            hist = self.get_history()
            return sum(1 for m in hist if m.get('role') in ('user', 'assistant'))
        except Exception:
            return 0


class Memory(db.Model):
    __tablename__ = 'memory'
    id    = db.Column(db.Integer,     primary_key=True)
    key   = db.Column(db.String(200), nullable=False, unique=True, index=True)
    value = db.Column(db.Text,        nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectContext(db.Model):
    """Stocke des métadonnées persistantes sur un workspace/projet."""
    __tablename__ = 'project_context'
    workspace  = db.Column(db.String(200), primary_key=True)
    stack      = db.Column(db.String(500), nullable=True)   # ex: "Flask + PostgreSQL"
    entry_point= db.Column(db.String(200), nullable=True)   # ex: "wsgi.py"
    notes      = db.Column(db.Text,        nullable=True)   # notes libres
    updated_at = db.Column(db.DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)
