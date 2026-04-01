# ⬡ Nemotron — Dev Agent

> Assistant IA de développement logiciel, conçu pour tourner dans **Termux / Proot Debian** et se déployer sur **Render**.  
> Par **Lucas46 Tech Studio**

---

## ✨ Fonctionnalités

| Catégorie | Détail |
|---|---|
| 🤖 **Multi-modèles** | OpenRouter — qwen3-coder, GPT-oss-120B, Llama 3.3, Mistral, Nemotron, et +5 fallbacks gratuits |
| 🔧 **Outils intégrés** | Lecture/écriture fichiers, exécution Python/Node, grep, recherche sémantique, fetch URL, DuckDuckGo |
| 💬 **Streaming SSE** | Réponse token par token, affichage en temps réel |
| 📂 **Workspaces** | Multi-workspace avec isolation sécurisée (path traversal proof) |
| 🧠 **Mémoire** | Mémoire persistante clé/valeur en base de données |
| 🔍 **Recherche sémantique** | Indexation ChromaDB des fichiers du workspace |
| 📎 **Upload de fichiers** | Joindre `.py .js .json .md .sql …` directement dans le chat |
| 🔒 **Sécurité** | Authentification mot de passe, rate-limiting, sandbox workspace, whitelist commandes |
| 📊 **Métriques** | Tokens, coût, cache hits, durée par session |
| ⚡ **Cache outils** | SQLite TTL-based pour éviter les appels redondants |

---

## 🚀 Démarrage rapide (Termux / Proot Debian)

```bash
# 1. Cloner ou décompresser le projet
cd ~
git clone <ton-repo> nemotron && cd nemotron
# OU: unzip Nemotron.zip && cd nemotron_project

# 2. Installation (Proot Debian)
bash setup.sh

# 3. Configurer l'API key
nano .env
# → renseigner OPENROUTER_API_KEY=sk-or-v1-...

# 4. Lancer
bash start.sh
# → http://localhost:5000
```

---

## ⚙️ Variables d'environnement

Copier `.env.example` → `.env` :

```bash
cp .env.example .env
```

| Variable | Description | Défaut |
|---|---|---|
| `OPENROUTER_API_KEY` | **Obligatoire** — clé OpenRouter | — |
| `APP_PASSWORD` | Mot de passe interface web | `devagent` |
| `SECRET_KEY` | Clé sessions Flask **(changer en prod!)** | clé dev |
| `DATABASE_URL` | SQLite local ou PostgreSQL | `sqlite:///devagent.db` |
| `WORKSPACE_ROOT` | Dossier des workspaces | `./workspaces` |
| `MAX_STEPS` | Étapes max agent par requête | `15` |
| `FLASK_DEBUG` | Mode debug **(false en prod!)** | `false` |

---

## 🌐 Déploiement sur Render

1. Pusher sur GitHub
2. Créer un **Web Service** sur [render.com](https://render.com)
3. Configurer les variables d'env dans le dashboard Render
4. Le `render.yaml` gère le reste :

```yaml
buildCommand: pip install -r requirements.txt
startCommand: gunicorn --timeout 300 --workers 2 wsgi:app
```

---

## 🗂️ Structure du projet

```
nemotron/
├── config.py              # Configuration centrale
├── wsgi.py                # Point d'entrée Gunicorn
├── requirements.txt       # Dépendances Python
├── start.sh               # Démarrage Termux/Proot
├── setup.sh               # Installation initiale
├── .env                   # Variables locales (ne pas commiter !)
├── .env.example           # Template .env
├── render.yaml            # Config déploiement Render
├── Procfile               # Process Gunicorn
│
├── core/
│   ├── agent.py           # Agent IA principal (stream_task)
│   ├── llm_client.py      # Client OpenRouter + fallbacks
│   ├── metrics.py         # Métriques session
│   ├── skill_loader.py    # Chargement dynamique des skills
│   ├── summarizer.py      # Résumé historique LLM
│   └── tool_cache.py      # Cache SQLite des outils
│
├── tools/
│   ├── __init__.py        # ToolManager (registry)
│   ├── file_tools.py      # read/write/list/delete fichiers
│   ├── edit_tools.py      # str_replace, view_file
│   ├── code_tools.py      # run_python, run_node, linter, tests
│   ├── command_tools.py   # execute_command (whitelist)
│   ├── search_tools.py    # grep, semantic_search
│   └── web_tools.py       # web_search, fetch_url
│
├── web/
│   ├── app.py             # Factory Flask, routes auth
│   ├── auth.py            # Décorateurs login_required
│   ├── models.py          # Conversation, Memory (SQLAlchemy)
│   ├── routes_api.py      # API REST (/api/*)
│   ├── routes_ui.py       # Routes UI (/)
│   └── limiter.py         # Rate-limiter Flask-Limiter
│
├── workspace/
│   ├── manager.py         # Gestion multi-workspace
│   ├── indexer.py         # Indexation ChromaDB
│   └── watcher.py         # Watchdog changements fichiers
│
├── skills/                # Contextes injectés dynamiquement
│   ├── python.md          # Flask, FastAPI, pip…
│   ├── nodejs.md          # Express, npm, ESM…
│   ├── sql.md             # PostgreSQL, migrations…
│   ├── debug.md           # Débogage, tracebacks…
│   ├── api.md             # REST, OpenRouter, streaming…
│   ├── termux.md          # Termux, Proot, bash…
│   └── git.md             # Git, GitHub Actions, Render…
│
├── templates/
│   ├── index.html         # Interface principale
│   └── login.html         # Page de connexion
│
└── static/
    ├── style.css          # Design sombre épuré
    └── script.js          # Frontend (streaming, markdown, modals)
```

---

## 🧰 Outils disponibles pour l'agent

| Outil | Description |
|---|---|
| `read_file` | Lire un fichier du workspace |
| `write_file` | Créer/écraser un fichier |
| `append_file` | Ajouter à la fin d'un fichier |
| `str_replace` | Remplacer une portion unique (safe) |
| `view_file` | Afficher avec numéros de ligne |
| `list_directory` | Lister un dossier |
| `delete_path` | Supprimer fichier/dossier |
| `get_file_info` | Taille, permissions, date |
| `run_python` | Exécuter du code Python |
| `run_node` | Exécuter du JavaScript |
| `run_linter` | Pylint / ESLint |
| `run_tests` | Pytest / Jest |
| `build_project` | npm run build, make, etc. |
| `get_dependencies` | Lire package.json / requirements.txt |
| `execute_command` | Shell whitelist (ls, git, curl…) |
| `grep_files` | Recherche regex dans les fichiers |
| `semantic_search` | Recherche vectorielle ChromaDB |
| `web_search` | DuckDuckGo |
| `fetch_url` | HTTP GET/POST vers une URL |

---

## 🔐 Sécurité

- **Workspace sandbox** : `path traversal` bloqué via `os.path.realpath()` + vérification de frontière
- **Symlinks** : résolus avant vérification (pas de bypass via lien symbolique)
- **Whitelist commandes** : `execute_command` n'autorise qu'une liste explicite (pas de `rm`)
- **Rate-limiting** : 200 req/min global, 30 req/min sur `/api/chat`
- **Timing attack** : `hmac.compare_digest` pour la vérification du mot de passe
- **Sessions** : `SECRET_KEY` fixe en dev (avertissement log), via env en prod

---

## 📝 Licence

MIT · Lucas46 Tech Studio
