/**
 * StaffArtistesAfinsPage — /staff/artistes/afins
 *
 * Read-only: artists who have engaged with us at least once. Every
 * column is counted by the backend from tables that already record the
 * interaction; nothing is edited or stored here.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import {
  EmptyState,
  PageHeader,
  Pill,
  Table,
  TableCard,
  Td,
  Th,
  THead,
  Tr,
} from '../../components/rd/surface'

const res = <span className="text-white/40">—</span>

function Row({ a }) {
  return (
    <Tr>
      <Td>
        <Link
          to={`/staff/artistes/${a.pk}`}
          className="font-semibold underline hover:text-tq-yellow"
        >
          {a.nom}
        </Link>
        {!a.aprovat && <span className="ml-2 text-[11px] text-white/40">no aprovat</span>}
      </Td>
      <Td>
        {a.collabs_acceptades > 0 ? (
          <Pill tone="green">
            {a.collabs_acceptades} de {a.collabs_convidades}
          </Pill>
        ) : a.collabs_convidades > 0 ? (
          <span className="text-white/40">0 de {a.collabs_convidades}</span>
        ) : (
          res
        )}
      </Td>
      <Td>{a.ultima_collab || res}</Td>
      <Td>{a.reaccions_sonda > 0 ? <Pill tone="yellow">{a.reaccions_sonda}</Pill> : res}</Td>
      <Td>
        {a.dm_missatges + a.dm_mencions + a.dm_reaccions > 0 ? (
          <span className="whitespace-nowrap text-xs">
            {a.dm_mencions > 0 && <Pill tone="green">{a.dm_mencions} mencions</Pill>}{' '}
            {a.dm_missatges > 0 && <Pill tone="yellow">{a.dm_missatges} missatges</Pill>}{' '}
            {a.dm_reaccions > 0 && <Pill tone="gray">{a.dm_reaccions} ♥</Pill>}
          </span>
        ) : (
          res
        )}
      </Td>
      <Td>{a.te_gestor ? <Pill tone="green">gestor</Pill> : res}</Td>
      <Td>{a.proposat_per_usuari ? <Pill tone="gray">proposat</Pill> : res}</Td>
      <Td>
        {a.instagram_url ? (
          <a
            href={a.instagram_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-tq-yellow underline whitespace-nowrap"
          >
            Instagram ↗
          </a>
        ) : (
          res
        )}
      </Td>
    </Tr>
  )
}

export default function StaffArtistesAfinsPage() {
  const [files, setFiles] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .get('/staff/artistes/afins/')
      .then(d => setFiles(d.results))
      .catch(e => setError(e.message))
  }, [])

  const subtitle =
    files === null
      ? 'Carregant…'
      : `${files.length} artistes que han respost almenys una vegada: una col·laboració acceptada, una reacció a una story, un missatge directe, un gestor a la web o una proposta d'un usuari.`

  return (
    <section>
      <PageHeader title="Artistes afins" subtitle={subtitle} />
      {error && <p className="text-sm text-red-300 mb-4">{error}</p>}
      <TableCard>
        <Table>
          <THead>
            <tr>
              <Th>Artista</Th>
              <Th title="Invitacions de col·laboració a Instagram acceptades, de les enviades">
                Col·laboracions
              </Th>
              <Th>Última</Th>
              <Th title="Stories «cançó del dia» amb un abast fora del normal">Reaccions</Th>
              <Th title="Missatges directes d'Instagram: stories seues on ens mencionen, missatges que ens han escrit i reaccions als nostres">
                Missatges directes
              </Th>
              <Th>Web</Th>
              <Th>Origen</Th>
              <Th>Instagram</Th>
            </tr>
          </THead>
          <tbody>
            {files?.length === 0 && (
              <tr>
                <td colSpan={8}>
                  <EmptyState>Encara no hi ha cap artista amb senyals.</EmptyState>
                </td>
              </tr>
            )}
            {files?.map(a => (
              <Row key={a.pk} a={a} />
            ))}
          </tbody>
        </Table>
      </TableCard>
    </section>
  )
}
