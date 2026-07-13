# TopQuaranta — Project manifest

## What this project is

TopQuaranta exists to prove — weekly, publicly, measurably — that music
in Catalan is alive and growing.

Not as an opinion. As data.

Every Saturday a single number becomes visible: the top 40 songs, per
territory, computed from real listening on Last.fm. The number is
reproducible (every coefficient is logged publicly). The code is open.
The data license is CC BY.

That is the project. Everything else is scaffolding around that weekly
number.

## What the project will not become

The following are non-goals. They are listed explicitly so that
decisions about what to build next stay anchored.

### No monetization that would corrupt the measurement

The project has running costs (server, domain, time) and will likely
accept revenue streams aligned with its mission. What it **won't**
do is compromise the measurement to get that revenue.

**Acceptable revenue:**

- **Banner ads or sponsorships for cultural content in Catalan** — a
  new album by a Catalan-speaking artist, a festival, a cultural
  event, a book. The spot is a product of the same ecosystem the
  project measures; showing it doesn't conflict with the mission,
  it reinforces it.
- **Listed support from labels, cultural institutions, or public
  bodies** whose purpose is to fund Catalan music visibility, as
  long as they buy *placement, not position*.

**Unacceptable revenue:**

- **Selling the data** (the rankings, the signal, the user proposals,
  the derived insights) to labels, platforms, or third parties. The
  data is CC BY precisely so that nobody — including the operators —
  can build a moat around it. Free downloads already fulfil any
  legitimate research use case.
- **Selling the user list** (registered accounts, proposal history,
  email addresses) under any banner — that's the surveillance vector
  the next section forbids.
- **Any revenue tied to ranking outcomes.** A sponsor cannot pay to
  move an artist up, have a specific track featured as #1, suppress
  a competitor, or influence the coefficients. The ranking is the
  measurement, and the measurement is what makes the project worth
  anything. If that compromises, the project is worthless regardless
  of revenue.
- **Ads for non-musical / non-cultural content** that dilute the
  editorial register of the site.

If any revenue stream is added, it's documented here as an edit to
this section — so a reader can always check what the current
commitments are.

### No platform capture

TopQuaranta measures what plays. It does not host music, does not
stream, does not link-out aggressively to a specific platform. We
count Last.fm scrobbles; Last.fm is the instrument, not the subject.

If a new platform displaces Last.fm as the dominant listening
signal, we switch to it. The project is platform-agnostic by
construction.

### No surveillance

TopQuaranta will not:
- Track individual users beyond the minimum Django session needed for
  authentication.
- Add third-party analytics, pixels, or SDKs.
- Share visitor logs or IPs with anyone, including law enforcement,
  unless legally compelled.

A person visiting the ranking is a reader, not a product.

### No gatekeeping

The definition of eligibility (`docs/product/definition.md`) is:
*is the song sung in Catalan?* That is the only test. We will not add:
- Quality filters ("this artist isn't serious enough").
- Purity filters ("this isn't Catalan enough").
- Political filters.
- Territorial filters beyond "the artist is from somewhere in the
  Catalan-speaking area or sings in Catalan".

Decisions are recorded in `StaffAuditLog` and the anonymized history
is public. Anyone can see what was rejected and why.

### No sudden algorithm changes

Every coefficient lives in `ConfiguracioGlobal`. Every change to a
coefficient is recorded in `StaffAuditLog` with actor, timestamp, and
reason. The public `/com-funciona/historial/` page shows the full
history. A ranking computed last month is **reproducible today**
(R1: `TopSetmanal` stores `config_snapshot`).

This means we can improve the algorithm, but we can't quietly
re-weight the past to change what was published.

## What the project values

### Transparency over convenience

If a feature requires hiding how something is computed, we don't ship
it. `/com-funciona/` exists because "our algorithm is proprietary" is
incompatible with this project's mission.

### Slow, durable decisions

We are not trying to grow fast. We are trying to be right for a long
time. A decision that stabilises the ranking's credibility matters
more than a decision that brings more traffic this week.

### Human review over automation

An ML model helps us prioritise. It never decides. Every artist,
every track enters the ranking after a human (staff) has looked at
it and made a decision that's logged in `HistorialRevisio`.

### Open source, open data, open governance

- Code: [github.com/Top-Quaranta/TopQuaranta](https://github.com/Top-Quaranta/TopQuaranta).
- Data: CC BY 4.0 (`LICENSE-DATA.md`).
- Governance: every destructive or consequential staff action is
  logged in `StaffAuditLog`. Every coefficient change is public.

## How this document is maintained

This manifest can change. But each change is a deliberate, commit-level
event that a reader can find in `git log`. The no-go list above is the
current commitment, not a promise beyond it.

If you're considering a contribution that would cross one of the
no-go lines, open a discussion first. If a better reason emerges to
cross it, we'll revise this document in public.

---

*"La música en català, viva i mesurable" — footer of every page on
topquaranta.cat.*
