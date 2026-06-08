/**
 * NewsletterDraftPage — /staff/social/esborrany
 *
 * Legacy review route kept for the cron email links. Reads `?setmana=`
 * and renders the shared NewsletterDraftEditor. The full first-class
 * surface (week selector + on-demand generate + KPIs) lives at
 * /staff/social/newsletter (the Newsletter channel view, llesca 3).
 */
import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/staff/StaffTable'
import NewsletterDraftEditor from './social/NewsletterDraftEditor'

export default function NewsletterDraftPage() {
  const [params] = useSearchParams()
  const setmana = params.get('setmana') || ''
  return (
    <section className="space-y-4">
      <PageHeader
        title="Esborrany de newsletter"
        subtitle="Revisió de l'esborrany setmanal (opt-out: s'envia diumenge si no es cancel·la)."
      />
      <div className="bg-white text-tq-ink rounded-lg shadow-md p-4 md:p-6 max-w-3xl">
        <NewsletterDraftEditor setmana={setmana} />
      </div>
    </section>
  )
}
