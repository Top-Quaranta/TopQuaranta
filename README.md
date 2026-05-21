<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0047ba,100:0047ba&height=120&section=header&animation=fadeIn" width="100%" />

# 🎵 TopQuaranta

<a href="https://www.topquaranta.cat">
  <img src="https://readme-typing-svg.herokuapp.com?font=Roboto&weight=600&size=22&pause=1000&duration=1000&color=0047ba&center=true&vCenter=true&width=600&lines=R%C3%A0nquing+setmanal+de+m%C3%BAsica+en+catal%C3%A0;Last.fm+%2B+Deezer+%C2%B7+10+territoris+%C2%B7+Top+40;Django+5.2+%2B+PostgreSQL+%C2%B7+Codi+obert" alt="Typing SVG" />
</a>

<br/>

![Status](https://img.shields.io/badge/Live-12b76a?style=for-the-badge)
![Django](https://img.shields.io/badge/Django_6.0-0047ba?style=for-the-badge&logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-0047ba?style=for-the-badge&logo=postgresql&logoColor=white)
![Last.fm](https://img.shields.io/badge/Last.fm-cf3339?style=for-the-badge&logo=lastdotfm&logoColor=white)
![CI](https://img.shields.io/github/actions/workflow/status/Top-Quaranta/TopQuaranta/ci.yml?branch=main&style=for-the-badge&label=CI)

</div>

---

## <img src="https://raw.githubusercontent.com/miquelmatoses/mm-design/main/icons/readme/icon-music-red.svg" width="20" height="20" /> Què és

**TopQuaranta** és el top setmanal públic de música en llengua catalana
per als Països Catalans. Cada setmana publica un **Top 40** per territori,
calculat a partir d'escoltes reals de Last.fm amb metadades de Deezer.

Missió cultural: demostrar que la música en català és **viva**, creix, i
mereix visibilitat. No monetitzem, no venem dades. El codi és obert perquè
qualsevol pugui revisar com es calcula.

## <img src="https://raw.githubusercontent.com/miquelmatoses/mm-design/main/icons/readme/icon-bolt-yellow.svg" width="20" height="20" /> Funcionalitats

- 📊 **Senyal diari** via Last.fm — `playcount` + `listeners` amb
  normalització per percentil.
- 🏆 **Rànquing setmanal** amb algoritme de 14 CTEs SQL (penalitzacions
  per antiguitat, monopoli, novetats). Transparència algorítmica
  pública a [/com-funciona](https://www.topquaranta.cat/com-funciona).
- 🗺️ **10 territoris**: CAT, VAL, BAL, CNO, AND, FRA, ALG, CAR, ALT, PPCC.
- ⚛️ **SPA React** com a interfície pública i d'administració (Sprint 4,
  abril 2026). Django passa a ser un backend API pur.
- 🎼 **Playlists Spotify** actualitzades cada matí per territori + novetats,
  mantenint URL estable i seguidors.
- 🎙️ **Whisper LID** per a identificació d'idioma automàtica sobre el
  preview de 30s de Deezer.
- 🧩 **MusicBrainz oracle** — ingesta contínua cada 15 min d'MBID, àrea,
  dates de vida, discografia i idioma de lletres. Resol col·lisions
  tipus Crim i valida novetats.
- 🫂 **Comunitat** — perfils públics, directori, publicacions moderades,
  missatgeria interna i comentaris amb notificacions email opt-out.
- 🗺️ **Mapa interactiu** — navegació drill-down per territori → comarca
  → municipi amb KPIs i graella dels artistes més escoltats per zona.
- 👥 **Panell staff React** per gestionar artistes, propostes, cançons i
  coeficients; tota acció destructiva queda a `StaffAuditLog`.
- 🧠 **Classificador ML** (Random Forest, 79 features, ROC-AUC 0.9994) per
  pre-classificar cançons noves (A/B/C) i prioritzar revisió humana.
- 💬 **Feedback d'usuaris** — botó "Corregir" a cada pàgina pública.
- 🔒 **Seguretat**: Argon2, 2FA TOTP staff, django-axes, CSP estricta.

## <img src="https://raw.githubusercontent.com/miquelmatoses/mm-design/main/icons/readme/icon-stack-blue.svg" width="20" height="20" /> Stack

<div align="center">

![React](https://img.shields.io/badge/React_19-0047ba?style=flat-square&logo=react&logoColor=white)
![Vite](https://img.shields.io/badge/Vite_8-0047ba?style=flat-square&logo=vite&logoColor=white)
![Tailwind](https://img.shields.io/badge/Tailwind_v4-0047ba?style=flat-square&logo=tailwindcss&logoColor=white)
![Django](https://img.shields.io/badge/Django_6.0-0047ba?style=flat-square&logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-cf3339?style=flat-square)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_14-0047ba?style=flat-square&logo=postgresql&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.12-0047ba?style=flat-square&logo=python&logoColor=white)
![Caddy](https://img.shields.io/badge/Caddy-0047ba?style=flat-square&logo=caddy)
![Hetzner](https://img.shields.io/badge/Hetzner-cf3339?style=flat-square)

</div>

## <img src="https://raw.githubusercontent.com/miquelmatoses/mm-design/main/icons/readme/icon-folder-blue.svg" width="20" height="20" /> Estructura

```
TopQuaranta/
├── topquaranta/    # Configuració Django + settings
├── music/          # Models domini + ML + signals
├── ingesta/        # Pipeline Last.fm + Deezer + Spotify (sync)
├── ranking/        # Algorisme setmanal (algorisme.py, 14 CTEs)
├── comptes/        # Usuari custom, PropostaArtista, Feedback, 2FA
├── web/            # Django API v1 + SEO + error handlers
│   └── api/        # tots els endpoints /api/v1/*
├── web-react/      # SPA React (públic + staff)
│   └── src/
│       ├── pages/
│       │   └── staff/    # 17 pàgines d'administració
│       ├── components/
│       └── context/      # Auth · Feedback
├── bin/            # Ops: tq-run, tq-recover, tq-health, tq-backup
├── deploy/         # Caddyfile + systemd + cron + logrotate
├── scripts/        # Anàlisi + one-shot migrations arxivades
└── vendor/         # mm-design tokens (vendored per a Django)
```

## <img src="https://raw.githubusercontent.com/miquelmatoses/mm-design/main/icons/readme/icon-code-blue.svg" width="20" height="20" /> Desenvolupament local

Requisits: Python 3.12, PostgreSQL 14+ (o SQLite per a tests).

```bash
# 1. Clone
git clone git@github.com:Top-Quaranta/TopQuaranta.git
cd TopQuaranta

# 2. Entorn virtual + dependencies
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 3. Variables d'entorn (vegeu CLAUDE.md §8 per la llista completa)
cp .env.example .env   # si existeix, o crea'l amb DATABASE_URL, LASTFM_API_KEY, etc.

# 4. Tests (SQLite in-memory, cap API externa)
pytest -q

# 5. Instal·la els pre-commit hooks (black + isort + missing-migration check)
pre-commit install

# 6. Django API local
DJANGO_SETTINGS_MODULE=topquaranta.settings.local python manage.py migrate
DJANGO_SETTINGS_MODULE=topquaranta.settings.local python manage.py runserver

# 7. SPA React
cd web-react
npm install
npm run dev        # http://localhost:5173 amb proxy a l'API
# ─ o ─
npm run build      # bundle estàtic a web-react/dist/
```

## <img src="https://raw.githubusercontent.com/miquelmatoses/mm-design/main/icons/readme/icon-user-blue.svg" width="20" height="20" /> Contribuir

- **Llegeix primer**: [`CLAUDE.md`](./CLAUDE.md) (convencions de codi,
  estructura, convencions de commit).
- **Polítiques i convencions**: [`docs/policies/`](./docs/policies/).
- **Emergències / incidents**: [`docs/ops/runbook.md`](./docs/ops/runbook.md).
- **Història del projecte**: [`docs/history/roadmap.md`](./docs/history/roadmap.md) i
  [`docs/history/changelog.md`](./docs/history/changelog.md).
- **Decisions arquitectòniques**: [`docs/decisions/`](./docs/decisions/).
- **Post-mortems**: [`docs/post-mortems/`](./docs/post-mortems/).
- **Política d'API**: [`docs/architecture/api-versioning.md`](./docs/architecture/api-versioning.md).
- **Política de claus SSH**: [`docs/ops/ssh-keys.md`](./docs/ops/ssh-keys.md).

Cada commit ha de passar:
- **pytest** (sense xarxa: mocks per a Last.fm / Deezer).
- **black** + **isort** (configurats a `pyproject.toml`).
- **makemigrations --check** (cap canvi de model sense migració).

El CI (GitHub Actions) ho valida. El pre-commit local ho fa en segons.

## <img src="https://raw.githubusercontent.com/miquelmatoses/mm-design/main/icons/readme/icon-pulse-green.svg" width="20" height="20" /> Estat

🟢 **En producció**: [topquaranta.cat](https://www.topquaranta.cat).

El pipeline corre automàticament via cron (hourly `obtenir_novetats`,
daily `obtenir_senyal`, weekly `calcular_ranking` oficials; vegeu
`/etc/cron.d/topquaranta` i `docs/history/roadmap.md`). Health: `tq-health` sobre el
servidor.

---

<div align="center">

![License](https://img.shields.io/badge/Codi-AGPL_3.0-cf3339?style=flat-square)
![Data](https://img.shields.io/badge/Dades-CC_BY_4.0-12b76a?style=flat-square)

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0047ba,100:0047ba&height=80&section=footer" width="100%" />

</div>
