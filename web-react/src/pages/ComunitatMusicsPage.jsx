/**
 * ComunitatMusicsPage — /comunitat-musics (public bridge, Slice D)
 *
 * Public marketing landing that sells the musician community to anonymous
 * visitors. Mirrors the SSR page (web/templates/seo/comunitat.html) that
 * bots index. Does not list profiles (the directory is registered-only);
 * it pitches the value and routes to register / the community.
 */
import { Helmet } from 'react-helmet-async'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const WHAT = [
  ['Crea el teu perfil de músic', 'Instruments, gèneres, nivell i què busques.'],
  ['Cerca al directori', 'Per instrument, gènere, territori i intenció ("busca grup").'],
  ['Connecta', 'Missatge directe amb qui t\'interessa.'],
  ['Publica anuncis', 'Busques banda, ofereixes col·laboració, novetats.'],
]

export default function ComunitatMusicsPage() {
  const { profile } = useAuth()
  const authed = !!profile?.is_authenticated
  const ctaTo = authed ? '/comunitat/perfil' : '/compte/registre'
  const ctaLabel = authed
    ? 'Vés al teu perfil de comunitat →'
    : 'Crea el teu compte i uneix-te →'

  return (
    <section className="max-w-3xl mx-auto px-4 py-12 text-white">
      <Helmet>
        <title>Comunitat de músics en català: busca grup i col·laboradors · TopQuaranta</title>
        <meta
          name="description"
          content="Fas música en català? Troba grup, busca col·laboradors i connecta amb músics de tots els territoris."
        />
      </Helmet>

      <p className="text-[10px] uppercase tracking-widest text-tq-yellow mb-2">Comunitat</p>
      <h1 className="text-4xl font-bold mb-3">Comunitat de músics en català</h1>
      <p className="text-lg text-white/80 mb-6">
        Busca grup, troba col·laboradors i fes música en la teua llengua.
        Connecta amb cantants, instrumentistes i productors de tots els
        territoris de parla catalana.
      </p>

      <Link
        to={ctaTo}
        className="inline-block px-5 py-2.5 bg-tq-yellow text-tq-ink rounded-md font-semibold text-sm mb-10"
      >
        {ctaLabel}
      </Link>

      <h2 className="text-xl font-bold mb-4">Què hi pots fer</h2>
      <div className="grid sm:grid-cols-2 gap-4 mb-10">
        {WHAT.map(([t, d]) => (
          <div key={t} className="bg-white/5 border border-white/10 rounded-lg p-4">
            <p className="font-semibold mb-1">{t}</p>
            <p className="text-sm text-white/70">{d}</p>
          </div>
        ))}
      </div>

      <p className="text-sm text-white/70">
        Cal un compte gratuït. En registrar-te pots dir que fas música en
        català i fer-te visible al directori perquè altres músics et trobin.
      </p>
    </section>
  )
}
