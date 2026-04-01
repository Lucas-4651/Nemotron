#!/bin/bash
# ─────────────────────────────────────────────────────
#  start.sh — Démarrage Nemotron (Termux / Proot Debian)
# ─────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Couleurs ──────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR]${NC}   $*"; exit 1; }

# ── Banner ────────────────────────────────────────────
echo -e "${CYAN}"
echo "  ███╗   ██╗███████╗███╗   ███╗ ██████╗ ████████╗██████╗  ██████╗ ███╗   ██╗"
echo "  ████╗  ██║██╔════╝████╗ ████║██╔═══██╗╚══██╔══╝██╔══██╗██╔═══██╗████╗  ██║"
echo "  ██╔██╗ ██║█████╗  ██╔████╔██║██║   ██║   ██║   ██████╔╝██║   ██║██╔██╗ ██║"
echo "  ██║╚██╗██║██╔══╝  ██║╚██╔╝██║██║   ██║   ██║   ██╔══██╗██║   ██║██║╚██╗██║"
echo "  ██║ ╚████║███████╗██║ ╚═╝ ██║╚██████╔╝   ██║   ██║  ██║╚██████╔╝██║ ╚████║"
echo "  ╚═╝  ╚═══╝╚══════╝╚═╝     ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝"
echo -e "  Dev Agent · Lucas46 Tech Studio${NC}"
echo ""

# ── Vérification Python ───────────────────────────────
command -v python3 >/dev/null 2>&1 || error "Python3 requis. Dans Proot: apt install python3"
PYTHON_VERSION=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
info "Python $PYTHON_VERSION détecté"

# ── Chargement .env ───────────────────────────────────
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    success ".env chargé"
else
    warn "Pas de .env — copier .env.example → .env et remplir les valeurs"
    warn "  cp .env.example .env && nano .env"
fi

# ── Vérification clé API ──────────────────────────────
if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    warn "OPENROUTER_API_KEY non définie — tu pourras la saisir dans l'interface"
else
    success "Clé API OpenRouter présente"
fi

# ── Répertoires ───────────────────────────────────────
mkdir -p workspaces/default logs
success "Répertoires vérifiés"

# ── Venv ──────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    info "Création du virtualenv…"
    python3 -m venv .venv
    success "Virtualenv créé"
fi

# Activation
source .venv/bin/activate
success "Virtualenv activé"

# ── Dépendances ───────────────────────────────────────
info "Vérification des dépendances…"
pip install -r requirements.txt -q --disable-pip-version-check
success "Dépendances OK"

# ── Port ──────────────────────────────────────────────
PORT="${PORT:-5000}"

# ── Démarrage ─────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Serveur démarré → http://localhost:${PORT}${NC}"
echo -e "${GREEN}  Mot de passe : ${APP_PASSWORD:-devagent}${NC}"
echo -e "${GREEN}  Ctrl+C pour arrêter${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "${FLASK_DEBUG:-false}" = "true" ]; then
    warn "Mode DEBUG activé — dev seulement"
    python3 -m flask --app wsgi:app run --host 0.0.0.0 --port "$PORT" --debug
else
    exec gunicorn --timeout 300 --workers 2 --bind "0.0.0.0:$PORT" \
         --access-logfile logs/access.log \
         --error-logfile logs/error.log \
         --log-level info \
         wsgi:app
fi
