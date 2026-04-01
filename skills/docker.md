# SKILL: Docker & Docker Compose

## Protocole obligatoire
1. `find_files("Dockerfile*")` — vérifier si un Dockerfile existe
2. `find_files("docker-compose*")` — vérifier la composition
3. `read_file("Dockerfile")` avant toute modification
4. Toujours tester le build localement avant de pusher

---

## Dockerfile — patterns recommandés

```dockerfile
# Python Flask — multi-stage léger
FROM python:3.11-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS prod
COPY . .
EXPOSE 5000
ENV FLASK_ENV=production
CMD ["gunicorn", "--timeout", "300", "--workers", "1",
     "--worker-class", "gevent", "--bind", "0.0.0.0:5000", "wsgi:app"]

# Node.js Express
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM deps AS prod
COPY . .
EXPOSE 3000
ENV NODE_ENV=production
CMD ["node", "server.js"]
```

## docker-compose.yml — stack web complète

```yaml
version: '3.9'
services:
  app:
    build: .
    ports: ["5000:5000"]
    environment:
      - DATABASE_URL=postgresql://user:pass@db/mydb
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    volumes:
      - ./workspaces:/app/workspaces
      - ./logs:/app/logs

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: mydb
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d mydb"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

## Commandes essentielles

```bash
# Build & run
docker build -t monapp .
docker run -p 5000:5000 --env-file .env monapp

# Compose
docker-compose up -d          # démarrer en arrière-plan
docker-compose logs -f app    # suivre les logs
docker-compose down -v        # arrêter + supprimer volumes
docker-compose restart app    # redémarrer un service

# Debug
docker exec -it <container> bash    # shell interactif
docker stats                         # CPU/RAM live
docker system prune -f               # nettoyer images orphelines
docker logs <container> --tail 50    # dernières lignes

# Image
docker images                        # lister images
docker rmi <image>                   # supprimer image
docker pull <image>                  # télécharger image
```

## .dockerignore — toujours créer

```
.git
.venv
venv
__pycache__
*.pyc
node_modules
.env
logs/
*.db
.DS_Store
```

## Erreurs courantes

| Erreur | Cause | Fix |
|--------|-------|-----|
| `port already in use` | Port occupé | `lsof -i :5000` puis `kill -9 <pid>` |
| `network not found` | Compose down incomplet | `docker network prune` |
| `permission denied /var/run/docker.sock` | User pas dans groupe docker | `sudo usermod -aG docker $USER` |
| `no space left` | Images/layers accumulés | `docker system prune -af` |
| `cannot connect to db` | DB pas encore prête | Utiliser `depends_on` + `healthcheck` |
| Conteneur quitte immédiatement | Process en foreground manquant | CMD doit lancer en foreground (pas daemon) |

## Proot/Termux

```bash
# Docker ne tourne pas nativement sous Termux/Proot
# Alternatives :
# 1. Podman (rootless) : pkg install podman
# 2. Utiliser l'hôte Docker via socket monté
# 3. Déployer sur Render/Railway à la place
```
