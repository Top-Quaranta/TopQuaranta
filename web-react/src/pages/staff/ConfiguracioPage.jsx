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
  const [sections, setSections] = useState([]);
  const [values, setValues] = useState({});
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/staff/configuracio/").then((data) => {
      setFields(data.fields);
      setSections(data.sections || []);
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
      if (out.sections) setSections(out.sections);
      setMsg("Configuració desada.");
    } catch (e) {
      setErr(e.payload?.error || e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!fields) return <p className="text-white/70">Carregant…</p>;

  // Group by section (server-provided order); a field with no section falls
  // into "Altres" via the server.
  const order = sections.length
    ? sections
    : [...new Set(fields.map((f) => f.section || "Altres"))];

  function renderField(f) {
    // Long-text fields (TextField, e.g. editorial_veu) render as a big
    // resizable textarea spanning both columns; short fields keep one line.
    const isLong = f.type === "TextField";
    return (
      <label
        key={f.name}
        className={"text-xs font-semibold" + (isLong ? " md:col-span-2" : "")}
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
          <p className="mt-0.5 text-[11px] font-normal opacity-60">{f.help}</p>
        )}
      </label>
    );
  }

  return (
    <section>
      <PageHeader
        title="Configuració global"
        subtitle="Paràmetres del ranking, soft cap, editorial i distribució"
        right={
          <Btn size="md" onClick={save} disabled={busy}>
            Desar
          </Btn>
        }
      />
      {err && <p className="text-red-300 mb-3">{err}</p>}
      {msg && <p className="text-emerald-300 mb-3">{msg}</p>}

      <div className="space-y-4">
        {order.map((sec) => {
          const secFields = fields.filter(
            (f) => (f.section || "Altres") === sec,
          );
          if (!secFields.length) return null;
          return (
            <TableCard key={sec} className="p-4">
              <h3 className="text-sm font-bold text-tq-yellow mb-3">{sec}</h3>
              <div className="grid md:grid-cols-2 gap-3">
                {secFields.map(renderField)}
              </div>
            </TableCard>
          );
        })}
      </div>
    </section>
  );
}
