cat > /home/claude/nemotron/skills/render.md << 'SKILL_EOF'
# SKILL: Render — Déploiement et Production

## Quand utiliser cette skill
Déploiement sur Render, configuration de services web, variables d'env, logs, build.

## Protocole
1. Vérifier que le `Start Command` utilise bien `process.env.PORT`
2. S'assurer qu'un endpoint `/health` existe
3. Tester localement avec `PORT=X NODE_ENV=production` avant de push

---

## Checklist déploiement

```
□ Procfile ou Start Command configuré
□ PORT utilisé depuis process.env.PORT (jamais hardcodé)
□ Health check endpoint /health qui retourne 200
□ Variables d'env configurées dans le dashboard (pas dans .env commité)
□ DATABASE_URL avec sslmode=require (PostgreSQL)
□ postgres:// remplacé par postgresql:// (Python/SQLAlchemy)
□ Build Command correct (npm install / pip install -r requirements.txt)
□ .gitignore inclut node_modules/, .env, __pycache__/
```

## Procfile — configurations courantes

```
# Node.js Express
web: node server.js

# Python Flask avec Gunicorn
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120

# Python Flask avec Gunicorn + streaming (pour agents)
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --worker-class gevent --timeout 300

# Node.js avec npm start
web: npm start
```

## Variables d'environnement Render

```bash
# Dans le dashboard Render → Environment → Add Environment Variable
# NE JAMAIS commiter ces valeurs

DATABASE_URL          # postgresql://user:pass@host/db?sslmode=require
SECRET_KEY            # générer avec: python3 -c "import secrets; print(secrets.token_hex(32))"
OPENROUTER_API_KEY    # clé OpenRouter
NODE_ENV              # production
PORT                  # injecté automatiquement par Render (ne pas définir)
RENDER_DEPLOY_HOOK    # URL de déclenchement de déploiement (pour CI/CD)
```

## Serveur Node.js compatible Render

```javascript
// server.js — pattern Render-ready
import express from 'express'
const app = express()

// OBLIGATOIRE: utiliser process.env.PORT
const PORT = process.env.PORT || 3000

// Health check Render
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok', timestamp: new Date().toISOString() })
})

// Gérer le SIGTERM proprement (Render envoie SIGTERM avant d'arrêter)
process.on('SIGTERM', () => {
  console.log('SIGTERM reçu, arrêt propre...')
  server.close(() => process.exit(0))
})

const server = app.listen(PORT, '0.0.0.0', () => {
  console.log(`Serveur démarré sur port ${PORT}`)
})
```

## Serveur Flask compatible Render

```python
# wsgi.py
from app import create_app

app = create_app()

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
```

## Logs Render

```bash
# Dans le dashboard → Logs
# Filtrer par niveau: error, warning, info

# Bonnes pratiques de logging pour Render
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Utiliser print() fonctionne aussi (Render capture stdout)
print(f"[INFO] Serveur démarré sur port {PORT}", flush=True)
```

## Render PostgreSQL vs Neon

```
Render PostgreSQL Free:
- Expire après 90 jours
- 1GB stockage
- Accès uniquement depuis les services Render du même compte
- URL: postgres://user:pass@host/db

Neon (recommandé pour persistance):
- Pas d'expiration
- 500MB free
- Accessible de partout (Termux, Render, CI)
- URL: postgresql://user:pass@host/db?sslmode=require
- Branching (dev/prod séparés)
```

## Éviter le spin down (free tier)

```bash
# Le free tier "dort" après 15min sans requête → premier wake-up ~30s

# Solution 1: Service de ping externe (cron-job.org, uptimerobot.com)
# URL à pinger: https://mon-service.onrender.com/health
# Intervalle: toutes les 10 minutes

# Solution 2: GitHub Actions
# .github/workflows/keepalive.yml
name: Keep Alive
on:
  schedule:
    - cron: '*/10 * * * *'  # toutes les 10min
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: curl -f ${{ secrets.APP_URL }}/health
```

## Deploy hook — déclencher depuis CI/CD

```bash
# Dans le dashboard Render → Settings → Deploy Hooks → Create

# Déclencher manuellement
curl -X POST "https://api.render.com/deploy/srv-xxxxx?key=yyyyyyy"

# Dans GitHub Actions
- name: Deploy to Render
  run: curl -X POST "${{ secrets.RENDER_DEPLOY_HOOK }}"
```

## Erreurs courantes Render

| Erreur | Cause | Fix |
|--------|-------|-----|
| `R10 Boot timeout` | Serveur démarre pas en 60s | Vérifier PORT + logs de démarrage |
| `Build failed` | Dépendance manquante | Vérifier Build Command |
| `H12 Request timeout` | Requête > 30s | Streaming ou réduire le temps de traitement |
| `Cannot connect to DB` | SSL manquant | `sslmode=require` ou `rejectUnauthorized: false` |
| `postgres:// invalid` | SQLAlchemy | Remplacer par `postgresql://` |
| `Module not found` | npm install pas lancé | Vérifier Build Command |
| `gunicorn not found` | Pas dans requirements | Ajouter `gunicorn` dans requirements.txt |
SKILL_EOF
echo "OK render"