# SSH key policy — server ↔ GitHub

## Current state (2026-04-17, verified)

- `git@github.com:miquelmatoses/TopQuaranta.git` — remote origin uses SSH.
- `~/.ssh/id_ed25519_github` — ed25519 deploy key registered as **read-only** on GitHub. Used by `~/.ssh/config` → `Host github.com`.
- No Personal Access Token anywhere in `.git/config`, `~/.netrc`, environment variables, or the repo itself.

Rotation from the old `https://miquelmatoses:ghp_***@github.com/…` HTTPS-with-PAT
setup completed in Phase 9, Session 1 (finding **S2**). This document
ensures the property is preserved on every future redeploy or server move.

## Rules

1. **Never** commit a PAT to git, include one in `.env`, or set one in
   `.git/config` (`url = https://…:ghp_…@github.com/…`).
2. **Never** store a GitHub PAT in `~/.netrc` either — same exposure surface.
3. All CI / deploy authentication runs through SSH deploy keys, not PATs.
4. Deploy keys are **read-only** by default. If a workflow genuinely
   needs write access (e.g., a release bot), grant a *separate* read/write
   key on that specific workflow's context — never share one key across
   read-only and write usage.
5. The `.ssh/id_ed25519_github{,.pub}` pair is machine-local. If the
   server is decommissioned, the disk **must** be securely wiped or
   physically destroyed before disposal — the private key lives there
   in plain text (protected only by filesystem permissions `600`).

## Rotation procedure

Run every 12 months or any time a server is swapped / a laptop with the
key is lost:

```bash
# 1. Generate a new key pair on the server.
ssh-keygen -t ed25519 -C "topquaranta-$(date +%Y%m%d)" \
    -f ~/.ssh/id_ed25519_github_new -N ''

# 2. Add the new pubkey as a deploy key on the GitHub repo (Settings →
#    Deploy keys → Add deploy key).  Leave "Allow write access" unchecked.
cat ~/.ssh/id_ed25519_github_new.pub

# 3. Point ~/.ssh/config at the new key (edit IdentityFile line).

# 4. Test:
ssh -T git@github.com  # should say "Hi miquelmatoses/TopQuaranta!"
cd ~/app && git fetch

# 5. Once confirmed, delete the old deploy key on GitHub and remove
#    the old key files locally:
shred -u ~/.ssh/id_ed25519_github
mv ~/.ssh/id_ed25519_github_new     ~/.ssh/id_ed25519_github
mv ~/.ssh/id_ed25519_github_new.pub ~/.ssh/id_ed25519_github.pub
```

## Verification

Paste into a shell as user `topquaranta`:

```bash
grep -E 'ghp_|://.+:.+@github' ~/.git/config ~/app/.git/config ~/.netrc 2>/dev/null \
    && echo "FAIL: credential material found" \
    || echo "OK: no PAT in git/netrc"
```

Should always print `OK: no PAT in git/netrc`.
