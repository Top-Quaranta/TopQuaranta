# scripts/mutacio — verificació per mutació, test a test

Origen: auditoria de tests del 2026-08-18
(`docs/audits/2026-08-18-auditoria-tests.md`). Regla: un test que
sobreviu ha de caure quan es trenca el codi que diu que vigila.

Corre-ho **en un worktree a banda** (muta fitxers de producció
contínuament i els restaura; una mort a mitges deixa un mutant al
disc — el `git checkout -- .` de l'arrencada ho neteja).

```bash
git worktree add --detach ../TopQuaranta-mut HEAD
cd ../TopQuaranta-mut
../TopQuaranta/.venv/bin/python ../TopQuaranta/scripts/mutacio/mut.py \
    social/tests /tmp/mut_social --slow=../TopQuaranta/scripts/mutacio/slow_tests.txt
```

- `mut.py <tests_dir> <out_dir> [--src=a,b] [--budget-runs=N] [--slow=file]`
  — cobertura per context de test → mutants AST per línia → corre només
  els tests que cobreixen la línia. Ix `verified.json`, `unverified.txt`
  i `never_covered.txt`. `--slow` llista els tests que necessiten
  migracions reals (seed de la matriu de distribució); la resta va amb
  `--no-migrations` (~1 s d'arrencada en lloc de 15).
- `mut2.py <out_dir> <tests_file> [--max-sites=N] [--skip-a]` — segona
  passada per als `unverified`: (A) tests sobre bancs de dades
  importats a nivell de mòdul; (B) tests que llegeixen fitxers
  no-Python (esborrat de línies del fitxer que el test obri).
- El que quede després de les dues passades es fa a mà: constraints
  `Meta` (eixamplar `fields`), scripts de shell (`exit 0`, error de
  sintaxi), tests que executen subprocessos.

Ritme orientatiu: ~4-10 s per mutant; una app de 400 tests, ~30 min.
Un mutant que fa un bucle infinit s'aborta als 120 s.
