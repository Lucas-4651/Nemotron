
# SKILL: Termux / Proot Debian / Bash / Linux

## Deux environnements supportés

| | Termux natif | Proot Debian | Render (prod) |
|--|--|--|--|
| Package manager | `pkg` | `apt` | `apt` (Ubuntu) |
| pip | `pip install X` | `pip install X --break-system-packages` | `pip install X` |
| Root | non | simulé | non (container) |
| Python | `pkg install python` | `apt install python3` | pré-installé |
| Chemins | `/data/data/com.termux/files` | `/root` | `/home/user` |

---

## Installation packages

```bash
# === Termux natif ===
pkg update && pkg upgrade -y
pkg install python nodejs git curl wget zip unzip openssh vim

# === Proot Debian ===
apt update && apt upgrade -y
apt install -y python3 python3-pip nodejs npm git curl wget \
               zip unzip build-essential libssl-dev

# pip dans Proot Debian (OBLIGATOIRE --break-system-packages)
pip install flask requests --break-system-packages
pip install -r requirements.txt --break-system-packages

# Venv (recommandé pour les projets)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # pas besoin de --break-system-packages dans venv
```

## Scripts Bash robustes

```bash
#!/bin/bash
set -euo pipefail
# set -e  → arrêter sur erreur
# set -u  → erreur si variable non définie
# set -o pipefail → erreur si une commande dans un pipe échoue

# Variables avec valeur par défaut
PORT=${PORT:-3000}
ENV=${NODE_ENV:-development}
WORKERS=${WORKERS:-2}

# Vérifier qu'une commande existe
command -v node >/dev/null 2>&1 || { echo "Node.js requis. pkg install nodejs"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Python3 requis"; exit 1; }

# Créer des dossiers
mkdir -p ./logs ./workspace ./tmp

# Charger les variables d'env
[ -f .env ] && export $(grep -v '^#' .env | xargs)

echo "Démarrage: PORT=$PORT ENV=$ENV"
```

## Gestion des processus

```bash
# Lancer en arrière-plan
node server.js > logs/server.log 2>&1 &
echo $! > .pid
echo "PID: $(cat .pid)"

# Arrêter proprement
kill $(cat .pid) 2>/dev/null && rm .pid || echo "Process déjà arrêté"

# Tuer par port
fuser -k 3000/tcp      # Linux/Proot
lsof -ti:3000 | xargs kill -9  # alternative

# Voir les process actifs
ps aux | grep node
ss -tlnp  # ports en écoute
```

## Variables d'environnement

```bash
# Fichier .env
cat > .env << 'EOF'
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
SECRET_KEY=changeme_en_production
PORT=3000
NODE_ENV=development
EOF

# Charger dans le shell courant
export $(grep -v '^#' .env | xargs)

# Vérifier
echo $DATABASE_URL
env | grep PORT

# .env.example (à commiter, sans valeurs sensibles)
cat > .env.example << 'EOF'
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
SECRET_KEY=your_secret_key_here
PORT=3000
NODE_ENV=development
EOF
```

## Fichiers et permissions

```bash
# Rendre exécutable
chmod +x script.sh
chmod +x gradlew

# Permissions courantes
chmod 755 dossier/     # rwxr-xr-x
chmod 644 fichier.txt  # rw-r--r--
chmod 600 .env         # rw------- (fichiers secrets)

# Voir les permissions
ls -la

# Propriétaire (dans Proot)
chown user:user fichier
```

## Manipulation de fichiers utiles

```bash
# Chercher du texte dans des fichiers
grep -rn "DATABASE_URL" .
grep -rn "def fetch" --include="*.py" .

# Remplacer dans un fichier
sed -i 's/ancien_texte/nouveau_texte/g' fichier.py

# Voir les dernières lignes d'un log
tail -f logs/server.log
tail -100 logs/error.log

# Comparer deux fichiers
diff fichier1.py fichier2.py

# Archiver et compresser
tar -czf backup.tar.gz dossier/
tar -xzf backup.tar.gz

# Espace disque
df -h
du -sh ./node_modules
```

## tmux — sessions persistantes (Termux)

```bash
# Installer
pkg install tmux

# Nouvelle session nommée
tmux new -s monserveur

# Dans la session: lancer le serveur
node server.js

# Détacher (garder en arrière-plan): Ctrl+B puis D

# Rattacher plus tard
tmux attach -t monserveur

# Lister les sessions
tmux ls

# Tuer une session
tmux kill-session -t monserveur
```

## Cron — tâches planifiées (Termux)

```bash
# Installer cron
pkg install cronie

# Éditer le crontab
crontab -e

# Exemples:
# Toutes les 5 minutes
*/5 * * * * /data/data/com.termux/files/usr/bin/node /root/projet/cron.js

# Tous les jours à 3h
0 3 * * * /usr/bin/python3 /root/projet/daily.py >> /root/logs/daily.log 2>&1

# Démarrer le service cron
crond
```

## Réseau et ports

```bash
# Voir les ports en écoute
ss -tlnp
netstat -tlnp

# Tester une connexion
curl -I https://mon-api.com
curl -X POST https://api.com/endpoint \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'

# Tester localement
curl http://localhost:3000/health
curl http://localhost:5000/api/status

# Ping
ping -c 3 google.com
```

## Render vs Termux — différences clés

```bash
# Sur Render:
# - Pas de .env → variables dans le dashboard
# - PORT est injecté automatiquement
# - /tmp disponible mais effacé entre redémarrages
# - Pas de cron natif → utiliser une tâche GitHub Actions ou service externe
# - Free tier: spin down après 15min inactivité

# Sur Termux:
# - .env chargé manuellement
# - PORT libre à choisir
# - Fichiers persistants dans ~/
# - cron disponible avec cronie
# - Toujours actif tant que Termux tourne
```

## Erreurs courantes

- `Permission denied` → `chmod +x script.sh`
- `command not found` → package non installé, vérifier PATH
- `No space left on device` → `pkg clean` ou `apt clean && apt autoclean`
- `bash: .env: No such file` → créer le fichier ou ignorer l'erreur avec `[ -f .env ] && ...`
- `bind: Address already in use` → `fuser -k PORT/tcp`
- `pip: externally-managed-environment` → ajouter `--break-system-packages`
