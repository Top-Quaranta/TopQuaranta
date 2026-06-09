/**
 * ConfiguracioPage — /staff/configuracio
 *
 * Edit global ranking algorithm coefficients. PATCH sends only
 * the changed fields.
 */
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import {
  Btn,
  Input,
  PageHeader,
  TableCard,
  Textarea,
} from "../../components/staff/StaffTable";

export default function ConfiguracioPage() {
  const [fields, setFields] = useState(null);
  const [values, setValues] = useState({});
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/staff/configuracio/").then((data) => {
      setFields(data.fields);
      setValues(
        Object.fromEntries(data.fields.map((f) => [f.name, String(f.value)])),
      );
    });
  }, []);

  async function save() {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const out = await api.patch("/staff/configuracio/", values);
      setFields(out.fields);
      setMsg("Configuració desada.");
    } catch (e) {
      setErr(e.payload?.error || e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!fields) return <p className="text-white/70">Carregant…</p>;

  return (
    <section>
      <PageHeader
        title="Configuració global"
        subtitle="Coeficients de l'algorisme de ranking"
        right={
          <Btn size="md" onClick={save} disabled={busy}>
            Desar
          </Btn>
        }
      />
      {err && <p className="text-red-300 mb-3">{err}</p>}
      {msg && <p className="text-emerald-300 mb-3">{msg}</p>}

      <TableCard className="p-4">
        <div className="grid md:grid-cols-2 gap-3">
          {fields.map((f) => {
            // Long-text fields (TextField, e.g. editorial_veu) render as a
            // big resizable textarea spanning both columns; short fields
            // keep the one-line input.
            const isLong = f.type === "TextField";
            return (
              <label
                key={f.name}
                className={
                  "text-xs font-semibold" + (isLong ? " md:col-span-2" : "")
                }
              >
                {f.label}
                {isLong ? (
                  <Textarea
                    value={values[f.name] || ""}
                    onChange={(e) =>
                      setValues((v) => ({ ...v, [f.name]: e.target.value }))
                    }
                    rows={8}
                    className="w-full mt-1"
                  />
                ) : (
                  <Input
                    value={values[f.name] || ""}
                    onChange={(e) =>
                      setValues((v) => ({ ...v, [f.name]: e.target.value }))
                    }
                    className="w-full mt-1 font-normal"
                  />
                )}
                {f.help && (
                  <p className="mt-0.5 text-[11px] font-normal opacity-60">
                    {f.help}
                  </p>
                )}
              </label>
            );
          })}
        </div>
      </TableCard>
    </section>
  );
}
