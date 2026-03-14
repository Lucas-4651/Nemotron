# web/limiter.py
# Instance partagée du rate-limiter Flask-Limiter.
# On l'initialise ici (sans app) puis on appelle limiter.init_app(app)
# dans create_app() pour respecter le pattern Application Factory.
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
