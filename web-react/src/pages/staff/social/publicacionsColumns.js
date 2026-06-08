/**
 * Column header contract for the publications table (llesca 2).
 *
 * Kept in its own module (not exported from the component file) so
 * fast-refresh stays component-only, and so the snapshot test can lock
 * the order without importing a component. Pairs with the backend
 * `_serialize` row contract.
 */
export const COLUMNS = [
  'Data',
  'Canal',
  'Objectiu',
  'Setmana',
  'Estat',
  'Enllaç',
  'Accions',
]
