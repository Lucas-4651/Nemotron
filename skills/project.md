# SKILL: Analyse de Gros Projets

## Protocole obligatoire pour tout projet inconnu

```
1. project_map()               # Vue d'ensemble complète avec tailles
2. find_files("*.md")          # README, CHANGELOG, docs
3. read_file("README.md")      # Contexte général
4. get_dependencies()          # Stack technique
5. find_files("*.env.example") # Variables d'env attendues
6. grep_files("def main\|if __name__\|app.listen\|server.listen")  # Points d'entrée
```

## Comprendre l'architecture

```bash
# Identifier les points d'entrée
grep_files("from flask import\|express()\|FastAPI()\|createServer")

# Trouver les routes/endpoints
grep_files("@app.route\|router\.\|app\.get\|app\.post")

# Trouver les modèles de données
grep_files("class.*Model\|db\.Column\|Schema\|interface ")

# Variables d'environnement utilisées
grep_files("os\.environ\|process\.env\|getenv")
```

## Workflow de modification sur gros projet

```
PHASE 1 — Comprendre (NE PAS MODIFIER)
  project_map()           # structure globale
  read_file(README)       # contexte
  view_file(fichier)      # lire avant modifier

PHASE 2 — Localiser
  grep_files(pattern)     # trouver les occurrences
  semantic_search(query)  # recherche par sens

PHASE 3 — Modifier
  str_replace             # modification ciblée et unique
  multi_str_replace       # plusieurs remplacements en un appel

PHASE 4 — Valider
  run_python / run_node   # tester
  run_linter              # vérifier la qualité
  run_tests               # suite de tests
```

## Refactorisation

```python
# Workflow renommage de fonction/variable
# 1. Vérifier toutes les occurrences
grep_files("ancien_nom")

# 2. Remplacer partout avec multi_str_replace sur chaque fichier
multi_str_replace(path="file.py", replacements=[
    {"old_str": "ancien_nom", "new_str": "nouveau_nom", "replace_all": True}
])

# 3. Valider
run_linter(path=".", lang="python")
run_tests()
```

## Gestion de la mémoire sur gros projets

```
# Sauvegarder le contexte projet pour les prochaines sessions
save_memory(key="projet_stack",     value="Flask + PostgreSQL + React")
save_memory(key="projet_entry",     value="wsgi.py → web/app.py")
save_memory(key="projet_structure", value="core/ tools/ web/ templates/")
save_memory(key="projet_conventions", value="snake_case, str_replace préféré")
```

## Analyse de performance

```bash
# Trouver les fichiers volumineux
find_files("*.py")  # puis filtrer par taille via get_file_info

# Identifier les imports circulaires
grep_files("import " , path=".")

# Trouver les TODO/FIXME
grep_files("TODO|FIXME|HACK|XXX|BUG")

# Chercher le code mort
grep_files("def .*:" )  # fonctions définies
grep_files("# noqa\|pass$\|\.\.\.^")  # stubs
```

## Erreurs courantes sur gros projets

| Situation | Solution |
|-----------|---------|
| Fichier trop long (>300L) | view_file avec start_line/end_line |
| Chercher une fonction | grep_files("def nom_fonction") |
| Comprendre un module | view_file → lire les imports + docstrings |
| Modifier sans casser | str_replace sur un contexte unique |
| Renommer partout | multi_str_replace + replace_all:true |
| Ajouter du code | insert_lines à la bonne ligne |
| Réorganiser | move_file pour déplacer des modules |
