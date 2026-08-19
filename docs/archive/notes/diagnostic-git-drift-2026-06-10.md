# Diagnòstic git drift prod vs origin/main (2026-06-10)

> NOMÉS-LECTURA. Cap accés al servidor, cap canvi a deploy/secrets. Anàlisi
> dels workflows i de l'historial de runs de GitHub Actions.

## Veredicte: drift BENIGNE — el deploy filtra per camins i salta merges només-docs

El drift `56a43f4` (prod) vs `071451a` (origin/main) **no és un deploy fallit ni
un job no disparat per error**: és el comportament dissenyat del filtre de camins
del workflow de deploy davant d'un merge **només de docs**.

## Evidència

1. **`071451a` és només-docs.** `git diff --name-only 56a43f4 071451a` →
   **un sol fitxer: `docs/platform-overview.md`** (PR #197, "docs(platform-overview):
   refresh…").

2. **`deploy.yml` té `paths-ignore` que cobreix exactament això:**

   ```yaml
   on:
     push:
       branches: [main]
       paths-ignore:
         - 'docs/**'
         - '*.md'
         - 'LICENSE*'
         - '.github/workflows/ci.yml'
         - '.github/workflows/ci-docs.yml'
         - '.github/PULL_REQUEST_TEMPLATE.md'
         - '.markdownlint.json'
   ```

   El push de `071451a` només toca `docs/platform-overview.md` → casa amb
   `docs/**` (i `*.md`) → **el job de deploy NO es dispara**.

3. **Confirmat a l'historial de runs:** `gh run list --workflow=deploy.yml`:
   - Últim run de Deploy = **`56a43f4`** → **success** (2026-06-09 17:30 UTC).
     Aquest és el HEAD que corre a prod.
   - Runs de Deploy amb `headSha=071451a`: **0**. El deploy mai es va encolar
     per a aquell commit.

4. **CI sí que va córrer.** `ci.yml` **no té `paths-ignore`** (corre a cada push
   i PR), així que els tests van cobrir igualment el merge de docs. El comentari
   del propi `deploy.yml` ho diu: *"CI still runs (it has no paths-ignore)"*.

## Per què és benigne

- Prod corre el **codi idèntic** a `origin/main`: l'única diferència entre
  `56a43f4` i `071451a` és un fitxer de documentació que no afecta el servei.
- `bin/tq-deploy` fa `git pull --ff-only` **només quan el job s'executa**. Com
  que el merge de docs no va disparar deploy, l'arbre de prod es va quedar a
  `56a43f4` a propòsit. **No hi ha res trencat ni pendent d'aplicar.**
- **El drift s'auto-cura sol** al pròxim push que toqui codi (no-docs): aquell
  deploy farà `git pull --ff-only` i avançarà l'arbre de prod fins a l'`origin/main`
  d'aquell moment, passant per `071451a` pel camí.

## Matís operatiu (no és una incidència)

La comprovació horària `tq-health` de git-drift (CLAUDE.md §11) pot marcar
`HEAD != origin/main` durant aquesta finestra. En el cas d'un merge **només-docs**
això és un transitori esperat, no una desviació de codi: el deploy va decidir
**correctament** no executar-se. Si es volgués eliminar fins i tot el soroll de
l'alerta, una opció (decisió teua, no aplicada) seria que el git-drift check
ignorés diferències que només toquen camins de `paths-ignore`.

**Conclusió:** ni deploy fallit ni job perdut. El filtre de camins va saltar el
merge només-docs de PR #197, deixant prod a `56a43f4` (l'últim deploy de codi,
exitós) mentre `origin/main` és `071451a`. Drift esperat i benigne.
