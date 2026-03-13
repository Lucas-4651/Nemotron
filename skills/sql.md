
# SKILL: SQL / PostgreSQL / SQLite / Neon

## Protocole obligatoire
- Toujours confirmer les noms exacts des tables et colonnes avant d'écrire une requête
- Pour DROP/TRUNCATE/DELETE sans WHERE → demander confirmation explicite
- Vérifier l'environnement (dev/prod) avant toute opération destructive
- Tester les requêtes sur dev avant de les appliquer en prod

---

## Connexion Neon PostgreSQL (Node.js)

```javascript
// db/pool.js — compatible Neon + tout PostgreSQL
import pg from 'pg'
const { Pool } = pg

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production'
    ? { rejectUnauthorized: false }  // Neon / Render
    : false,                          // local / dev
  max: 5,                 // Neon free tier: max 5 connexions
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
})

export async function query(sql, params = []) {
  const client = await pool.connect()
  try {
    return await client.query(sql, params)
  } finally {
    client.release()  // TOUJOURS libérer le client
  }
}
```

## Connexion PostgreSQL (Python)

```python
# db.py
import psycopg2
from psycopg2.extras import RealDictCursor
import os

def get_conn():
    return psycopg2.connect(
        os.environ['DATABASE_URL'],
        sslmode='require',          # obligatoire pour Neon
        cursor_factory=RealDictCursor  # retourne des dicts
    )

def query(sql, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            if sql.strip().upper().startswith('SELECT'):
                return cur.fetchall()
            conn.commit()
            return cur.rowcount
```

## Patterns SQL robustes

```sql
-- UPSERT (insérer ou mettre à jour)
INSERT INTO predictions (match_id, score, confidence)
VALUES ($1, $2, $3)
ON CONFLICT (match_id)
DO UPDATE SET
  score = EXCLUDED.score,
  confidence = EXCLUDED.confidence,
  updated_at = NOW();

-- Transaction pour opérations multiples
BEGIN;
  UPDATE rounds SET status = 'closed' WHERE id = $1;
  INSERT INTO results (round_id, data) VALUES ($1, $2);
COMMIT;

-- Pagination efficace
SELECT * FROM matches
ORDER BY created_at DESC
LIMIT $1 OFFSET $2;

-- JSON dans PostgreSQL
SELECT data->>'field' as field FROM table;          -- TEXT
SELECT data->'field' as field FROM table;           -- JSON
SELECT * FROM table WHERE data @> '{"key":"val"}';  -- contient

-- Aggregations utiles
SELECT
  COUNT(*) as total,
  AVG(confidence)::numeric(5,2) as avg_conf,
  COUNT(*) FILTER (WHERE result = 'correct') as correct
FROM predictions;
```

## Migrations (pattern manuel sans ORM)

```javascript
// db/migrate.js — système de migration simple
const migrations = [
  {
    version: 1,
    up: `
      CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(120) UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
      );
    `
  },
  {
    version: 2,
    up: `ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user';`
  },
]

async function migrate() {
  await query(`CREATE TABLE IF NOT EXISTS schema_versions (version INT PRIMARY KEY)`)
  const { rows } = await query(`SELECT MAX(version) as v FROM schema_versions`)
  const current = rows[0].v || 0

  for (const m of migrations) {
    if (m.version > current) {
      console.log(`Migration v${m.version}...`)
      await query(m.up)
      await query(`INSERT INTO schema_versions VALUES ($1)`, [m.version])
      console.log(`v${m.version} OK`)
    }
  }
}

migrate().catch(console.error)
```

## SQLite (dev local)

```python
# db_sqlite.py
import sqlite3
import json

def get_conn(path='./app.db'):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row   # retourne des dicts
    conn.execute('PRAGMA journal_mode=WAL')  # meilleures perf
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

# Utilisation
with get_conn() as conn:
    rows = conn.execute('SELECT * FROM table WHERE id = ?', (id,)).fetchall()
    result = [dict(r) for r in rows]
```

## JSON stocké en TEXT (pattern courant)

```python
# Problème: PostgreSQL retourne les colonnes JSON-en-TEXT comme strings
# Solution: parser après lecture

import json

def parse_json_fields(row, fields):
    """Parse les champs JSON stockés en TEXT."""
    result = dict(row)
    for field in fields:
        if field in result and isinstance(result[field], str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return result

# Exemple
rows = await query('SELECT * FROM learning_states')
for row in rows.rows:
    data = parse_json_fields(row, ['weights', 'history', 'metadata'])
```

## Opérations Neon spécifiques

```bash
# Se connecter en CLI (depuis Termux ou serveur)
psql $DATABASE_URL

# Lister les tables
\dt

# Voir la structure d'une table
\d nom_table

# Exporter une table en CSV
\copy table TO 'export.csv' CSV HEADER;

# TRUNCATE sans reset des IDs
TRUNCATE TABLE learning_states;

# TRUNCATE avec reset des séquences
TRUNCATE TABLE predictions RESTART IDENTITY;
```

## Render — base de données

- Render PostgreSQL: URL dans `DATABASE_URL` env var
- Neon: même chose, `sslmode=require` ou `ssl: {rejectUnauthorized: false}`
- Free tier Neon: max 5 connexions simultanées → utiliser un pool petit
- Render PostgreSQL free: expire après 90 jours → préférer Neon pour persistance

## Erreurs courantes

- `SSL connection required` → ajouter `sslmode=require` ou `ssl: {rejectUnauthorized: false}`
- `too many connections` → réduire `max` dans Pool ou utiliser PgBouncer
- `column does not exist` → PostgreSQL case-sensitive, vérifier les guillemets
- `value too long for varchar` → augmenter la taille ou utiliser TEXT
- `invalid input syntax for integer` → paramètre string reçu, caster avec `::int`
- `FATAL: password authentication failed` → clé expirée sur Neon, regenerer
