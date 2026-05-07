/**
 * ComunitatPublicaPage — /comunitat/public
 *
 * Publicly accessible feed of approved public posts. No auth required.
 * Separate from /comunitat (which also shows internal posts to
 * registered users) so the routing stays explicit.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { stripMarkdown } from '../lib/strip-markdown'
import useApi from '../hooks/useApi'

export default function ComunitatPublicaPage() {
  const [page, setPage] = useState(1)
  const { data } = useApi(`/comunitat/publicacions-publiques/?page=${page}`)

  return (
    <section className="max-w-3xl mx-auto text-white">
      <p className="text-[10px] uppercase tracking-widest text-tq-yellow mb-1">Comunitat</p>
      <h1 className="text-3xl font-bold mb-2">Publicacions</h1>
      <p className="text-sm text-white/70 mb-6">
        Selecció pública d'articles, notes i novetats de l'equip i la comunitat.{' '}
        <Link to="/compte/accedir" className="underline">Registra't</Link> per veure
        també el feed intern i publicar-hi.
      </p>

      {!data && <p className="text-sm text-white/70">Carregant…</p>}
      {data?.results?.length === 0 && (
        <p className="text-sm text-white/60 italic">Cap publicació pública encara.</p>
      )}

      <ul className="space-y-3">
        {data?.results?.map(p => (
          <li key={p.pk}>
            <Link
              to={`/comunitat/${p.pk}`}
              className="block bg-white text-tq-ink rounded-lg p-4 hover:shadow transition-shadow"
            >
              <h2 className="font-bold text-lg mb-1">{p.titol}</h2>
              <p className="text-sm text-tq-ink/70 line-clamp-3 whitespace-pre-wrap">{stripMarkdown(p.cos)}</p>
              <p className="text-[11px] text-tq-ink/50 mt-2">
                per {p.autor.nom_public}
                {p.autor.is_staff && ' · staff'}
                {p.publicat_at && ` · ${p.publicat_at.slice(0, 10)}`}
              </p>
            </Link>
          </li>
        ))}
      </ul>

      {data?.num_pages > 1 && (
        <div className="flex items-center gap-2 mt-4 text-xs text-white/60">
          <button disabled={!data.has_previous} onClick={() => setPage(p => p - 1)}
                  className="px-3 py-1 rounded border border-white/20 disabled:opacity-40">Anterior</button>
          <span>Pàg {data.page} de {data.num_pages}</span>
          <button disabled={!data.has_next} onClick={() => setPage(p => p + 1)}
                  className="px-3 py-1 rounded border border-white/20 disabled:opacity-40">Següent</button>
        </div>
      )}
    </section>
  )
}
