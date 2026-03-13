from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class Conversation(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(200), nullable=False, default='Nouvelle conversation')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    workspace = db.Column(db.String(200), nullable=False, default='default')
    history = db.Column(db.Text, default='[]')  # JSON list

    def set_history(self, hist):
        self.history = json.dumps(hist, ensure_ascii=False)

    def get_history(self):
        return json.loads(self.history) if self.history else []

class Memory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(200), nullable=False, unique=True)
    value = db.Column(db.Text, nullable=False)