# Cohort casc-buit — embut del MAIG (recon)

> **NOMÉS-LECTURA, 2026-06-13.** Cap esborrat, cap crida externa.
> **L'ABRIL (5 094, seed català manual) queda 100 % EXCLÒS** de qualsevol
> esborrat fins nova ordre. Tot aquest treball és sobre el MAIG (24 897).

## TL;DR (honest)

L'embut barat **no acota** el residu a una mida assumible. Dels 24 897 del
maig, els senyals gratuïts de BD només classifiquen amb confiança **~912**
(891 conservar + 21 probable-fora). Els altres **23 985 queden DUBTÓS** —
i el cub dubtós **encara conté catalans reals** (p.ex. *Guiu Cortés*), així
que **no es pot esborrar en bloc**. Recerca artista-a-artista sobre 23 985
**NO és assumible**. Cal una decisió de Miquel sobre el camí (sota).

Per què els senyals barats són gairebé cecs aquí:
- **Quasi tots els aprovats són catalans** (2 004 de 2 006 tenen territori
  PPCC) → l'eix "source català vs no-català" és degenerat.
- **Només 884 dels 24 897 conserven una vora `ArtistaLastfmSimilar`
  entrant.** El cron reemplaça les similars per source de manera completa,
  així que l'origen històric (quin aprovat els va descobrir) **s'ha perdut**
  per a 24 013. Sense vora ⇒ sense senyal d'esglaó 1.

## ESGLAÓ 1 (gratis, BD — vores de similar entrants)

| | Recompte |
|---|---:|
| MAIG cohort | 24 897 |
| amb vora entrant (`ArtistaLastfmSimilar` target) | 884 |
| …de source CATALÀ (territori PPCC) | 863 |
| …de source només NO-català | 21 |
| **sense cap vora entrant** | **24 013** |

(Només 2 aprovats no són de territori català, d'aquí que el munt
"no-català" sigui residual.)

## ESGLAÓ 2 (gratis, BD — encreuament de nom normalitzat)

Nom normalitzat (sense accents/puntuació, minúscules) del maig creuat amb el
**seed d'abril** (4 921 noms) + el **catàleg aprovat** (2 003 noms):

- **Coincidències: 30.** (El mateix artista ja existeix com a català →
  conservar.)

## GRUPS (suma = 24 897)

| Grup | Recompte | Acció |
|---|---:|---|
| **PROBABLE CATALÀ / conservar** (vora de source català ∪ nom coincident) | **891** | **NO s'esborra** |
| **PROBABLE FORA** (vora només de no-català, cap coincidència) | **21** | candidat segur a esborrat (mostra sota — clarament forà) |
| **DUBTÓS / RESIDU** (sense vora ∧ sense coincidència) | **23 985** | sense senyal clar — vegeu sota |

### Mostra 40 · PROBABLE FORA (clarament no-català)

```
Raydar · Black Milk · Vector Seven · Gatillazo · BARBARO URBANO VARGAS &
AVENREC · Dano & Emelvi · Isla K · Emxnii · Rels B ft. Maikel Delacalle ·
Diles · Rels B, Dellafuente · AZ · Smut Peddlers · Tha God Fahim · Sadat X ·
Akauzazte · Oddisee · S3an · Blueprint · Godfather Don · Canibus
```

(US hip-hop, reggaeton, punk basc… cap rastre català. Esborrat segur, però
només 21.)

### El DUBTÓS (23 985) — caracterització

- **No-llatins** (CJK / ciríl·lic / etc. — gairebé segur forans): **166**.
- **Noms llatins** (anglès/castellà/portuguès/**i algun català**): **23 819**.
- Mostra aleatòria (mostra que la majoria semblen forans **però hi ha
  catalans escampats**, p.ex. *Guiu Cortés*):

```
Cybernetic:Fuckheadz · Sam Dexter · Glen Darren · Opal Maven · NerdKids ·
Lili Castiglioni · Emma Hallin · OBK · Alvin Lee · Los Renovados De
California · Guiu Cortés ⟵ català · Filipe Papi · Aleks Syntek · Eugenia
Quevedo · Maztek · Гневъ · Projekt Ostry Emade · Viaje a 800 · Fair Warning
```

## Conclusió i decisió pendent (Miquel)

El gate que vas posar — *"recerca externa només SI el residu té mida
assumible"* — **no es compleix**: 23 985 no és assumible per a recerca
artista-a-artista (≈ 24 k crides amb tallacircuits = hores, i imperfecte).
I com que el dubtós conté catalans reals, **no es pot esborrar en bloc**.

**Accions netes ja disponibles (amb el teu OK):**
- **Conservar els 891** (probable català) — definitiu.
- **Esborrar els 21 probable-fora** (+ opcionalment els 166 no-llatins del
  dubtós) — petit i segur.

**Per als 23 985 dubtós, opcions (tu tries; no he tocat res):**
1. **Oracle batch barat (recomanat abans de cap crawl per-artista):** baixar
   **una sola vegada** el catàleg de **Viasona** (oracle fort de música
   catalana) i creuar-hi els 23 819 noms llatins → coincidència = conservar;
   la resta queda com a residu molt més petit per a recerca o esborrat.
   Una fetch, no 24 k crides.
2. **Política de "no esborrar":** ara que la cascada està parada i el fix de
   la llista d'staff (#241) ja amaga el soroll, aquests pendents **fan poc
   mal** quedant-se. Cost de mantenir-los ≈ baix; cost d'esborrar un català
   per error ≈ alt i irreversible (sense tombstone).
3. **Crawl per-artista** (Deezer/Viasona/Bandcamp, mai Spotify) amb
   tallacircuits — **NO recomanat a 24 k**: massa volum per a un sol pas.
   Només sobre un residu ja acotat per l'opció 1.

**No segueixo a la FASE DE RECERCA** perquè el residu no és assumible (el teu
propi gate). Espero que decideixis el camí per als 23 985.

*Recon acabat. Cap esborrat, cap crida externa, cap estat canviat.*
