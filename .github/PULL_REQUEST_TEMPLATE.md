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

Només les declaracions que el CI no pot verificar (la resta ja les força):

- [ ] He llegit les `docs/policies/` rellevants per al canvi
      (`conventions.md`, `identities.md`, `sprint-process.md`,
      `docs-maintenance.md`, `post-mortems.md`).
- [ ] Si el canvi és una decisió arquitectònica (criteris a
      `docs/policies/sprint-process.md`), he creat un ADR a
      `docs/decisions/`.
- [ ] Les captures/screenshots a la descripció són reals o estan
      etiquetades `EXAMPLE` / `MOCK`.

## Override docs-coherence (excepcional)

Si `docs-coherence` falla perquè el PR toca un subsistema documentat
i de debò no cal actualitzar el doc (refactor intern sense efecte
conceptual, renaming purament mecànic, etc.), afegeix una línia al
cos del PR amb aquest format exacte:

```
docs-reviewed: <doc-path> : <raó>
```

El CI verifica que el doc existeix, que correspon al subsistema
disparat, i que la raó no és buida. Cada override accepta afegeix
la label `docs-review-skipped` per a auditoria. Per defecte,
actualitza el doc; no facis servir l'override com a camí ràpid.

## Related

<!-- Issues, ADRs, post-mortems, commits relacionats:
     - ADR: docs/decisions/NNNN-slug.md
     - Post-mortem: docs/post-mortems/YYYY-MM-DD-slug.md
     - Commit antic: abc1234
-->

🤖 Generated with [Claude Code](https://claude.com/claude-code)
