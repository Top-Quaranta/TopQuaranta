/**
 * staffViews — the single source of truth for every /staff navigable view.
 *
 * Both the left sidebar (`components/StaffLayout`) and the panell tiles
 * (`StaffDashboardPage`) render by mapping this registry, so adding a view
 * is ONE entry here and it shows up in both places automatically. Before
 * this, the two lists were hand-mirrored and drifted: the sidebar had the
 * social sub-channels + Spotify while the panell didn't, and Instagram had
 * a route (`/staff/social/instagram`) that appeared in neither.
 *
 * Item shape:
 *   to        route path (must match a <Route> under /staff/* in App.jsx)
 *   label     short label for the sidebar
 *   title     fuller title for the panell tile (defaults to `label`)
 *   desc      one-line description for the panell tile
 *   end       NavLink exact-match (only the self-link `/staff` needs it)
 *   badge     sidebar live-badge key (fetched in StaffLayout)
 *   countKey  panell queue-count key (fetched in StaffDashboardPage)
 *   inSidebar default true; set false to hide from the sidebar
 *   inPanell  default true; set false to hide from the panell tiles
 */

export const STAFF_GROUPS = [
  {
    label: "Visió general",
    items: [
      // Self-link: only in the sidebar (the panell IS this page).
      { to: "/staff", label: "Panell", end: true, inPanell: false },
      {
        to: "/staff/estat",
        label: "Estat",
        title: "Estat del sistema",
        desc: "Inventari, pipelines, ML i cues — dashboard visual.",
      },
      {
        to: "/staff/analytics",
        label: "Analytics",
        title: "Analytics",
        desc: "Mètriques agregades del web, comunitat i xarxes socials.",
      },
    ],
  },
  {
    label: "Cua del dia",
    items: [
      {
        to: "/staff/pendents",
        label: "Pendents",
        title: "Artistes pendents",
        desc: "Aprovar o descartar artistes auto-descoberts per la ingesta.",
        countKey: "artistes_pendents",
      },
      {
        to: "/staff/propostes",
        label: "Propostes",
        title: "Propostes d'artistes",
        desc: "Propostes d'usuaris per afegir artistes nous al sistema.",
        countKey: "propostes_obertes",
      },
      {
        to: "/staff/solicituds",
        label: "Sol·licituds",
        title: "Sol·licituds de gestió",
        desc: "Usuaris demanant poder gestionar un artista existent.",
        countKey: "solicituds_gestio_obertes",
      },
      {
        to: "/staff/sollicituds-revisio",
        label: "Sol·licituds revisió",
        title: "Sol·licituds de revisió",
        desc: "Sol·licituds de revisió d'entrades del catàleg.",
        badge: "sollicituds_revisio_pendents",
      },
      {
        to: "/staff/feedback",
        label: "Feedback",
        title: "Feedback d'usuaris",
        desc: "Correccions i errors reportats des de les pàgines públiques.",
        countKey: "feedback_obert",
      },
    ],
  },
  {
    label: "Catàleg",
    items: [
      {
        to: "/staff/artistes",
        label: "Artistes",
        title: "Artistes",
        desc: "Llista, edició i creació manual d'artistes aprovats.",
      },
      {
        to: "/staff/artistes/sense-instagram",
        label: "Artistes sense Instagram",
        title: "Artistes sense Instagram",
        desc: "Artistes aprovats sense instagram_url, per presència al top.",
      },
      {
        to: "/staff/cancons",
        label: "Cançons",
        title: "Cançons",
        desc: "Cançons no verificades a revisar.",
        countKey: "cancons_no_verificades",
      },
      {
        to: "/staff/albums",
        label: "Àlbums",
        title: "Àlbums",
        desc: "Edició d'àlbums i correcció de portades.",
      },
    ],
  },
  {
    label: "Top",
    items: [
      {
        to: "/staff/top",
        label: "Top provisional",
        title: "Top provisional",
        desc: "Revisar el top diari i rebutjar entrades.",
      },
    ],
  },
  {
    label: "Comunitat",
    items: [
      {
        to: "/staff/publicacions",
        label: "Publicacions",
        title: "Publicacions pendents",
        desc: "Publicacions públiques esperant aprovació.",
        countKey: "publicacions_pendents",
      },
      {
        to: "/staff/usuaris",
        label: "Usuaris",
        title: "Usuaris",
        desc: "Llista d'usuaris, moderació d'spam, reset 2FA.",
      },
    ],
  },
  {
    label: "Distribució",
    items: [
      {
        to: "/staff/social",
        label: "Social",
        title: "Distribució multi-canal",
        desc: "Cockpit: interruptor mestre + graella de canals i calendari.",
        end: true,
      },
      {
        to: "/staff/social/publicacions",
        label: "Publicacions",
        title: "Publicacions socials",
        desc: "Historial de publicacions per canal i esborrat remot.",
      },
      {
        to: "/staff/social/instagram",
        label: "Instagram",
        title: "Instagram",
        desc: "Credencials, fase, story-cap i matriu del canal Instagram.",
      },
      {
        to: "/staff/social/mastodon",
        label: "Mastodon",
        title: "Mastodon",
        desc: "Credencials i estat del canal Mastodon.",
      },
      {
        to: "/staff/social/bluesky",
        label: "Bluesky",
        title: "Bluesky",
        desc: "Credencials i estat del canal Bluesky.",
      },
      {
        to: "/staff/social/telegram",
        label: "Telegram",
        title: "Telegram",
        desc: "Credencials i estat del canal Telegram.",
      },
      {
        to: "/staff/social/newsletter",
        label: "Newsletter",
        title: "Newsletter",
        desc: "Esborrany setmanal i estat del canal Newsletter.",
      },
      {
        to: "/staff/social/spotify",
        label: "Spotify",
        title: "Spotify",
        desc: "OAuth, monitoratge Premium i sincronització de playlists.",
      },
    ],
  },
  {
    label: "Diagnòstic",
    items: [
      {
        to: "/staff/senyal",
        label: "Senyal",
        title: "Senyal diari",
        desc: "Dades brutes Last.fm (playcount + listeners) per dia.",
      },
      {
        to: "/staff/historial",
        label: "Historial",
        title: "Historial de decisions",
        desc: "Log d'aprovacions i rebuigs previs.",
      },
      {
        to: "/staff/auditlog",
        label: "Auditoria",
        title: "Auditoria staff",
        desc: "Registre immutable d'accions destructives.",
      },
    ],
  },
  {
    label: "Sistema",
    items: [
      {
        to: "/staff/configuracio",
        label: "Configuració",
        title: "Configuració global",
        desc: "Coeficients de l'algorisme de top i kill-switches.",
      },
    ],
  },
];

// Flat helper used by tests / anything that needs every item once.
export const STAFF_VIEWS = STAFF_GROUPS.flatMap((g) => g.items);
