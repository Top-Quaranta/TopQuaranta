/**
 * InstagramSection — the bespoke controls of the Instagram channel view
 * (3c). Rendered as Section 1 + Control of `ChannelView` (canal=instagram)
 * via `desc.section1.kind === 'instagram'`. Custom (like NewsletterSection)
 * because Instagram's controls don't fit the generic descriptor slots:
 *
 *   - Section 1: credentials (token form + test/clear, masked display) +
 *     token TTL badge.
 *   - Control: the "Què publica" matrix (MatriuCanalToggles
 *     canal=instagram, with the per-cell dia_setmana weekday gate).
 *
 * Self-fetches `/staff/social/` for config + credentials (same data the
 * cockpit used to). Endpoints: `credentials/`, `credentials/test/`,
 * `credentials/clear/`. The legacy per-slot distribution phase was
 * removed 2026-06 (the matrix's dia_setmana replaces it). The story-cap
 * knob (`story_max_cancons_ppcc`) is no longer edited here — it stays an
 * operational knob in /staff/configuracio, read by the stories cron.
 */
import { useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { Btn, Pill, TableCard } from "../../../components/staff/StaffTable";
import MatriuCanalToggles from "./MatriuCanalToggles";

function tokenTone(daysLeft) {
  if (daysLeft == null) return "gray";
  if (daysLeft < 7) return "red";
  if (daysLeft < 21) return "yellow";
  return "green";
}

export default function InstagramSection() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [output, setOutput] = useState("");
  const [tokenDraft, setTokenDraft] = useState("");
  const [userIdDraft, setUserIdDraft] = useState("");

  function reload() {
    return api
      .get("/staff/social/")
      .then(setData)
      .catch(() => setData(null));
  }

  useEffect(() => {
    reload();
  }, []);

  if (!data) return null;
  const config = data.config || {};
  const credentials = data.credentials || { configured: false };

  async function saveCredentials() {
    if (!tokenDraft.trim()) {
      alert("Enganxa el token.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post("/staff/social/credentials/", {
        access_token: tokenDraft.trim(),
        instagram_user_id: userIdDraft.trim(),
      });
      setTokenDraft("");
      setUserIdDraft("");
      await reload();
      alert(
        `Credencials desades. Compte detectat: @${res.resolved_username || "?"} ` +
          `(ID ${res.resolved_user_id}). Comprova-les amb "Provar token".`,
      );
    } catch (e) {
      alert(`Error: ${e.payload?.error || e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function testCredentials() {
    setBusy(true);
    setOutput("");
    try {
      const res = await api.post("/staff/social/credentials/test/");
      setOutput(JSON.stringify(res, null, 2));
    } catch (e) {
      setOutput(`Error: ${e.payload?.error || e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function clearCredentials() {
    if (
      !confirm(
        "Esborrar les credencials d'Instagram desades? Es tornarà a mode DRY-RUN.",
      )
    )
      return;
    setBusy(true);
    try {
      await api.post("/staff/social/credentials/clear/");
      await reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* ── Section 1: credencials + TTL ─────────────────────── */}
      <div>
        <h2 className="mb-2 text-base font-bold text-white font-display">
          Credencials i token
        </h2>
        <TableCard className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Pill tone={credentials.configured ? "green" : "yellow"}>
              {credentials.configured ? "Configurades" : "Sense credencials"}
            </Pill>
            <Pill tone={tokenTone(config.token_days_left)}>
              {config.token_days_left == null
                ? "Token no configurat"
                : `${config.token_days_left} dies fins caducar`}
            </Pill>
          </div>
          {credentials.configured && (
            <p className="text-xs text-tq-ink/70">
              Token{" "}
              <code className="bg-tq-ink/5 px-1.5 py-0.5 rounded">
                {credentials.token_masked}
              </code>{" "}
              · IG user ID{" "}
              <code className="bg-tq-ink/5 px-1.5 py-0.5 rounded">
                {credentials.instagram_user_id}
              </code>
              {credentials.expires_at && (
                <> · Caduca {credentials.expires_at.slice(0, 10)}</>
              )}
              {credentials.updated_by && (
                <>
                  {" "}
                  · Desat per <strong>{credentials.updated_by}</strong>
                </>
              )}
            </p>
          )}
          {credentials.configured && (
            <div className="flex gap-2">
              <Btn tone="primary" onClick={testCredentials} disabled={busy}>
                Provar token (read-only)
              </Btn>
              <Btn tone="danger" onClick={clearCredentials} disabled={busy}>
                Esborrar credencials
              </Btn>
            </div>
          )}
          <details>
            <summary className="text-xs cursor-pointer font-semibold text-tq-ink/70">
              {credentials.configured
                ? "Substituir credencials…"
                : "Afegir credencials…"}
            </summary>
            <div className="mt-2 space-y-2">
              <label className="block text-xs">
                <span className="block mb-1 font-semibold">
                  Long-lived access token
                </span>
                <input
                  type="password"
                  autoComplete="off"
                  value={tokenDraft}
                  onChange={(e) => setTokenDraft(e.target.value)}
                  placeholder="IGAA..."
                  className="w-full px-2 py-1 border border-tq-ink/20 rounded text-xs font-mono"
                />
                <span className="block text-[10px] text-tq-ink/60 mt-1">
                  El token es genera a developers.facebook.com → Instagram → API
                  setup → Generate token.
                </span>
              </label>
              <details className="text-xs">
                <summary className="cursor-pointer text-tq-ink/70">
                  Override manual del Instagram user ID (rar)
                </summary>
                <input
                  type="text"
                  value={userIdDraft}
                  onChange={(e) => setUserIdDraft(e.target.value)}
                  placeholder="178…"
                  className="mt-1 w-full px-2 py-1 border border-tq-ink/20 rounded text-xs font-mono"
                />
              </details>
              <Btn
                tone="primary"
                onClick={saveCredentials}
                disabled={busy || !tokenDraft}
              >
                Desar
              </Btn>
            </div>
          </details>
          {output && (
            <pre className="bg-tq-ink text-white/90 p-3 text-xs overflow-x-auto whitespace-pre-wrap rounded">
              {output}
            </pre>
          )}
        </TableCard>
      </div>

      {/* ── Control: matriu ───────────────── */}
      <div>
        <h2 className="mb-2 text-base font-bold text-white font-display">
          Què publica
        </h2>
        <TableCard className="p-4 space-y-4">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-tq-ink/60 mb-2">
              Matriu de distribució
            </p>
            <MatriuCanalToggles canal="instagram" />
            <p className="text-[11px] text-tq-ink/60 mt-2">
              Desmarcar atura la distribució d'eixe tipus a Instagram; el dia
              fixa el dia de la setmana (sense restricció = qualsevol dia).
            </p>
          </div>
        </TableCard>
      </div>
    </div>
  );
}
