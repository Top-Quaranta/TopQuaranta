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
  mastodon: {
    key: 'mastodon',
    nom: 'Mastodon',
    switchField: 'mastodon_actiu',
    payloadKey: 'mastodon',
    platforms: ['mastodon'],
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
}
