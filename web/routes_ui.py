from flask import Blueprint, render_template, session
from web.auth import login_required

ui_bp = Blueprint('ui', __name__)

@ui_bp.route('/')
@login_required
def index():
    return render_template('index.html')

# On pourrait ajouter d'autres routes UI si nécessaire