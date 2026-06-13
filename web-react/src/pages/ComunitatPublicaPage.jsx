/**
 * ComunitatPublicaPage — /comunitat/public (redisseny web).
 *
 * Public feed of approved posts (no auth). Reskinned to the new language:
 * rd header + glass post rows + rd pagination. Endpoint unchanged.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { stripMarkdown } from '../lib/strip-markdown'
import useApi from '../hooks/useApi'
import { Kicker, Crit } from '../components/rd/primitives'

export default function ComunitatPublicaPage() {
  const [page, setPage] = useState(1)
  const { data } = useApi(`/comunitat/publicacions-publiques/?page=${page}`)

  return (
    <section className="max-w-3xl mx-auto text-white">
      <Kicker color="var(--color-tq-yellow)">comunitat</Kicker>
      <Crit as="h1" className="rd-cc-h2" style={{ fontSize: 28, marginTop: 4 }}>PUBLICACIONS</Crit>
      <p className="text-sm text-white/70 mt-2 mb-6">
        Selecció pública d'articles, notes i novetats de l'equip i la comunitat.{' '}
        <Link to="/compte/accedir" className="rd-prose-link">Registra't</Link> per veure
        també el feed intern i publicar-hi.
      </p>

      {!data && <p className="rd-empty">Carregant…</p>}
      {data?.results?.length === 0 && <p className="rd-empty">Cap publicació pública encara.</p>}

      <ul className="flex flex-col gap-3">
        {data?.results?.map(p => (
          <li key={p.pk}>
            <Link to={`/comunitat/${p.pk}`} className="rd-com-post rd-glass">
              <h2 className="font-extrabold text-lg mb-1" style={{ fontFamily: 'var(--font-body)' }}>{p.titol}</h2>
              <p className="text-sm text-white/70 line-clamp-3 whitespace-pre-wrap">{stripMarkdown(p.cos)}</p>
              <p className="text-[11px] text-white/45 mt-2">
                per {p.autor.nom_public}{p.autor.is_staff && ' · staff'}{p.publicat_at && ` · ${p.publicat_at.slice(0, 10)}`}
              </p>
            </Link>
          </li>
        ))}
      </ul>

      {data?.num_pages > 1 && (
        <nav className="rd-pager" style={{ marginTop: 20, justifyContent: 'flex-start' }} aria-label="Paginació">
          <button type="button" disabled={!data.has_previous} onClick={() => setPage(p => p - 1)} className="rd-btn rd-btn--ghost">Anterior</button>
          <span className="text-sm text-white/60 tabular-nums">Pàg {data.page} de {data.num_pages}</span>
          <button type="button" disabled={!data.has_next} onClick={() => setPage(p => p + 1)} className="rd-btn rd-btn--ghost">Següent</button>
        </nav>
      )}
    </section>
  )
}
