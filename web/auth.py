from functools import wraps
from flask import session, jsonify, request, redirect, url_for

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Non authentifié'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def login_required_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Non authentifié'}), 401
        return f(*args, **kwargs)
    return decorated