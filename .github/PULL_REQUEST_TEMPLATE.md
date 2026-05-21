<!-- Pull request template — TopQuaranta -->

## Descripció

<!-- Una explicació curta del canvi i per què. -->

## Tipus

- [ ] Fix
- [ ] Feat
- [ ] Refactor
- [ ] Docs
- [ ] Chore

## Checklist

- [ ] He llegit `docs/policies/` rellevants per al canvi
      (`conventions.md`, `identities.md`, `sprint-process.md`,
      `docs-maintenance.md`, `post-mortems.md`).
- [ ] He actualitzat `docs/architecture/<area>.md` si el canvi
      toca un subsistema documentat — **o justifica per què no
      cal** en una línia aquí sota.
- [ ] Si el canvi és una decisió arquitectònica (criteris a
      `docs/policies/sprint-process.md`), he creat ADR a
      `docs/decisions/`.
- [ ] Si el canvi toca `models.py`, la migració corresponent va
      al mateix PR i `bin/tq-deploy` l'aplicarà abans del reload
      (vegeu `docs/policies/conventions.md` § "Migrations").
- [ ] He afegit `# Spec: docs/<path>.md` als mòduls nous amb
      doc dedicada.
- [ ] Tests verds localment o al servidor (`pytest -q`).
- [ ] Captures/screenshots a la descripció són reals o
      etiquetades `EXAMPLE` / `MOCK`.

<!-- "No cal docs update" justification (if you didn't check the
     box above): -->

## Related

<!-- Issues, ADRs, post-mortems, commits relacionats:
     - ADR: docs/decisions/NNNN-slug.md
     - Post-mortem: docs/post-mortems/YYYY-MM-DD-slug.md
     - Commit antic: abc1234
-->

🤖 Generated with [Claude Code](https://claude.com/claude-code)
