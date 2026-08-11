# Informe diari de YouTube

> Quadre de comandament **temporal** de la fase d'implementació de la
> connexió amb YouTube (2026-08). Separat d'`analytics.md` pel mateix
> motiu que `analytics-goaccess.md`: és una superfície pròpia i
> l'analytics general ja frega el llindar de mida.
>
> La ingesta (descobriment, aparellament, senyal) viu a
> [`pipeline.md`](pipeline.md) §3.1 bis. Ací només l'informe.

`enviar_informe_youtube` (07:00) és el quadre de comandament mentre dura
el rodatge de la connexió amb YouTube, que per quota s'allarga setmanes.
Comparteix el llenguatge visual del Setmanari i el seu `_kpi.html`, i
reutilitza `_delta`. Seccions: descobriment de canals amb ETA, cançons
connectades per territori, **el punt cec**
(quantes de les cançons que Last.fm no veu ja tenen vídeo — la xifra que
diu si això funciona), senyal recollit i incidències.

Els comptadors «trobats avui» i «connectades avui» surten de
`Artista.youtube_checked_at` i `Canco.youtube_matched_at`; sense eixos
segells l'informe hauria d'aproximar el moviment diari, i aproximar en
un informe sobre qualitat de dades és exactament el que aquest projecte
intenta deixar de fer.

**L'ETA té dues bases i diu quina fa servir.** Amb 3 dies o més
d'història, el ritme observat dels últims 7. Amb menys, la capacitat del
pressupost (`DEFAULT_BUDGET // COST_SEARCH` ≈ 90/dia). La primera
execució real deia «~145 dies» perquè només havia corregut una vegada i
amb pressupost retallat, quan la xifra real eren ~6 dies. Mínim «~1 dia»:
arrodonir a 0 feia que el template amagara la línia.

**Temporal per disseny:** quan el rodatge acabe s'esborra la línia del
cron. No hi ha interruptor de configuració per a una cosa que s'apaga
amb una línia.


## Quan s'acaba

Esborra la línia `enviar_informe_youtube` de `deploy/cron.topquaranta`,
executa `bin/tq-sync-infra` i esborra aquest document. Els camps
`youtube_checked_at` i `youtube_matched_at` es queden: són historial de
la ingesta, no de l'informe.
