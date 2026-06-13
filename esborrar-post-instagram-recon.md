# Esborrar un post d'Instagram publicat — recon

> **NOMÉS-LECTURA, 2026-06-13.** Cap canvi al codi, a la BD ni a Instagram.
> Cap crida que modifiqui res (els tests contra l'API de Meta es van fer en
> una recon anterior, no aquí). Diagnòstic separat en les dues capes.

## TL;DR

L'esborrat **no és un error nostre empassat** ni un no-op silenciós: el nostre
codi crida Meta, Meta **rebutja** la petició, el backend torna **502** i el
frontend mostra **«✖ Error»** amb el missatge de Meta. La causa real és de
**configuració de plataforma**: Meta **sí** que permet esborrar media
publicat, però **només** via `graph.facebook.com` + "Instagram API amb
**Facebook** Login" + permís `instagram_manage_contents`. La nostra integració
fa servir `graph.instagram.com` + "Instagram API amb **Instagram** Login", una
superfície on **esborrar media NO està suportat** → Meta respon
`400 code=100 subcode=33 "does not support this operation"`.

→ No és arreglable amb un canvi petit: caldria **migrar la integració d'IG a
Facebook Login**. Mentrestant el botó promet una cosa que no pot complir.

---

## 1. La nostra banda — flux complet de l'esborrat

**Botó (frontend):** `web-react/src/pages/staff/social/PublicacionsTable.jsx`
- Etiqueta `DELETE_LABEL` → "Esborrar IG" / "Esborrar story IG" (i Mastodon/
  Bluesky/Telegram).
- `eliminarRemot(post)` (línia 183): si no hi ha `instagram_media_id` →
  `alert("…mai s'ha publicat o ja s'ha resetejat")`. Si n'hi ha → `confirm()`
  destructiu → `POST /staff/social/eliminar-remot/ {pk}`.
- Resposta: `setOutput(res.ok ? '✓' : '✖' + res.msg)`. **`api.post` llança
  en non-2xx** (`web-react/src/lib/api.js:37` → `throw err` amb
  `err.payload`), així que un **502** salta al `catch` (línia 203) i mostra
  `✖ Error: … {e.payload.msg}`. **L'operador SÍ que veu l'error** (amb el text
  cru de Meta). No és silenciós.

**Endpoint (backend):** `web/api/staff/social/posts.py`
- `social_eliminar_remot` (línia 650) → `_delete_remote_and_reset(post)` dins
  un `try/except Exception` que torna **502** amb el nom de l'excepció (NO
  s'empassa l'error; el propaga). Si `ok` és False → 400 (sense id remota) o
  **502** (error d'API).
- `_delete_remote_and_reset` (línia 550), branca `instagram_feed`/
  `instagram_story`:
  ```python
  r = requests.delete(f"{GRAPH_BASE}/{ext_id}", params={"access_token": _token()}, timeout=30)
  ok = r.ok
  msg = f"DELETE /{ext_id} → {r.status_code}: {r.text[:300]}" if not r.ok else "…200 OK"
  if not ok: return False, msg          # ← surt ABANS de tocar la BD
  # només si ok: reset local (status→pendent, media_id="", etc.)
  ```
- `social_eliminar_instagram` (línia 494, endpoint antic equivalent): mateix
  `requests.delete`; en `not r.ok` torna **502 sense resetejar** la fila.

**Pas a pas quan algú prem «Esborrar IG»:**
1. confirm() → `POST /staff/social/eliminar-remot/`.
2. Backend: `requests.delete(https://graph.instagram.com/v19.0/{media_id}?access_token=…)`.
3. Meta respon `400 {"error":{"message":"Unsupported delete request…does not
   support this operation","code":100,"error_subcode":33}}`.
4. `r.ok` és False → `_delete_remote_and_reset` torna `(False, msg)` **sense
   modificar la fila** → endpoint torna **502 {ok:false, msg}**.
5. Frontend: `catch` → «✖ Error: … {msg de Meta}». La fila segueix
   `status=publicat` amb el `instagram_media_id` intacte.

**Veredicte capa 1:** el codi és *correcte estructuralment* — propaga l'error i
**no canvia l'estat en cas de fallada** (cap fantasma generat per nosaltres).
El `except Exception` que l'auditoria del pipeline marcava com a sospitós **NO
és la causa aquí** (aquell és a les management commands; aquest `except` torna
502, no empassa). El que falla és la crida a Meta en sí.

## 2. La banda d'Instagram — què diu la documentació oficial

Sí, el codi intenta esborrar el media via Meta: `DELETE /{media-id}` contra
`GRAPH_BASE`.

**`GRAPH_BASE = "https://graph.instagram.com/v19.0"`** i el token surt de
`InstagramAuth.access_token` + `instagram_user_id` (`social/instagram_client.py:38,53,61`)
→ això és la **"Instagram API amb Instagram Login"** (token d'usuari d'IG
directe, sense Pàgina de Facebook).

**Documentació oficial de Meta** (Instagram Media reference) — esborrar media
publicat **està suportat**, PERÒ amb aquests requisits:

- **Host:** `graph.facebook.com` (no `graph.instagram.com`).
  > "Host URL `graph.facebook.com`"
- **Login:** *només* "Instagram API with **Facebook** Login".
  > "This api only supports Instagram API with Facebook login only."
- **Permís:** `instagram_manage_contents` (a més d'`instagram_basic`).
- **Carrusels:** s'esborra l'àlbum sencer indicant l'**id del contenidor del
  carrusel**; no es poden esborrar fills individuals.
  > "Non-ad posts, Stories, Reels and entire carousel albums are supported. …
  > Individually deleting media within a carousel is not supported."

**Conclusió capa 2:** esborrar **NO** és un límit absolut de la plataforma —
existeix— però **NO** a la superfície que fem servir nosaltres. A
`graph.instagram.com` + Instagram Login l'operació de DELETE de media no
existeix, i Meta respon `code=100 subcode=33`. **És un desajust de
configuració** (superfície d'API + tipus de login + permís), no un bug de
lògica nostre.

## 3. Estat de consistència (`instagram_media_id`)

- **Fallada de Meta (estat actual):** el reset local només passa **després**
  d'un `r.ok`. Com que Meta falla, la fila **no es toca** → segueix
  `status=publicat` amb `instagram_media_id`. **No es crea cap post fantasma**
  en la direcció "nosaltres diem esborrat / IG el manté". ✅
- **Direcció inversa (esborrat manual a l'app d'IG):** si algú esborra el post
  a mà a Instagram, Meta el treu però la **nostra fila queda obsoleta**
  (`publicat` + media_id que ja no existeix). Llavors `eliminar-remot` fallaria
  amb 400/404 i `republicar` fallaria al pas de delete. Aquest desajust **sí
  que pot passar ara** (de fet va passar avui). L'escapatòria existeix:
  `social_reset` (`POST /staff/social/reset/`, botó "Reset") buida la fila
  localment **sense** tocar IG. Però el seu docstring diu "for that use
  `eliminar-instagram` first" — instrucció **enganyosa** perquè
  `eliminar-instagram` no funciona per a IG.

## 4. Opcions (sense implementar) — ordenades per honestedat amb l'usuari

L'estat actual (un botó "Esborrar IG" que sempre torna un error cru de Meta) és
el **menys honest**: promet una acció que no pot fer i deixa un missatge tècnic
confús. Per ordre d'honestedat:

1. **Fer el botó honest (immediat, baix cost, NOSTRE).** Per a `instagram_feed`
   / `instagram_story`: substituir "Esborrar IG" per un flux que **no menteixi**:
   - "Marca com retirat al nostre sistema" = el `reset` local que ja existeix
     (status→pendent, neteja media_id), **+ instrucció clara**: "Instagram no
     permet esborrar per API amb la configuració actual; esborra'l a mà a
     l'app", idealment amb un **enllaç al permalink** del post (es pot obtenir
     amb `GET /{media-id}?fields=permalink` mentre encara existeix).
   - Corregir el docstring/ajuda de `social_reset` (treure "use
     eliminar-instagram first").
   - Mastodon/Bluesky/Telegram **no es toquen** — allà l'esborrat remot sí que
     funciona.
2. **Arreglar-ho de veritat: migrar la integració d'IG a Facebook Login
   (gran, NOSTRE+Meta).** Connectar el compte IG Business a una Pàgina de
   Facebook, demanar `instagram_manage_contents` (App Review), i reescriure el
   flux contra `graph.facebook.com`. Llavors el DELETE funciona (carrusel
   sencer via l'id del contenidor, que ja guardem a `instagram_media_id`).
   Risc: re-auth, App Review, i tocar el flux de **publicació** que ara
   funciona. Decisió de producte: ¿val la pena per a una acció poc freqüent?
3. **Llevar el botó d'esborrat d'IG (mínim).** Si no es migra i no es vol el
   flux manual, treure'l és més honest que deixar-lo fallant — però perd
   l'escapatòria de reset. Pitjor que l'opció 1.

> Qualsevol cura que toqui Instagram de veritat o l'estat de publicacions:
> decisió i OK explícit de Miquel.

---

## Apèndix — evidència

- Codi: `web/api/staff/social/posts.py` (`social_eliminar_remot` 650,
  `_delete_remote_and_reset` 550, `social_eliminar_instagram` 494,
  `social_reset` 452); `social/instagram_client.py:38,53,61`;
  `web-react/src/pages/staff/social/PublicacionsTable.jsx` (183, 210, 50);
  `web-react/src/lib/api.js:37`.
- Error empíric (recon anterior, avui): `DELETE
  /18126719920623117 → 400 IGApiException code=100 subcode=33 "Unsupported
  delete request … does not support this operation"`.
- Documentació Meta:
  [Instagram Media reference (developers.facebook.com)](https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/),
  [IG User media (developers.facebook.com)](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/).

*Recon acabat. Cap canvi. Implementació/cura → decisió de Miquel.*
