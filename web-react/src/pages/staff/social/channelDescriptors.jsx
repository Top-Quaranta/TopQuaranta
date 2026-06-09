/**
 * channelDescriptors — per-channel data for the shared ChannelView.
 *
 * Slice 1 of the distribution-views redistribution. A descriptor
 * declares everything the ChannelView template needs to paint a single
 * channel: header identity, the per-channel switch field on
 * ConfiguracioGlobal, the credentials payload key + form + endpoints,
 * and the SocialPost platforms that belong to it. Adding a channel — or
 * a credential field on one — means extending this map, not writing a
 * new page.
 *
 * `summary` / `help` are render functions (JSX) so each channel keeps
 * its own masked-credentials line and onboarding copy without the
 * template knowing the shape.
 */

export const CHANNEL_DESCRIPTORS = {
  instagram: {
    key: 'instagram',
    nom: 'Instagram',
    switchField: 'instagram_actiu',
    platforms: ['instagram_feed', 'instagram_story'],
    // Section 1 + Control are bespoke (credentials with test/clear, the
    // distribution phase, the story cap and the IG matrix), so they live
    // in a custom `InstagramSection` (like NewsletterSection) rather than
    // the generic credentials/control slots — which stay null here so the
    // generic sections don't double-render.
    section1: { kind: 'instagram' },
    kpis: {
      enviaments: { label: 'Enviaments', status: 'exists' },
      seguidors: { label: 'Seguidors', status: 'exists' },
      abast: { label: 'Abast', status: 'missing' },
    },
    control: null,
    auth: null,
    analytics: { status: 'exists', available: ['likes', 'reach', 'impressions'] },
  },
  mastodon: {
    key: 'mastodon',
    nom: 'Mastodon',
    switchField: 'mastodon_actiu',
    payloadKey: 'mastodon',
    platforms: ['mastodon'],
    // 4-section schema (llesca 3). Each block declares FONT + ESTAT; the
    // view paints an honest dash for `status: 'missing'`, never a fake 0.
    section1: null,
    kpis: {
      enviaments: { label: 'Enviaments', status: 'exists' },
      seguidors: { label: 'Seguidors', status: 'exists' },
      abast: { label: 'Abast', status: 'missing' }, // API doesn't expose reach
    },
    control: {
      tipus: ['top_ppcc', 'top_territorial', 'nous_singles', 'nous_albums'],
      nota: 'feed-only; tots els tipus del calendari (implícit al codi)',
    },
    analytics: { status: 'exists', available: ['likes', 'replies', 'shares'] },
    auth: {
      saveEndpoint: '/staff/social/mastodon/',
      testEndpoint: '/staff/social/mastodon/test/',
      clearEndpoint: '/staff/social/mastodon/clear/',
      clearConfirm:
        'Esborrar credencials Mastodon? El cron passarà a mode DRY-RUN per a aquest canal.',
      fields: [
        {
          name: 'instance_url',
          label: 'Instància',
          placeholder: 'https://mastodont.cat',
          required: true,
        },
        {
          name: 'access_token',
          label: 'Access token',
          placeholder: 'access_token',
          type: 'password',
          required: true,
        },
        { name: 'handle', label: 'Handle (opcional)', placeholder: 'handle (opcional)' },
      ],
      summary: (p) => (
        <>
          <strong>{p.handle || '(handle no establert)'}</strong> @{' '}
          <code>{p.instance_url}</code> · token <code>{p.token_masked}</code>
          {p.updated_by && (
            <>
              {' '}· per <strong>{p.updated_by}</strong>
            </>
          )}
        </>
      ),
      help: (
        <>
          Sense credencials. Crea una «App» a la teva instància (Settings →
          Development → New Application, scopes:{' '}
          <code>write:media write:statuses</code>) i enganxa el token.
        </>
      ),
    },
  },

  bluesky: {
    key: 'bluesky',
    nom: 'Bluesky',
    switchField: 'bluesky_actiu',
    payloadKey: 'bluesky',
    platforms: ['bluesky'],
    section1: null,
    kpis: {
      enviaments: { label: 'Enviaments', status: 'exists' },
      seguidors: { label: 'Seguidors', status: 'exists' },
      abast: { label: 'Abast', status: 'missing' },
    },
    control: {
      tipus: ['top_ppcc', 'top_territorial', 'nous_singles', 'nous_albums'],
      nota: 'feed-only; tots els tipus del calendari (implícit al codi)',
    },
    analytics: { status: 'exists', available: ['likes', 'replies', 'shares'] },
    auth: {
      saveEndpoint: '/staff/social/bluesky/',
      testEndpoint: '/staff/social/bluesky/test/',
      clearEndpoint: '/staff/social/bluesky/clear/',
      clearConfirm:
        'Esborrar credencials Bluesky? El cron passarà a mode DRY-RUN per a aquest canal.',
      fields: [
        {
          name: 'handle',
          label: 'Handle',
          placeholder: 'topquaranta.bsky.social',
          required: true,
        },
        {
          name: 'app_password',
          label: 'App password',
          placeholder: 'app password',
          type: 'password',
          required: true,
        },
      ],
      summary: (p) => (
        <>
          <strong>@{p.handle}</strong> · contrasenya <code>{p.password_masked}</code>
          {p.did && (
            <>
              {' '}· DID <code className="text-[10px]">{p.did}</code>
            </>
          )}
          {p.updated_by && (
            <>
              {' '}· per <strong>{p.updated_by}</strong>
            </>
          )}
        </>
      ),
      help: (
        <>
          Sense credencials. Crea una <strong>App Password</strong> a{' '}
          <a
            className="underline"
            href="https://bsky.app/settings/app-passwords"
            target="_blank"
            rel="noopener"
          >
            bsky.app/settings/app-passwords
          </a>{' '}
          (NO la contrasenya del compte).
        </>
      ),
    },
  },

  telegram: {
    key: 'telegram',
    nom: 'Telegram',
    switchField: 'telegram_actiu',
    payloadKey: 'telegram',
    platforms: ['telegram'],
    section1: null,
    kpis: {
      enviaments: { label: 'Enviaments', status: 'exists' },
      seguidors: { label: 'Membres', status: 'exists' }, // getChatMemberCount
      abast: { label: 'Abast', status: 'missing' },
    },
    control: {
      tipus: ['top_ppcc', 'top_territorial', 'nous_singles', 'nous_albums'],
      nota: 'feed-only; tots els tipus del calendari (implícit al codi)',
    },
    // Bot API exposes no per-message engagement → no post analytics.
    analytics: { status: 'missing', available: [] },
    auth: {
      saveEndpoint: '/staff/social/telegram/',
      testEndpoint: '/staff/social/telegram/test/',
      clearEndpoint: '/staff/social/telegram/clear/',
      clearConfirm:
        'Esborrar credencials Telegram? El cron passarà a mode DRY-RUN per a aquest canal.',
      fields: [
        {
          name: 'bot_token',
          label: 'Bot token',
          placeholder: 'bot_token (de @BotFather)',
          type: 'password',
          required: true,
        },
        {
          name: 'chat_id',
          label: 'Canal',
          placeholder: '@canal o ID numèric',
          required: true,
        },
      ],
      summary: (p) => (
        <>
          <strong>{p.bot_username ? `@${p.bot_username}` : '(bot)'}</strong> → canal{' '}
          <code>{p.chat_id}</code> · token <code>{p.token_masked}</code>
          {p.updated_by && (
            <>
              {' '}· per <strong>{p.updated_by}</strong>
            </>
          )}
        </>
      ),
      help: (
        <>
          Sense credencials. Parla amb{' '}
          <a className="underline" href="https://t.me/BotFather" target="_blank" rel="noopener">
            @BotFather
          </a>
          , fes <code>/newbot</code>, copia el token. Després afegeix el bot al teu
          canal com a admin amb permís de <em>Post messages</em> i fica el handle
          (<code>@topquaranta</code>) com a chat_id.
        </>
      ),
    },
  },

  newsletter: {
    key: 'newsletter',
    nom: 'Newsletter',
    switchField: 'newsletter_actiu',
    // No per-channel credentials payload: the newsletter uses the
    // server-side SMTP (EMAIL_HOST), not a row in /staff/social/.
    payloadKey: null,
    platforms: ['newsletter'],
    auth: null,
    // Section 1 (the on-demand draft surface) is the newsletter's
    // first-class management area; the credentials slot is skipped.
    section1: { kind: 'newsletter' },
    kpis: {
      enviaments: { label: 'Enviaments', status: 'exists' },
      subscriptors: { label: 'Subscriptors', status: 'exists' }, // PerfilUsuari.vol_newsletter
    },
    control: {
      tipus: ['top_ppcc'],
      nota: 'newsletter = només top_ppcc (no segueix el calendari)',
    },
    // No metrics handler (Brevo stats not wired) → honest dash, not 0.
    analytics: { status: 'missing', available: [] },
  },
}
