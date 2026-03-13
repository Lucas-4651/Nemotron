
# SKILL: Debug / Analyse d'erreurs

## Protocole obligatoire
1. `view_file` sur le fichier concerné — ne jamais corriger sans lire le code
2. Identifier la ligne exacte dans le stack trace
3. `run_python` ou `run_node` pour reproduire l'erreur
4. Fix minimal d'abord — ne pas refactoriser en même temps
5. Valider que l'erreur disparaît après le fix

---

## Lire un stack trace

```
# Python — lire du BAS vers le HAUT
Traceback (most recent call last):       ← début de la chaîne
  File "app.py", line 42, in route       ← où ça a été appelé
  File "service.py", line 18, in get     ← où ça a planté
AttributeError: 'NoneType' has no 'id'  ← l'erreur réelle ← LIRE ICI EN PREMIER

# JavaScript — idem
TypeError: Cannot read properties of undefined (reading 'map')
    at processData (utils.js:23:15)     ← fichier:ligne:colonne
    at async handler (routes.js:45:5)
```

## Reproduire une erreur

```python
# run_python — isoler le problème
import sys
sys.path.insert(0, '/chemin/vers/projet')

# Reproduire avec les données minimales qui causent l'erreur
from services.prediction import predict
result = predict({'match_id': None})  # tester le cas qui plante
print(result)
```

```javascript
// run_node — tester une fonction isolément
import { fetchMatches } from './services/vfl.js'
const result = await fetchMatches(0)  // tester avec valeur limite
console.log(JSON.stringify(result, null, 2))
```

## Erreurs Python — causes et fixes

```python
# AttributeError: 'NoneType' has no attribute 'X'
# → une fonction a retourné None au lieu d'un objet
result = get_user(id)  # retourne None si inexistant
result.name  # PLANTE

# Fix:
result = get_user(id)
if result is None:
    return {'error': 'User not found'}, 404
# OU
result = get_user(id) or User()  # valeur par défaut

# KeyError: 'field'
data = {'a': 1}
data['b']  # PLANTE

# Fix:
data.get('b', default_value)  # retourne default si absent
data.get('b') or default_value

# TypeError: unsupported operand type(s): 'str' + 'int'
# → types incompatibles
total = "5" + 3  # PLANTE
# Fix:
total = int("5") + 3
# OU
total = f"{5 + 3}"

# JSONDecodeError
import json
json.loads("not json")  # PLANTE
# Fix:
try:
    data = json.loads(text)
except json.JSONDecodeError:
    data = {}  # ou logger l'erreur

# IndentationError / SyntaxError
# → utiliser python3 -m py_compile fichier.py pour localiser
```

## Erreurs JavaScript — causes et fixes

```javascript
// TypeError: Cannot read properties of undefined
const data = undefined
data.map(...)  // PLANTE

// Fix:
const data = response?.items ?? []  // optional chaining + nullish coalescing
data?.map(...)  // seulement si data existe

// UnhandledPromiseRejection
// → await manquant ou .catch() absent
async function handler() {
  const data = fetchData()  // MANQUE await
  // Fix:
  const data = await fetchData()
}

// ReferenceError: X is not defined
// → variable hors scope ou import manquant
import { helper } from './utils.js'  // vérifier l'import

// SyntaxError: Unexpected token
// → souvent une virgule manquante ou accolade non fermée
// → node --check fichier.js pour localiser

// CORS Error (dans le navigateur)
// → configurer côté SERVEUR, pas côté client
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*')
  next()
})
```

## Erreurs réseau / API

```python
# Debugger une requête HTTP qui échoue
import requests

r = requests.post(url, json=payload, timeout=30)
print(f"Status: {r.status_code}")
print(f"Headers: {dict(r.headers)}")
print(f"Body: {r.text[:500]}")  # les 500 premiers chars

# 401 → clé API invalide
# 422 → payload malformé (voir r.text pour les détails)
# 429 → rate limit (voir header Retry-After)
# 500 → erreur serveur distant (hors de notre contrôle)
# 503 → service indisponible (retry avec backoff)
```

## Erreurs Flask / SQLAlchemy

```python
# RuntimeError: Working outside of application context
# → accès à db/session hors contexte Flask
with app.app_context():
    user = User.query.get(1)

# sqlalchemy.orm.exc.DetachedInstanceError
# → objet chargé dans une session fermée
# Fix: utiliser expire_on_commit=False OU recharger dans la session
db.session.refresh(obj)

# IntegrityError: duplicate key / unique constraint
from sqlalchemy.exc import IntegrityError
try:
    db.session.add(obj)
    db.session.commit()
except IntegrityError:
    db.session.rollback()
    # gérer le doublon
```

## Erreurs Render / Production

```bash
# Voir les logs en temps réel sur Render
# Dans le dashboard → Logs

# Erreurs communes Render:
# R10 Boot timeout → le serveur ne démarre pas en 60s
#   → vérifier que PORT est bien utilisé: app.run(port=int(os.environ.get('PORT', 5000)))
# H10 App crashed → crash au démarrage, voir les logs
# H12 Request timeout → requête > 30s, optimiser ou répondre en streaming

# Tester localement comme en production
PORT=5000 NODE_ENV=production node server.js
```

## Stratégie de débogage progressif

```python
# Ajouter des logs stratégiques
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def ma_fonction(data):
    logger.debug(f"Entrée: {data}")
    result = traitement(data)
    logger.debug(f"Résultat: {result}")
    return result

# Vérifier les variables d'env au démarrage
for key in ['DATABASE_URL', 'API_KEY']:
    val = os.environ.get(key)
    print(f"{key}: {'SET' if val else 'MANQUANT'}")
```