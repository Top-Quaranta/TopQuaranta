# Observació primer batch col·laboradors IG — dilluns 2026-07-06

> Nota local de referència (untracked), escrita 2026-07-05.
> Fail-safe del poller: PR #314. Estat verificat a prod el 05-07:
> `ig_collaboradors_actiu=True`, **0 invitacions** a
> `InvitacioColaboracioIG`, disc/crons OK.

## Què passarà demà

- **09:30 UTC (11:30 CEST)** — `publicar_social` publica el feed
  `top_territorial` i (flag actiu) invita fins a 3 col·laboradors.
  Simulació del 05-07 per a BAL: **Fades (@fadesfadesfades),
  Triquell (@_triquell), Maria Jaume (@mariajaume_)** — els tres
  categoria B, mai convidats.
- **10:00 UTC** — primer tick del poller `pollar_colaboracions_ig`
  amb invitacions pendents reals. AMB EL FAIL-SAFE (PR #314): si el
  Graph no retorna cap dels invitats pendents, no toca cap estat i
  deixa l'evidència al log.

## Què mirar després de les 09:30 (publicació)

```bash
# Les 3 files noves d'invitació (estat esperat: pendent)
sudo -u topquaranta bash -c 'cd /home/topquaranta/app && \
  DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
  .venv/bin/python manage.py shell -c "
from social.models import InvitacioColaboracioIG as I
for i in I.objects.all():
    print(i.ig_media_id, i.username_snapshot, i.estat, i.data_invitacio)"'

# El post ha sortit? (i amb quants col·laboradors)
grep -i "collab\|colaborad" /var/log/topquaranta/social.log | tail -20
```

## Què mirar després de les 10:00 (primer tick del poller)

**On és l'output cru**: `/var/log/topquaranta/analytics.log` —
dues línies per media:

```bash
grep "get_collaborators raw" /var/log/topquaranta/analytics.log | tail -5
grep "\[raw\] media=" /var/log/topquaranta/analytics.log | tail -5
grep "fail-safe" /var/log/topquaranta/analytics.log | tail -5
```

- `get_collaborators raw media=... body=...` → el JSON verbatim del
  Graph ABANS de cap interpretació. **Açò és el que ADR-0015 necessita
  per validar el vocabulari d'`invite_status`.**
- `[raw] media=... statuses={...}` → el mapa parsejat.
- Si apareix `fail-safe: media ...` → el Graph NO ha retornat els
  pendents; el poller no ha tocat res (correcte). Decisió humana amb
  el body cru a la mà (probablement ajustar `reconcile_estat` amb el
  vocabulari real).

## Interpretació dels estats

| Símptoma a la BD (via shell de dalt) | Lectura |
|---|---|
| 3 files `pendent` + body cru amb `invite_status: pending` | 🟢 Tot correcte: el Graph SÍ llista pendents; el mapping funciona |
| 3 files `pendent` + línia `fail-safe` al log | 🟡 El Graph no llista pendents (el que temíem). Cap dany fet. Llegir el body cru i adaptar `reconcile_estat` |
| Cap fila d'invitació després de les 09:30 | 🟡 El guard de substitució ha descartat el pool o `media_publish` ha rebutjat els collaborators — mirar social.log |
| Alguna fila `rebutjada` a les 10:00 del mateix dia | 🔴 SÍMPTOMA DE MALINTERPRETACIÓ (ningú rebutja en 30 min): el fail-safe no ha cobert el cas. Mirar el body cru; el cooldown de 90 dies s'hauria aplicat — cal revertir l'estat a mà |
| Fila `acceptada` el mateix matí | 🟢 Possible i bo (l'acceptació IG és immediata-o-mai) |

## Recordatoris

- El límit dur de 3 col·laboradors és de la Graph API; stories no en
  porten (per disseny; només user_tags).
- `caducada` arriba als 14 dies, no demà.
- La taxa d'acceptació apareix a `MetricaPipeline`
  (`ig_collab_taxa_acceptacio`) i al panell staff.
- Quan el batch estiga observat i el vocabulari confirmat: passar
  **ADR-0015 → Accepted** i valorar la mini-vista staff
  d'`InvitacioColaboracioIG`.
- De la simulació: alguns handles del pool fan mala espina
  (@dariasalsa per a Adrià Salas, @tontaca13 per a Suu, @wazooo per a
  Mireia Vives, @_samantha) — no afecten demà (no seleccionats) i el
  guard de substitució els descartaria si el Graph els rebutja, però
  valdria la pena revisar-los a /staff/artistes quan tingues un moment.
