# Informe — Provinença dels orfes desactivats per la migració 0090

Data: 2026-06-07. Read-only (BD prod). NO fix.

## Pregunta

La migració `music 0090` va desactivar orfes (cançons pendents sense cap
artista aprovat). El descens net de la cua va ser **537 → 352 (−185)**,
més que les 149 mesurades a l'auditoria. Volem saber: d'on venen, i si hi
ha una **font d'ingest viva** que el ganxo de de-aprovació (#159) NO
cobreix.

## Reconciliació del −185 vs 149

El −185 net **no** és tot 0090: inclou churn d'ingest horari entre la
mesura i el deploy (entren cançons pendents noves alhora que 0090 en
desactiva). El conjunt **net atribuïble a 0090** són els orfes inactius
que mai van passar per rebuig a nivell de cançó:

| Conjunt (estat actual) | Count |
|---|---|
| Orfes inactius (contributors_raw buit, cap artista aprovat) | 181 |
| · amb rebuig a nivell de **cançó** (ja inactius abans de 0090) | 32 |
| · **sense** rebuig de cançó → víctimes de 0090 | **149** |

Els 149 coincideixen amb la mesura original de l'auditoria. Els 32 amb
historial `rebutjada` de cançó ja estaven `activa=false` (via
`rebutjar_canco`); no són víctimes de 0090.

## Repartiment dels 149 (víctimes de 0090): rebuig vs ingest fresc

Criteri "camí de rebuig": algun artista enllaçat (main o col·laborador)
té un `StaffAuditLog action=artista_rebutjar` o un `HistorialRevisio`
`rebutjada` amb motiu `desvincular_artista`/`artista_incorrecte` sota el
seu nom.

| Camí | Count | Cobert pel ganxo #159? |
|---|---|---|
| **Camí de rebuig** (artista rebutjat → cançó reassignada/òrfena, patró Irokz/Aïsha) | **116** | Sí (el ganxo de de-aprovació ara desactiva en rebutjar) |
| **Ingest fresc** (cap evidència de rebuig en cap artista enllaçat) | **33** | No (mai passa per rebuig) |

## Els 33 d'"ingest fresc": NO és una font viva

| Mètrica | Valor |
|---|---|
| created_at (rang) | **2026-04-10 → 2026-04-13** (finestra de 3 dies) |
| Creats en els últims 30 dies | **0** |
| Derivades de soroll (slowed/remix/live/…) per nom | 0 |
| font_descoberta del main | `deezer_contributor` (auto-descobert) |

Tots els 33 daten de la mateixa finestra de mitjans d'abril — el mateix
episodi que va crear Irokz/Aïsha (04-10..04-12): materialització massiva
de col·laboradors Deezer **abans** del fix de diferiment del 2026-05-07
(`contributors_raw`, que ara ajorna la creació de pendents fins a
l'aprovació). Cap orfe nou en 30 dies.

## Conclusió

1. **No hi ha font d'ingest viva** produint orfes ara mateix. Els 149
   tracen tots a l'episodi d'abril; 0 nous en 30 dies. Els 33 "fresc" són
   residu d'aquell episodi (pre-fix de diferiment), no un degoteig de
   P1/P2/getSimilar en curs.
2. El **camí de rebuig (116)** queda cobert d'ara endavant pel ganxo de
   de-aprovació de #159.
3. La cua té **0 orfes actius** ara (post-0090). 
4. Implicació per al **gate a l'ingest P1/P2**: NO és urgent — no hi ha
   leak viu. L'escombrat recurrent (FASE 2) és una **xarxa de seguretat**
   auto-curativa per a drift futur (p. ex. si reaparegués un episodi de
   materialització), no una resposta a una hemorràgia activa.

Cap acció presa (read-only).
