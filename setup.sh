#!/bin/bash
# ─────────────────────────────────────────────────────
#  setup.sh — Installation initiale (Proot Debian)
#  Usage: bash setup.sh
# ─────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }

info "=== Setup Nemotron ==="

# ── Détection environnement ──────────────────────────
if [ -f /data/data/com.termux/files/usr/bin/pkg 2>/dev/null ]; then
    ENV_TYPE="termux"
else
    ENV_TYPE="debian"
fi
info "Environnement détecté : $ENV_TYPE"

# ── Packages système ──────────────────────────────────
if [ "$ENV_TYPE" = "termux" ]; then
    info "Mise à jour Termux…"
    pkg update -y && pkg upgrade -y
    pkg install -y python nodejs git curl wget zip unzip
else
    info "Mise à jour Proot Debian…"
    apt update -qq && apt upgrade -y -qq
    apt install -y -qq python3 python3-pip python3-venv \
        git curl wget zip unzip build-essential 2>/dev/null || true
fi
success "Packages système installés"

# ── .env ─────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn ".env créé depuis .env.example — pense à renseigner OPENROUTER_API_KEY"
    warn "  nano .env"
else
    success ".env déjà présent"
fi

# ── Venv ─────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    info "Création virtualenv Python…"
    python3 -m venv .venv
    success "Virtualenv créé"
fi

source .venv/bin/activate

info "Installation des dépendances Python…"
pip install --upgrade pip -q
pip install -r requirements.txt -q
success "Dépendances installées"

# ── Répertoires ───────────────────────────────────────
mkdir -p workspaces/default logs
success "Répertoires créés"

# ── Permissions ───────────────────────────────────────
chmod +x start.sh setup.sh
success "Permissions OK"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup terminé !${NC}"
echo -e "${GREEN}  Lance : bash start.sh${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
