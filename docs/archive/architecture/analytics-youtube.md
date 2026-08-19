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

## Des del 2026-08-17: la pregunta és si es poden juntar

El descobriment va acabar el catàleg («queden per provar: 0»), així que
les barres de progrés informaven d'un fet tancat. El correu passa a
respondre el que continua obert: **quantes visualitzacions val una
escolta**, i quantes cançons rescataria juntar les dues fonts — que és
per al que es va construir la segona font (el top valencià tenia 22
files de 40).

Dos blocs nous, i tots dos porten la seua pròpia advertència:

- **Es poden juntar?** Mediana de visualitzacions per escolta sobre les
  cançons que es mouen a les dues bandes, amb la meitat central i la
  mida de la mostra. Per davall de 30 parelles diu «encara no és
  fiable», entre 30 i 100 «primer indici», i a partir de 100 convida a
  mirar si convergeix. Un factor tret de quatre parelles sembla un
  número i és soroll; el correu ho ha de dir, no imprimir-lo pla.
- **Què guanyaríem.** Cançons que YouTube veu moure's i Last.fm no, en
  conjunt i per territori. Són exactament les que ara no poden entrar al
  top.

**La referència es busca amb marge**, no a la data exacta de fa set dies:
`_MARGE_DIES = 3`, igual que fa `ranking.algorisme` amb `SenyalDiari`, i
l'increment es reescala als dies transcorreguts de veres. Exigir el dia
exacte és fràgil — amb una sola foto perduda el correu diria «cap cançó
comparable», que sembla una troballa i és un forat de dades. Comprovat el
17/08: amb data exacta eixien 0 comparables i amb marge, 77.

El moviment mínim per a entrar a la comparativa és de 5 en una setmana a
les dues fonts (`_MOVIMENT_MIN`): amb 1 escolta i 300 visualitzacions, la
divisió dona 300 i no significa res.

### El veredicte mira l'estabilitat, no la mida (2026-08-18)

La primera versió donava el vistiplau quan hi havia 100 parelles o més.
El 18/08 n'hi havia 179 —«prou» de sobra— i la mediana havia anat
**1 → 23 → 9** en tres dies. La mida de la mostra és condició necessària
i no suficient: el que decideix és que el número pare de moure's.

Ara el correu porta la mediana dels últims `_DIES_HISTORIAL` (5) dies i
només diu «s'ha assentat» quan les tres últimes queden dins d'un ±25 %
(`_ESTABLE_MARGE`). El marge és ample a posta: busquem que deixe de
saltar per múltiples, no precisió decimal. L'històric es recalcula a cada
execució en lloc de desar-se — són poques consultes i no val la pena una
taula per a un informe temporal.

### Un factor global o un per artista

Mesurat el 18/08 sobre 179 parelles i 22 artistes amb 3 o més cançons
comparables:

| | Dispersió (coef. de variació) |
|---|---|
| Entre tot el catàleg | **2,57** |
| Dins d'un mateix artista | **0,64** |

Quatre vegades més estreta dins de l'artista. La proporció sembla una
propietat del **públic de cada artista**, no una constant del catàleg:
Maria Jaume va de 3 a 12 i Power Burkas de 0 a 2, però ROMÀNTIC DIMONI
va de 12 a 67. Si es manté, la conversió ha de ser per artista, i el
factor global de 9 seria fals per a quasi tots.

El correu ho compara cada dia i ho diu explícitament. El llindar per a
afirmar-ho és que la dispersió interna siga menys del 70 % de la global.

### El carril importa, i no és el mateix que l'artista (2026-08-18)

Ho va assenyalar el Miquel: «això té en compte si tenim canal oficial?».
No ho tenia, i és una variable de primer ordre. Un videoclip del canal
propi té un ordre de magnitud més de públic que una Art Track (mediana
de 3.392 visualitzacions contra 92), així que la mateixa cançó dona
proporcions molt distintes segons d'on vinguen les visites:

| | Mediana | Meitat central | Dispersió |
|---|---|---|---|
| Només Art Track | 4 | 2–9 | 2,19 |
| Amb videoclip propi | 36 | 9–148 | 1,84 |
| Barrejades | 9 | 3–54 | **2,57** |

**Nou vegades de diferència**, i barrejar-los infla la dispersió del
conjunt. El correu les separa des d'ara.

El que això NO és: una explicació alternativa de l'efecte per artista.
Controlant per carril, la dispersió interna de l'artista baixa **encara
més** — 0,48 amb Art Track sol i 0,40 amb videoclip, contra 0,64
barrejat. L'artista continua sent la variable forta.

Altres variables comprovades el mateix dia, per a tancar-les:

- **Volum**: no explica res. Amb 5–20 escoltes la dispersió és 2,51 i
  amb 20–100 és 2,71. No és soroll de números menuts.
- **Edat de la cançó**: mou el nivell, no la dispersió. Les d'1 a 6
  mesos tenen mediana 13 i les de més de 6 mesos, 3 — quatre vegades
  menys. La dispersió es queda al voltant de 2,3 en tots dos casos.

O siga que el carril i l'edat desplacen el nivell, i l'artista és el que
estreny. Com que les cançons d'un mateix artista solen compartir carril i
edat, una conversió per artista ja absorbeix les tres coses.

### Un carril nou no és una setmana de públic (2026-08-18)

`SenyalYouTube.views` és la **suma de tots els carrils** d'una cançó. Quan
se n'hi afegeix un —perquè per fi s'aparella el videoclip del canal
propi— la suma fa un bot amb el comptador de tota la vida del vídeo nou.
Llegir eixe bot com a increment setmanal infla la xifra per ordres de
magnitud.

Andreu Valor: 140 visualitzacions el 12/08 amb 1 vídeo, 88.450 el 13/08
amb 4. El moviment real de la setmana eren **17**; l'informe li'n
comptava **103.048** i el posava al capdamunt del top valencià. Ho va
detectar el Miquel dient que no li quadrava que fos tan famós.

`n_videos` es guarda a cada foto justament per a això: **un increment
només és honest si el conjunt de carrils és el mateix als dos extrems**.
És la mateixa família que `_robust_weekly_from_series` de
`ranking.algorisme` per a Last.fm — un esglaó d'un acumulat no és
audiència.

Abast de la contaminació el dia que es va trobar: 176 de 1.937 cançons
(9 %), però eren les més grosses, així que dominaven el cap del rànquing.
Efecte de la guarda sobre les conclusions:

| | Contaminat | Net |
|---|---|---|
| Parelles comparables | 179 | 156 |
| Mediana del factor | 9 | 6 |
| Candidates VAL (M=200, llindar=200) | 92 | **74** |
| Cap del top VAL | Andreu Valor | **La Fúmiga** |

La conclusió de fons aguanta —sumar ompli els tops— però els números
estaven un 20 % inflats i l'ordre del cap era fals.

**Açò val també per a la integració al rànquing**: si algun dia
`SenyalYouTube` entra al càlcul del top, la mateixa guarda ha d'anar al
lector del senyal, no només a l'informe.

### Comptar carrils no basta: cal saber quins (2026-08-19)

La guarda anterior comparava `n_videos` als dos extrems de la finestra.
És un **substitut**, i el Miquel va trobar per on falla: si un dia
desapareix un vídeo menut i n'entra un de gran, el compte es queda igual
i el bot es cola sencer.

Des del 2026-08-19, `SenyalYouTube.views_per_video` guarda
`{video_id: views}` de cada dia, i l'increment setmanal es calcula
**sumant restes per vídeo** en lloc de restar sumes:

```python
comuns = set(avui) & set(abans)
delta = sum(avui[v] - abans[v] for v in comuns if avui[v] >= abans[v])
```

Amb això, per construcció:

- un **vídeo nou** no aporta res el dia que apareix —no en tenim base— i
  aporta tot el que guanye a partir de l'endemà;
- un **vídeo que desapareix** deixa d'aportar sense restar el que havia
  acumulat;
- una **substitució** d'un vídeo per un altre ja no es pot confondre amb
  públic, que és el forat que quedava.

És un mapa a la mateixa fila i no una taula nova: sempre es llig la foto
sencera d'una cançó, mai vídeos solts, i estalvia unes 3.800 files al
dia.

Les files escrites abans d'eixa data no porten detall i cauen al criteri
antic (mateix `n_videos` als dos extrems), que per a una cançó d'un sol
carril és equivalent. La sèrie de Last.fm hi cau sempre: no té carrils.

### El correu conta l'efecte sobre el top (2026-08-19)

Amb la decisió a prop, la pregunta útil deixa de ser «quin és el factor»
i passa a ser **quantes files canvien i qui les decideix**. El bloc de
dalt del correu ho simula cada dia amb la configuració real:

| | files ara | amb YouTube | noves | mana YT |
|---|---|---|---|---|
| CAT | 40/40 | 40/40 | 0 | 0 |
| VAL | **30/40** | **40/40** | **+10** | 0 |
| BAL | 40/40 | 40/40 | 0 | 0 |
| ALT | 5/40 | **13/40** | +8 | 0 |

«Noves» són files que entren al top 40 i abans no hi eren. «Mana YT» són
files on les visualitzacions pesen més que les escoltes: **si es queda a
zero, YouTube només omple buits i no reordena res del que Last.fm ja
veu**, que és el comportament que es va buscar en triar el pes.

Es calcula amb `ConfiguracioGlobal`, així que moure el pes al panell
canvia el correu de l'endemà sense desplegar res. Mentre no hi haja prou
història és una simulació, i el correu diu **quants dies falten**; quan
la font s'activa sola (vegeu [`algorithm.md`](algorithm.md) §2.4),
descriu el top que s'està publicant. No hi ha res a encendre.
