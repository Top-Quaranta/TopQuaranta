/**
 * StaffSocialPage — /staff/social
 *
 * Distribution cockpit (house kit). Shows:
 *  - The master distribution switch + the six-channel grid (effective
 *    state + last send; links to the per-channel views).
 *  - The week calendar + "Generar totes les slides" dry-run button.
 *
 * Instagram config (credentials, phase, story cap, token TTL, matrix)
 * moved to its own ChannelView at /staff/social/instagram (3c).
 *
 * The publications list (search, filters, links, lifecycle actions) and
 * the slide gallery moved to /staff/social/publicacions
 * (PublicacionsTable). Mastodon/Bluesky/Telegram have their own views.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import {
  Btn,
  PageHeader,
  Pill,
  TableCard,
} from "../../components/staff/StaffTable";

// Effective per-channel state from /staff/social/estat-canals/, mapped
// to house Pill tones (semantic, token-driven — no raw palette).
const EFECTIU_PILL = {
  actiu: { tone: "green", label: "Actiu" },
  pausat_global: { tone: "gray", label: "Pausat pel mestre" },
  pausat_canal: { tone: "red", label: "Pausat (canal)" },
};

// The six channels of the cockpit grid. `field` is the per-channel
// switch on ConfiguracioGlobal; `view` points at the channel's own
// house-style page when it has one (slice 1: the three simple
// channels) — the rest keep an inline toggle until later slices.
const CHANNELS = [
  {
    key: "instagram",
    label: "Instagram",
    field: "instagram_actiu",
    view: "/staff/social/instagram",
  },
  {
    key: "mastodon",
    label: "Mastodon",
    field: "mastodon_actiu",
    view: "/staff/social/mastodon",
  },
  {
    key: "bluesky",
    label: "Bluesky",
    field: "bluesky_actiu",
    view: "/staff/social/bluesky",
  },
  {
    key: "telegram",
    label: "Telegram",
    field: "telegram_actiu",
    view: "/staff/social/telegram",
  },
  {
    key: "newsletter",
    label: "Newsletter",
    field: "newsletter_actiu",
    view: "/staff/social/newsletter",
  },
  { key: "rss", label: "RSS", field: "rss_actiu", view: null },
];

function fmtLastSend(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return d.toLocaleString("ca", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function StaffSocialPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [output, setOutput] = useState("");

  // Per-channel honest state (effective state + last send) from the
  // dedicated endpoint, alongside the main social_list payload.
  const [estat, setEstat] = useState(null);
  const reload = () =>
    Promise.all([
      api.get("/staff/social/"),
      api.get("/staff/social/estat-canals/").catch(() => null),
    ])
      .then(([d, e]) => {
        setData(d);
        setEstat(e);
      })
      .catch(() => setData(null));
  useEffect(() => {
    reload();
  }, []);

  if (!data) return <p className="p-6">Carregant…</p>;
  const { config, calendari } = data;

  // Master distribution switch (distribucio_activa). Gates ALL six
  // channels — the real global pause (replaces the old "Kill switch"
  // that only wrote instagram_actiu).
  async function toggleMaster() {
    const next = !config.distribucio_activa;
    if (
      next === false &&
      !confirm(
        "Pausar TOTA la distribució?\n\nCap canal publicarà (Instagram, " +
          "Mastodon, Bluesky, Telegram, newsletter, RSS) fins que reactivis " +
          "el mestre. Els switches per canal es conserven.",
      )
    )
      return;
    setBusy(true);
    try {
      await api.post("/staff/social/toggle/", {
        channel: "global",
        actiu: next,
      });
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function previewAll() {
    setBusy(true);
    setOutput(
      "▶ Generant totes les slides de la setmana (PPCC + territoris + novetats)…",
    );
    try {
      const res = await api.post("/staff/social/preview-all/", {});
      const lines = [];
      (res.runs || []).forEach((r) => {
        lines.push(`$ manage.py ${r.args.join(" ")}`);
        if (!r.ok && r.error) lines.push(`⚠ ${r.error}`);
      });
      lines.push("");
      lines.push(res.output || "(sense sortida)");
      setOutput(lines.join("\n"));
      await reload();
      requestAnimationFrame(() => {
        document
          .getElementById("social-output")
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    } catch (e) {
      setOutput(
        `✖ Error: ${e.payload?.error || e.message || e}\n\n${e.payload?.output || ""}`,
      );
    } finally {
      setBusy(false);
    }
  }

  // Mastodon / Bluesky / Telegram credentials now live in their own
  // house-style views (web-react/src/pages/staff/social/ChannelView.jsx
  // + channelDescriptors.jsx) — slice 1 of the distribution-views
  // redistribution. This cockpit keeps only the master switch, the
  // six-channel grid and the channels not yet migrated (Instagram,
  // newsletter, RSS).

  // ── Channel toggles (instagram / newsletter / rss; the migrated
  // channels toggle from their own view) ──
  async function toggleChannel(channel) {
    setBusy(true);
    try {
      await api.post("/staff/social/toggle/", { channel });
      await reload();
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`);
    } finally {
      setBusy(false);
    }
  }

  // Per-publication lifecycle actions (preview / publicar / reset /
  // re-publicar / eliminar-remot) + the slides gallery now live on the
  // unified publications table (pages/staff/social/PublicacionsTable.jsx
  // → /staff/social/publicacions). This cockpit keeps the master switch,
  // the channel grid, the Instagram config + the week calendar (whose
  // "Generar totes les slides" button renders the week in dry-run).

  return (
    <section className="space-y-6">
      <PageHeader
        title="Distribució"
        subtitle={`Control del calendari setmanal · mode ${
          config.dry_run ? "DRY-RUN" : "PRODUCCIÓ"
        }`}
        right={
          <Pill tone={config.dry_run ? "gray" : "green"}>
            {config.dry_run ? "DRY-RUN" : "Producció"}
          </Pill>
        }
      />

      {/* ── Master distribution switch (kit) ──────────────────── */}
      <TableCard className="p-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <p className="text-[11px] uppercase tracking-widest text-tq-ink/75">
              Interruptor mestre de distribució
            </p>
            <p className="text-sm mt-1 font-semibold flex items-center gap-2 flex-wrap">
              <Pill tone={config.distribucio_activa ? "green" : "red"}>
                {config.distribucio_activa ? "Activa" : "Pausada"}
              </Pill>
              {config.distribucio_activa
                ? "cada canal segueix el seu propi switch"
                : "cap canal publica (els sis)"}
            </p>
          </div>
          <Btn
            tone={config.distribucio_activa ? "danger" : "primary"}
            size="md"
            disabled={busy}
            onClick={toggleMaster}
          >
            {config.distribucio_activa
              ? "Pausar-ho tot"
              : "Reactivar distribució"}
          </Btn>
        </div>
        <p className="text-xs mt-3">
          <Link
            to="/staff/social/newsletter"
            className="underline decoration-dotted hover:decoration-solid"
          >
            Newsletter (esborrany + generació) →
          </Link>
        </p>
      </TableCard>

      {/* ── Channel grid (kit) ────────────────────────────────── */}
      <div>
        <h2 className="text-base font-bold text-white font-display mb-1">
          Canals
        </h2>
        <p className="text-sm text-white/70 mb-3">
          Els sis canals com a iguals. El mestre de dalt els gateja tots; cada
          canal té a més el seu propi switch. Mastodon, Bluesky i Telegram tenen
          vista pròpia; Instagram, newsletter i RSS es gestionen encara aquí
          sota.
        </p>
        <TableCard className="p-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {CHANNELS.map((c) => {
              const st = estat?.canals?.[c.key];
              const efectiu =
                st?.efectiu || (config[c.field] ? "actiu" : "pausat_canal");
              const ef = EFECTIU_PILL[efectiu] || {
                tone: "gray",
                label: efectiu,
              };
              const actiu = !!config[c.field];
              return (
                <div
                  key={c.key}
                  className="p-3 border border-tq-ink/10 rounded-md flex items-start justify-between gap-2"
                >
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-widest text-tq-ink/75">
                      {c.label}
                    </p>
                    <div className="mt-1">
                      <Pill tone={ef.tone}>{ef.label}</Pill>
                    </div>
                    {c.key !== "rss" && (
                      <p className="text-[10px] text-tq-ink/75 mt-1">
                        Últim: {fmtLastSend(st?.ultim_enviament)}
                        {st?.font === "audit" && " (audit)"}
                      </p>
                    )}
                  </div>
                  <div className="shrink-0">
                    {c.view ? (
                      <Btn tone="secondary" onClick={() => navigate(c.view)}>
                        Gestiona →
                      </Btn>
                    ) : (
                      <Btn
                        tone={actiu ? "danger" : "primary"}
                        disabled={busy}
                        onClick={() => toggleChannel(c.key)}
                        title={
                          actiu ? "Pausar aquest canal" : "Activar aquest canal"
                        }
                      >
                        {actiu ? "Pausar" : "Activar"}
                      </Btn>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </TableCard>
      </div>

      {/* ── Legacy controls (not yet migrated: Instagram config,
          calendar, publications list). Wrapped in an explicit white
          surface so the `text-tq-ink` inside reads on the dark body —
          slices 2-4 move these out into their own house-style views. */}
      <div className="bg-white text-tq-ink rounded-lg shadow-md p-4 md:p-6 space-y-6">
        {/* Channels not yet migrated to their own view (Mastodon,
          Bluesky and Telegram now live under /staff/social/<canal> via
          the channel grid above). */}
        <p className="text-[11px] text-tq-ink/75">
          La <strong>newsletter</strong> usa l'SMTP configurat a{" "}
          <code>EMAIL_HOST</code>; envia cada diumenge als usuaris amb{" "}
          <code>vol_newsletter=True</code> (revisa l'
          <Link to="/staff/social/esborrany" className="underline">
            esborrany
          </Link>{" "}
          abans). L'<strong>RSS</strong> es serveix a <code>/rss/top.xml</code>{" "}
          + <code>/rss/novetats.xml</code> sense altres credencials. Mastodon,
          Bluesky i Telegram tenen ara la seva pròpia vista (graella de dalt).
        </p>

        {/* ── Calendari de la setmana ───────────────────────────── */}
        <section>
          <h2 className="text-base font-bold font-display mb-2">
            Calendari d'aquesta setmana
          </h2>
          <p className="text-xs text-tq-ink/75 mb-2">
            El cron entra cada dia i publica cada slot segons la matriu de
            distribució (actiu + dia de cada canal). La rotació territorial està
            resolta — així ja saps quin top toca abans de prémer res.
          </p>
          <div className="mb-3">
            <button
              type="button"
              disabled={busy}
              onClick={previewAll}
              className="px-3 py-1.5 rounded bg-tq-ink text-tq-yellow text-xs font-bold hover:bg-tq-ink/90 disabled:opacity-50"
            >
              Generar totes les slides de la setmana (dry-run)
            </button>
            <span className="text-[11px] text-tq-ink/75 ml-2">
              Renderitza tots els slots (PPCC + territoris + novetats) sense
              publicar. Després pots veure'ls amb "Veure slides" a la taula de
              baix.
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="text-xs min-w-[560px] w-full border-collapse">
              <thead>
                <tr className="text-left text-tq-ink/70">
                  <th className="py-1 pr-3">Dia</th>
                  <th className="py-1 pr-3">Plataforma</th>
                  <th className="py-1 pr-3">Tipus</th>
                  <th className="py-1">Territori</th>
                </tr>
              </thead>
              <tbody>
                {(calendari || []).map((s) => (
                  <tr key={`${s.platform}-${s.tipus}-${s.weekday}`}>
                    <td className="py-1 pr-3" title={s.publication_date}>
                      <strong>{s.weekday_name}</strong>{" "}
                      <span className="text-tq-ink/75">
                        · setm. {s.project_week}
                      </span>
                    </td>
                    <td className="py-1 pr-3">
                      {s.platform.replace("instagram_", "")}
                    </td>
                    <td className="py-1 pr-3">{s.tipus}</td>
                    <td className="py-1">{s.territori_label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Insights externs ─────────────────────────────────── */}
        <div className="p-3 border border-tq-ink/15 rounded-md bg-gray-50 text-xs">
          <p className="font-semibold mb-1">
            Insights — on mirar les mètriques
          </p>
          <p className="text-tq-ink/70">
            Les estadístiques (reach, completion rate, follower growth,
            engagement) no apareixen aquí encara — les mira al{" "}
            <a
              href="https://business.facebook.com/latest/insights/overview"
              target="_blank"
              rel="noopener"
              className="underline hover:text-tq-yellow-deep"
            >
              Meta Business Suite Insights
            </a>{" "}
            o a la mateixa app d'Instagram (Profile → Insights).
          </p>
          <p className="text-tq-ink/75 mt-1">
            Sprint K integrarà el subset rellevant directament al panell
            (Insights API + comptadors interns ètics). De moment, mira-les cada
            dilluns per calibrar quins slots i dies actives a la matriu.
          </p>
        </div>

        {/* ── Captured stdout ──────────────────────────────────── */}
        {output && (
          <pre
            id="social-output"
            className="bg-tq-ink text-tq-yellow text-xs p-3 rounded overflow-x-auto whitespace-pre-wrap"
          >
            {output}
          </pre>
        )}

        {/* ── Posts list (moved) ───────────────────────────────── */}
        <p className="text-sm text-tq-ink/75">
          La llista de publicacions (amb cerca, filtres, enllaços i accions de
          cicle de vida) viu ara a{" "}
          <Link
            to="/staff/social/publicacions"
            className="underline font-semibold"
          >
            Publicacions
          </Link>
          .
        </p>
      </div>
    </section>
  );
}
