/**
 * Snapshot guard for the publications table column contract.
 *
 * The backend serializer (`_serialize`) and this header list are two
 * halves of one contract; a reorder or rename here should be a
 * deliberate, reviewed change, not an accident. Pairs with the backend
 * `test_serialize_exposes_table_columns`.
 */
import { describe, it, expect } from 'vitest'
import { COLUMNS } from './publicacionsColumns'

describe('PublicacionsTable COLUMNS', () => {
  it('locks the column order required by llesca 2', () => {
    expect(COLUMNS).toEqual([
      'Data',
      'Canal',
      'Objectiu',
      'Setmana',
      'Estat',
      'Enllaç',
      'Accions',
    ])
  })
})
