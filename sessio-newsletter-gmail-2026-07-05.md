# Sessió newsletter — compatibilitat Gmail + destí de prova (2026-07-05)

> Nota local de referència (untracked). Font canònica: **PR #312**
> (branca `feat/newsletter-gmail-compat`, CI 12/12 verd,
> **SENSE MERGEJAR** — esperant la teua revisió de render).

## Recon (Fase 1) — el que es va trobar

- **Mida vs límit 102 KB de Gmail: cap risc.** L'esborrany de la
  setmana 2026-06-29 renderitzat complet fa **34,6 KB** (5,5 KB gzip);
  post-refactor ~43 KB. (El HTML no es persisteix: la BD només guarda
  subject + narrative_html.)
- Problemes reals al template (`comptes/templates/comptes/email_newsletter_top.html`):
  classes de layout només al bloc `<style>` (Gmail el pot descartar),
  contenidor `width="640"` fix, fons foscos sense `bgcolor` redundant
  (el dark mode de Gmail invertia les targetes), vores `rgba()`,
  `<a>` embolcallant `<table>` a les targetes territorials/novetats,
  i columnes sense amplada fixa (targetes 4-10 i territorials no
  uniformes — el símptoma que veies).

## Fet (Fases 2-3)

- Template refactoritzat al patró email: hybrid fluid (100% +
  max-width 640 + ghost MSO), estils inline a tot, `bgcolor` redundant,
  `meta color-scheme: dark`, hex sòlids, `table-layout:fixed` amb
  amplades explícites → targetes a amplada completa i uniformes.
  **Zero canvis de contingut/textos/UTM.**
- **`ConfiguracioGlobal.newsletter_desti_prova`** (migració ranking
  0034, buit per defecte): si té valor, l'esborrany setmanal s'envia
  TAMBÉ a eixa adreça. Mai a subscriptors (fixat amb tests; revisat el
  diff: només toca el camí de preview, `send_top_newsletter` intacte).
- 10 tests nous; suite 1475 passed. Docs comptes.md al dia.

## Per validar el render (la teua part)

1. Revisa el PR #312 (sobretot el template).
2. Post-merge: posa el teu Gmail a `newsletter_desti_prova` a
   `/staff/configuracio` i genera un esborrany des de
   `/staff/social/newsletter` (o espera el de dissabte 18:00).
3. Compara Gmail (clar i fosc) amb Spark. Si el render convenç,
   buida el camp o deixa'l per a futures proves.
