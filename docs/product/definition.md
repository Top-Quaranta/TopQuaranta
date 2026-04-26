# What counts as "music in Catalan"

TopQuaranta ranks *music in Catalan*. That sounds obvious until you look
at concrete cases: a Valencian band with a bilingual album, a track
with 80% Catalan and a chorus in English, a live version re-released
in Spanish, a duet between a Catalan singer and a non-Catalan
collaborator. Without an explicit definition, every edge case becomes
an arbitrary decision.

This document is the definition. It is deliberately narrower than the
informal sense of "Catalan music" so that the ranking stays a faithful
measurement of a single variable — the vitality of the language in
music — rather than a broader cultural proxy.

## The core rule

A track is eligible if **the primary vocal delivery is in Catalan**.
Primary vocal delivery means the full sung text, not samples, inserts,
or spoken interludes.

Instrumental tracks have no vocal delivery at all, so by this same
rule they are not in Catalan and therefore not eligible. They are
rejected with `motiu="no_catala"` — no separate "instrumental"
motiu is needed. A track with no lyrics can't be measured for
language vitality by any stretch of the definition.

## Operational criteria

A track is marked `verificada=True` (eligible for the ranking) when it
satisfies all of:

1. **Language**: the complete lyrics are in Catalan — any variant
   (eastern, western, balearic, algueresc, etc.). Occasional words or
   phrases in another language (loan words, proper names, a single
   line in the bridge) do not disqualify.
2. **Release**: the track was released in the last 12 months
   (`DIES_CADUCITAT = 365`). This ensures the ranking measures current
   music, not accumulated catalog.
3. **Artist identity**: the track is attributed to at least one
   `Artista` marked `aprovat=True` who represents themselves as a
   Catalan-language artist.

## Edge cases — the rulebook

### Bilingual tracks

Tracks with sustained non-Catalan sections (say, a rapped verse in
Spanish taking up a third of the song) are **not** eligible.

A single line, a sampled English phrase, or a chant is fine. Rule of
thumb: if the non-Catalan section could be replaced with silence
without changing what the song *is*, the track is eligible.

### Multiple versions

The original release is the canonical version. A Spanish re-recording
of the same track is a different `Canco` and must meet the criteria
independently (it won't, for the Spanish version).

If a track is released *simultaneously* in Catalan and another
language by the same artist, only the Catalan version enters the
ranking.

### Collaborations

A collaboration is eligible if the **majority** of the vocal delivery
is in Catalan and the lead credit belongs to a Catalan-language
artist. A guest verse in Spanish or Portuguese inside an otherwise
Catalan song does not disqualify, but it's a signal to check the
attribution — the guest artist may need their own `PropostaArtista`
review rather than automatic addition as a collaborator.

### Covers and interpretations

A Catalan cover of a non-Catalan original is eligible if the cover is
fully sung in Catalan. A non-Catalan cover of a Catalan original is
not — the artist is performing in a different language now.

### Generative / traditional / liturgical

Folk songs, religious music, traditional songs all qualify if sung in
Catalan. Generative AI tracks are eligible when the output is
attributable to an identifiable approved `Artista`; anonymous AI
churn is not (there's no artist to credit).

### Territorial scope

The ranking covers the Catalan-speaking territories (Països Catalans):
Catalunya, País Valencià, Illes Balears, Catalunya Nord, l'Alguer,
Andorra, and the Franja. A Catalan-language artist based outside
these territories (say, a Catalan speaker in Madrid or Berlin)
is eligible — the variable is the language, not the geography.

The per-territory view is derived from the artist's declared
`ArtistaLocalitat`, not from the song's lyrics.

## Governance

### Who decides

The **staff panel** is the arbiter. Staff members:

1. Review every new artist before `aprovat=True`.
2. Review every new track before `verificada=True`.
3. Record the decision in `HistorialRevisio` with a `motiu` field.

Every decision is logged in `StaffAuditLog` and the anonymized
history is public at `/com-funciona/historial/`.

### The ML pre-classifier

An ML model (`music/ml.py`) pre-classifies new tracks A/B/C to
prioritize human review. **The model does not decide** — it accelerates
the queue. Class A is likely-eligible and queued first; class C is
likely-ineligible and queued last. Every track is still reviewed by a
human before entering the ranking.

### Appeals

An artist or user who believes a track was wrongly rejected can
reopen the question by submitting a `PropostaArtista` with the
justification. Staff will review and, if the original `HistorialRevisio`
was wrong, flip `verificada` and record the reasoning. The audit log
preserves both decisions.

## What this definition is not

- Not a judgment about artistic quality or cultural value.
- Not a measure of an artist's "Catalanness" — many Catalan-speaking
  artists release in multiple languages, and we only count their
  Catalan-language work.
- Not a gatekeeping tool for what counts as "real" Catalan music —
  a song in a regional variant counts as much as one in the most
  standardized register.

The single question is: *is this song sung in Catalan?* Everything
else follows.
