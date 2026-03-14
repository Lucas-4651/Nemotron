
# SKILL: Node.js / Express / npm

## Protocole obligatoire
1. `view_file` sur chaque fichier à modifier AVANT tout changement
2. `list_directory` pour comprendre la structure complète
3. `view_file package.json` pour connaître les dépendances disponibles
4. `str_replace` pour les modifications ciblées, `write_file` seulement pour les nouveaux fichiers
5. `run_node` pour valider avant de déclarer terminé

---

## Serveur Express production-ready

```javascript
// server.js
import express from 'express'
import 'dotenv/config'

const app = express()
const PORT = process.env.PORT || 3000

app.use(express.json({ limit: '10mb' }))
app.use(express.urlencoded({ extended: true }))

// CORS
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', process.env.ALLOWED_ORIGIN || '*')
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
  if (req.method === 'OPTIONS') return res.sendStatus(200)
  next()
})

// Routes
import apiRouter from './routes/api.js'
app.use('/api', apiRouter)

// Health check (obligatoire pour Render)
app.get('/health', (req, res) => res.json({ status: 'ok', uptime: process.uptime() }))

// Gestion d'erreurs centralisée
app.use((err, req, res, next) => {
  console.error(err.stack)
  res.status(err.status || 500).json({
    error: process.env.NODE_ENV === 'production' ? 'Erreur serveur' : err.message
  })
})

app.listen(PORT, () => console.log(`Serveur sur port ${PORT}`))
export default app
```

## Connexion PostgreSQL (Neon / Render)

```javascript
// db/pool.js
import pg from 'pg'
const { Pool } = pg

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false,
  max: 10,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
})

pool.on('error', (err) => console.error('Pool error:', err))

export async function query(text, params) {
  const start = Date.now()
  try {
    const res = await pool.query(text, params)
    if (Date.now() - start > 1000) console.warn('Requete lente:', text)
    return res
  } catch (err) {
    console.error('DB error:', err.message)
    throw err
  }
}

export default pool
```

## fetchWithRetry — APIs externes

```javascript
// utils/fetch.js
export async function fetchWithRetry(url, options = {}, maxRetries = 3) {
  let lastError
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), options.timeout || 30000)
      const res = await fetch(url, { ...options, signal: controller.signal })
      clearTimeout(timeout)
      if (res.status === 429) {
        await new Promise(r => setTimeout(r, Math.pow(2, attempt) * 1000))
        continue
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res
    } catch (err) {
      lastError = err
      if (attempt < maxRetries) await new Promise(r => setTimeout(r, 1000 * attempt))
    }
  }
  throw lastError
}
```

## Config avec validation au démarrage

```javascript
// config.js
const required = ['DATABASE_URL', 'SECRET_KEY']
const missing = required.filter(k => !process.env[k])
if (missing.length) { console.error('Variables manquantes:', missing); process.exit(1) }

export const config = {
  port: parseInt(process.env.PORT) || 3000,
  dbUrl: process.env.DATABASE_URL,
  isProduction: process.env.NODE_ENV === 'production',
}
```

## package.json — scripts

```json
{
  "type": "module",
  "scripts": {
    "start": "node server.js",
    "dev": "node --watch server.js",
    "check": "node --check server.js"
  },
  "engines": { "node": ">=18" }
}
```

## Structure recommandée

```
projet/
├── server.js
├── config.js
├── db/pool.js
├── routes/
├── services/
├── middleware/
├── utils/fetch.js
├── .env
├── .env.example
└── package.json
```

## Render — déploiement

- Start Command: `node server.js`
- Variables d'env: dashboard Render uniquement (pas de .env en prod)
- Health check path: `/health`
- `PORT` est injecté automatiquement — ne jamais hardcoder
- Free tier spin down apres 15min → prévoir un cron de ping externe
- Build Command: `npm install` (pas npm ci si pas de package-lock)

## Termux / Proot

```bash
pkg install nodejs          # Termux natif
apt install nodejs npm -y   # Proot Debian
node --max-old-space-size=256 server.js  # si mémoire limitée
node --check server.js      # vérifier syntaxe
fuser -k 3000/tcp           # tuer process sur port 3000
```

## Erreurs courantes

- `Cannot find module` → `npm install` + vérifier chemin relatif
- `EADDRINUSE` → `fuser -k PORT/tcp`
- `ERR_REQUIRE_ESM` → ajouter `"type":"module"` dans package.json
- `ssl required` (Neon) → `ssl: { rejectUnauthorized: false }`
- `SIGTERM` sur Render → vérifier que app écoute sur `process.env.PORT`
- `R10 Boot timeout` (Render) → serveur doit démarrer en moins de 60s
