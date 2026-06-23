/**
 * StaffTable — back-compat shim.
 *
 * The staff table/form kit now lives at `components/rd/surface.jsx`
 * (the rd light canon, staff-unification option B). This file re-exports
 * it byte-for-byte so existing importers keep working: public pages that
 * pull `Field`/`Select`, the shared `FilterPanel`, and `LastfmPanel`/
 * `MusicBrainzPanel`. Staff pages import from `components/rd/surface`
 * directly. Do NOT add new components here — add them to `rd/surface`.
 */
export {
  TableCard,
  Table,
  THead,
  Th,
  Td,
  Tr,
  EmptyState,
  Callout,
  Pill,
  Btn,
  Input,
  Textarea,
  Select,
  Pagination,
  PageHeader,
  Field,
} from "../rd/surface";
