# Etiquetatge d'Instagram i handles caducats

> Com etiquetem artistes als carrusels d'Instagram i què passa quan un
> compte deixa d'existir. Separat de [`social.md`](social.md) pel mateix
> motiu que `social-collaboradors.md`: superfície pròpia i el doc general
> ja estava al llindar de mida.

Etiquetem l'artista principal **i tots els col·laboradors** de cada
cançó, així que la superfície de comptes que enviem és molt més gran que
els 40 del top. Meta **no ignora** una etiqueta dolenta: llança
`code 110` («cannot be accessed») i **s'endú la pujada sencera**.

El 03/08 el compte d'una col·laboradora que ni encapçalava cap cançó
(`tontaca13`, de Suu, renombrat feia temps) va tombar el top territorial
de Catalunya de la setmana 27/07, que **no s'ha publicat mai** — no hi ha
reintent i la rotació de territoris no el va tornar a programar.

Ara `upload_carousel_item` llig els comptes que Meta anomena a
`error_user_msg`, els lleva i reintenta una vegada. Un artista sense
etiquetar és infinitament millor que un top que no existeix.

**No podem validar handles per endavant**: aquesta app no té
`business_discovery` (mateixa família de límit que la lectura
d'acceptacions de col·laboració). Un rebuig en publicar és **l'única**
evidència que un compte ha canviat, així que es guarda a
`Artista.instagram_rebutjat_at`, el Setmanari el reporta a Incidències i
el filtre `?instagram=rebutjat` els llista. Editar la URL neteja la marca.

## El que no podem fer

Validar un handle abans de publicar. `business_discovery` no existeix per
al tipus d'app que fem servir (Instagram Login), igual que passa amb la
lectura d'acceptacions de col·laboració — vegeu
[`social-collaboradors.md`](social-collaboradors.md) i l'ADR-0015 §5.5.

Provar-ho creant contenidors de prova tampoc: compten contra el límit de
publicació de 24 h i posarien en risc les publicacions reals.

Per tant el descobriment és **reactiu per força**. La degradació fa que
eixe descobriment no coste res: el post ix igual i l'evidència es guarda.
