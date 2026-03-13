
# SKILL: Git / GitHub / GitHub Actions / Render Deploy

## Protocole
1. `execute_command` avec `git status` avant tout commit
2. Toujours vérifier ce qu'on commite avec `git diff --staged`
3. Messages de commit descriptifs (type + scope + description)
4. Ne jamais forcer un push sur main sans vérification

---

## Workflow quotidien

```bash
# Voir l'état
git status
git diff                  # changements non-stagés
git diff --staged         # changements stagés

# Commiter proprement
git add fichier.py        # ajouter un fichier précis
git add -p                # ajouter par morceaux (review interactive)
git commit -m "fix(api): corriger timeout sur fetchWithRetry"

# Types de commit: feat fix docs refactor test chore style perf
# Exemples:
git commit -m "feat(agent): ajouter skill_loader avec détection automatique"
git commit -m "fix(db): corriger pool ssl pour Neon en production"
git commit -m "refactor(tools): extraire web_tools dans module séparé"

# Push
git push origin main
```

## Branches

```bash
# Créer et switcher
git checkout -b feature/nom-feature

# Voir les branches
git branch -a

# Merger dans main
git checkout main
git merge --no-ff feature/nom-feature -m "merge: feature/nom-feature"

# Supprimer après merge
git branch -d feature/nom-feature
git push origin --delete feature/nom-feature
```

## Annuler des erreurs

```bash
# Annuler le dernier commit (garder les changements)
git reset --soft HEAD~1

# Annuler les changements d'un fichier (non commité)
git checkout -- fichier.py

# Annuler tous les changements non-commités (DANGER)
git checkout -- .

# Voir ce qui a changé dans le dernier commit
git show --stat HEAD

# Retrouver un commit perdu
git reflog
git checkout <hash>
```

## .gitignore essentiel

```
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/

# Node.js
node_modules/
dist/
build/

# Environnement (JAMAIS commiter)
.env
.env.local
.env.production

# DB locales
*.db
*.sqlite
*.sqlite3
instance/

# Logs et tmp
*.log
*.tmp
.DS_Store
```

## GitHub Actions — CI/CD Python (Render)

```yaml
# .github/workflows/deploy.yml
name: Deploy to Render

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -v
        env:
          DATABASE_URL: ${{ secrets.TEST_DATABASE_URL }}

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Render deploy
        run: curl -X POST "${{ secrets.RENDER_DEPLOY_HOOK }}"
```

## GitHub Actions — CI/CD Node.js (Render)

```yaml
# .github/workflows/deploy.yml
name: Deploy Node to Render

on:
  push:
    branches: [main]

jobs:
  test-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci
      - run: node --check server.js
      - name: Deploy to Render
        if: success()
        run: curl -X POST "${{ secrets.RENDER_DEPLOY_HOOK }}"
```

## GitHub Actions — Build APK Android

```yaml
# .github/workflows/build-apk.yml
name: Build APK

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { java-version: '17', distribution: 'temurin' }
      - name: Setup Android SDK
        uses: android-actions/setup-android@v3
      - name: Build APK
        run: |
          chmod +x gradlew
          ./gradlew assembleRelease
      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: app-release
          path: app/build/outputs/apk/release/*.apk
```

## Render — déploiement depuis GitHub

1. Connecter le repo GitHub dans le dashboard Render
2. Branch: `main`
3. Auto-deploy: ON (déclenché par chaque push sur main)
4. Build Command: `npm install` ou `pip install -r requirements.txt`
5. Start Command: `node server.js` ou `gunicorn wsgi:app`
6. Récupérer le Deploy Hook URL → mettre dans GitHub Secrets comme `RENDER_DEPLOY_HOOK`

## Secrets GitHub

```bash
# Ajouter via GitHub CLI
gh secret set RENDER_DEPLOY_HOOK --body "https://api.render.com/deploy/xxx"
gh secret set DATABASE_URL --body "postgresql://..."

# Ou via l'interface: Settings → Secrets → Actions
```

## Termux — git config initiale

```bash
git config --global user.email "ton@email.com"
git config --global user.name "Lucas46"

# Authentification GitHub via token (pas de mot de passe)
git remote set-url origin https://TOKEN@github.com/user/repo.git

# Ou SSH (recommandé)
ssh-keygen -t ed25519 -C "ton@email.com"
cat ~/.ssh/id_ed25519.pub  # copier dans GitHub Settings → SSH Keys
```

## Erreurs courantes

- `fatal: not a git repository` → `git init` ou être dans le bon dossier
- `rejected: non-fast-forward` → `git pull --rebase` avant de push
- `Permission denied (publickey)` → clé SSH non ajoutée à GitHub
- `nothing to commit` → changements pas stagés, faire `git add`
- `conflict` lors d'un merge → éditer les fichiers avec `<<<<`, faire `git add`, puis `git commit`
