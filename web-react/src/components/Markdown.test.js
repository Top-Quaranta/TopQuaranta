import { describe, expect, it } from 'vitest'
import { safeUrl } from './Markdown'

describe('Markdown safeUrl — link/image scheme sanitization', () => {
  it('keeps safe schemes', () => {
    expect(safeUrl('https://x.com/a')).toBe('https://x.com/a')
    expect(safeUrl('http://x.com')).toBe('http://x.com')
    expect(safeUrl('mailto:a@b.cat')).toBe('mailto:a@b.cat')
  })

  it('keeps relative + anchors', () => {
    expect(safeUrl('/artista/x')).toBe('/artista/x')
    expect(safeUrl('#secc')).toBe('#secc')
  })

  it('drops dangerous schemes', () => {
    expect(safeUrl('javascript:alert(1)')).toBe('')
    expect(safeUrl('JaVaScRiPt:alert(1)')).toBe('')
    expect(safeUrl('data:text/html,<script>')).toBe('')
    expect(safeUrl('vbscript:msgbox')).toBe('')
  })

  it('handles empty/null', () => {
    expect(safeUrl('')).toBe('')
    expect(safeUrl(null)).toBe('')
  })
})
