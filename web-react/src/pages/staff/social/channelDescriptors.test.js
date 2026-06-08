/**
 * Regression guard for the channel descriptors that drive ChannelView.
 *
 * The descriptors are the contract between the staff UI and the
 * per-channel staff endpoints: each channel's save/test/clear URLs and
 * the exact credential field names the backend reads. A rename or a
 * dropped channel here silently breaks the Mastodon/Bluesky/Telegram
 * views, so we lock the shape down.
 */
import { describe, it, expect } from 'vitest'
import { CHANNEL_DESCRIPTORS } from './channelDescriptors'

// The exact credential field names each staff endpoint expects (see
// web/api/staff/social/*). These are the backend contract — if a field
// is renamed on either side without the other, the save POSTs the wrong
// keys and the channel silently goes DRY-RUN.
const EXPECTED = {
  mastodon: {
    switchField: 'mastodon_actiu',
    platforms: ['mastodon'],
    fields: ['instance_url', 'access_token', 'handle'],
    required: ['instance_url', 'access_token'],
  },
  bluesky: {
    switchField: 'bluesky_actiu',
    platforms: ['bluesky'],
    fields: ['handle', 'app_password'],
    required: ['handle', 'app_password'],
  },
  telegram: {
    switchField: 'telegram_actiu',
    platforms: ['telegram'],
    fields: ['bot_token', 'chat_id'],
    required: ['bot_token', 'chat_id'],
  },
}

describe('CHANNEL_DESCRIPTORS', () => {
  it('covers the simple channels + newsletter (llesca 3)', () => {
    expect(Object.keys(CHANNEL_DESCRIPTORS).sort()).toEqual([
      'bluesky',
      'mastodon',
      'newsletter',
      'telegram',
    ])
  })

  it('every descriptor declares the 4-section schema keys', () => {
    for (const d of Object.values(CHANNEL_DESCRIPTORS)) {
      expect('section1' in d).toBe(true) // null or { kind }
      expect(d.kpis).toBeTruthy()
      expect(d.control).toBeTruthy()
      expect(d.analytics).toBeTruthy()
      expect(['exists', 'missing']).toContain(d.analytics.status)
    }
  })

  describe('newsletter', () => {
    const d = CHANNEL_DESCRIPTORS.newsletter
    it('is credential-less and is the section-1 channel', () => {
      expect(d.auth).toBeNull()
      expect(d.payloadKey).toBeNull()
      expect(d.section1).toEqual({ kind: 'newsletter' })
      expect(d.switchField).toBe('newsletter_actiu')
    })
    it('publishes only top_ppcc and has no post analytics', () => {
      expect(d.control.tipus).toEqual(['top_ppcc'])
      expect(d.analytics.status).toBe('missing')
      expect(d.kpis.subscriptors.status).toBe('exists')
    })
  })

  for (const [key, exp] of Object.entries(EXPECTED)) {
    describe(key, () => {
      const d = CHANNEL_DESCRIPTORS[key]

      it('keys itself consistently', () => {
        expect(d.key).toBe(key)
        expect(d.payloadKey).toBe(key)
        expect(d.switchField).toBe(exp.switchField)
        expect(d.platforms).toEqual(exp.platforms)
        expect(typeof d.nom).toBe('string')
      })

      it('wires the staff endpoints under /staff/social/<key>/', () => {
        expect(d.auth.saveEndpoint).toBe(`/staff/social/${key}/`)
        expect(d.auth.testEndpoint).toBe(`/staff/social/${key}/test/`)
        expect(d.auth.clearEndpoint).toBe(`/staff/social/${key}/clear/`)
        expect(d.auth.clearConfirm).toBeTruthy()
      })

      it('declares the exact credential fields the backend reads', () => {
        expect(d.auth.fields.map((f) => f.name)).toEqual(exp.fields)
        const required = d.auth.fields
          .filter((f) => f.required)
          .map((f) => f.name)
        expect(required).toEqual(exp.required)
        d.auth.fields.forEach((f) => {
          expect(f.label).toBeTruthy()
          expect(f.placeholder).toBeTruthy()
        })
      })

      it('renders summary + help without throwing', () => {
        // node-env: we don't mount, just assert they produce elements.
        expect(d.auth.summary({})).toBeTruthy()
        expect(d.auth.help).toBeTruthy()
      })
    })
  }
})
