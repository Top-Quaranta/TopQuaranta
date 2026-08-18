# Inventari de la suite de tests — 1708 tests

**Total: P=1416 · D=142 · M=150**  (P = promesa, es queda · D = detector de canvis, fora · M = promesa mal ancorada, es reescriu)

| àrea | tests | P | D | M | fora+reescriu |
|---|---|---|---|---|---|
| social | 411 | 302 | 55 | 54 | 26 % |
| web | 346 | 315 | 14 | 17 | 8 % |
| ingesta | 280 | 254 | 8 | 18 | 9 % |
| music | 212 | 175 | 23 | 14 | 17 % |
| comptes | 147 | 106 | 18 | 23 | 27 % |
| analytics | 131 | 113 | 5 | 13 | 13 % |
| topquaranta | 109 | 89 | 14 | 6 | 18 % |
| ranking | 72 | 62 | 5 | 5 | 13 % |


## social

- `test_afirmacions_verificables.py` — 7 tests, tot P

### `social/tests/test_ambassador.py` — 4 tests · P 3 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_caption_without_position_omits_ordinal` | **M** | keep 'no ordinal when unknown'; drop exact copy «Manel entra al Top» |  |

### `social/tests/test_artist_join.py` — 24 tests · P 17 · D 4 · M 3

| test | col | raó | incident |
|---|---|---|---|
| `test_feed_list_uses_artistes_noms` | **D** | docstring admits it does not test what it claims; dup of three_names_fit_full |  |
| `test_join_artists_text_only_first_fits` | **M** | pins off-by-one output «Mari…»; check len≤max_chars and endswith … instead |  |
| `test_join_artists_two_lines_greedy_maximizes_line1` | **D** | pins greedy vs balanced packing (algorithm choice); a balanced split would be an improvement |  |
| `test_pack_greedy_line_helper_is_incremental` | **D** | unit test of private helper _pack_greedy_line; behaviour covered via _join_artists |  |
| `test_word_wrap_is_opportunistic_not_forced` | **M** | conditional `if len(parts)==2` makes it near-vacuous; assert unconditionally that no name is broken |  |
| `test_word_wrap_split_with_realistic_data` | **M** | pins exact split point Arde/Bogotá; check lines fit and any split is at a word boundary |  |
| `test_word_wrap_splits_when_line2_would_need_ellipsis` | **D** | docstring admits the setup does not trigger word-wrap; only asserts ellipsis — dup of stress_39 |  |
- `test_bluesky_upload_retry.py` — 3 tests, tot P

### `social/tests/test_captions.py` — 7 tests · P 5 · D 0 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_caption_top_fallback_on_engine_error` | **M** | promise = never publish empty on engine bug; drop exact log text and legacy header copy, keep non-empty + entries listed |  |
| `test_caption_top_uses_narrative_engine` | **M** | checks engine path via copy tokens (' setmana','cim'); assert hero block present / differs from legacy shape | post-mortems/2026-05-20-narrative-engine-collapsed.md |

### `social/tests/test_catalan_with_preposition.py` — 18 tests · P 14 · D 4 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_bare_article_token_falls_back_to_apostrof_elision` | **D** | pins arguably-wrong «d'El»; docstring says 'pin the behaviour' |  |
| `test_empty_name` | **D** | pins «de » with trailing space — odd behaviour, not a promise |  |
| `test_split_article_detects_titlecase` | **D** | private helper; behaviour already asserted through with_preposition tests |  |
| `test_split_article_ignores_non_articles` | **D** | private helper; dup of no-article cases via public API |  |

### `social/tests/test_collaboradors.py` — 19 tests · P 18 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_dataclass_shapes` | **D** | tautology on a dataclass constructor |  |

### `social/tests/test_editorial_fixes.py` — 10 tests · P 8 · D 2 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_hero_templates_plural_with_7_days` | **D** | dup of test_hero_templates_say_1_dia_not_1_dies (plural follows trivially) |  |
| `test_pick_short_no_duplicates_unchanged` | **D** | control case pinned to exact join copy; nothing beyond llista_amb_i |  |

### `social/tests/test_feed_artwork_moviment.py` — 18 tests · P 15 · D 2 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_duotone_mosaic_grid_shape` | **D** | tautology over a private grid mapping table |  |
| `test_duotone_veil_stops_and_size` | **M** | veil alpha stops (0.66/0.16/0.72) mirror constants; keep size+RGBA and 'veil heavier at edges than centre' |  |
| `test_moviment_flag_off_creates_no_row` | **D** | strict subset of test_moviment_flag_off_no_invitation |  |

### `social/tests/test_feed_redesign.py` — 19 tests · P 9 · D 7 · M 3

| test | col | raó | incident |
|---|---|---|---|
| `test_album_band_top_matches_fitxa` | **D** | pixel row of band top vs tokens |  |
| `test_album_title_never_ellipsised` | **M** | only asserts canvas size — vacuous; should check no '…' drawn / title fits |  |
| `test_chip_shows_recoloured_silhouette_not_text` | **M** | keep 'accent silhouette present in chip'; drop optH height and centre pins |  |
| `test_cover_masthead_ink_anchored_to_fitxa` | **D** | pixel cap-top pins ±8 vs fitxa tokens; change detector |  |
| `test_cover_singles_masthead_matches_albums` | **D** | pixel pins; dup of masthead test |  |
| `test_render_feed_novetats_uses_redesign` | **D** | monkeypatched delegation check (call-shape); any restructuring of builders kills it |  |
| `test_singles_blinds_ppcc_row_count` | **D** | pixel-count dup of test_singles_blinds_ppcc |  |
| `test_singles_row_top_and_pitch_match_fitxa` | **D** | row y0/pitch pixel pins |  |
| `test_territori_maps_cno_to_nord` | **D** | pins abbr copy 'NOR'; abbr code path is gone per test_chip docstring |  |
| `test_territori_unknown_falls_back_to_green` | **M** | exact fallback RGB; assert it never raises and returns valid colours |  |

### `social/tests/test_freshness.py` — 9 tests · P 7 · D 2 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_boolean_wrapper_matches_verdict` | **D** | trivial wrapper equivalence |  |
| `test_living_artist_recent_release_passes` | **D** | dup of test_fresh_original_release_is_verified |  |
- `test_ig_handles_rebutjats.py` — 6 tests, tot P
- `test_ig_publish_robustness.py` — 8 tests, tot P

### `social/tests/test_instagram_collaborator_tagging.py` — 17 tests · P 15 · D 0 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_slide_tags_round_robin_when_multiple_entries_have_collabs` | **M** | pins exact index order incl. renderer reversal; assert 'all principals before any 2nd collab' by rank sets |  |
| `test_slide_tags_top_mirror_renderer_countdown_order` | **M** | real bug (tags mismatched artists) but hardcodes renderer chunking; derive expected chunks from the renderer | docstring: pre-2026-06 tag/slide mismatch |

### `social/tests/test_matriu_dia_setmana.py` — 5 tests · P 2 · D 0 · M 3

| test | col | raó | incident |
|---|---|---|---|
| `test_get_matriu_exposes_dies_publicacio` | **M** | keep 'no dia_setmana leaked' + 'dies_publicacio == publish_weekdays_for'; drop literal weekdays |  |
| `test_newsletter_is_sunday_for_ppcc_only` | **M** | 'newsletter only PPCC' is a promise; Sunday==6 should be checked against deploy/cron.topquaranta, not a literal |  |
| `test_push_channels_follow_calendar` | **M** | hardcodes weekday numbers mirroring CALENDARI; assert indicator == derived from social.calendari.CALENDARI |  |

### `social/tests/test_matriu_distribucio.py` — 12 tests · P 10 · D 0 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_matrix_excludes_web_and_rss` | **M** | exact canal set breaks when a channel is added; keep 'rss/web not in matrix, rss governed by own switch' |  |
| `test_seed_creates_todays_combos` | **M** | len(rows)==17 breaks on any new combo; assert every push canal×tipus seeded on, drop the count |  |
- `test_mencions.py` — 4 tests, tot P

### `social/tests/test_multi_channel.py` — 9 tests · P 6 · D 3 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_caption_short_bluesky_300_char_cap` | **D** | dup of test_captions::test_caption_short_bluesky_respects_300_char_limit |  |
| `test_caption_short_top_fits_under_500_chars` | **D** | dup of test_captions::test_caption_short_mastodon_respects_500_char_limit (weaker, no DB) |  |
| `test_publicar_canal_telegram_dry_run` | **D** | dup of mastodon dry-run with platform swapped |  |

### `social/tests/test_narrative.py` — 48 tests · P 41 · D 2 · M 5

| test | col | raó | incident |
|---|---|---|---|
| `test_build_novetats_enriches_flags_and_composes_narrative` | **M** | flags + narrative path are promises; drop exact hashtag list equality |  |
| `test_composer_bluesky_respects_300_chars` | **D** | dup of test_bluesky_never_exceeds_300_with_long_artist_names (weaker) |  |
| `test_composer_top5_excludes_hero_canco` | **D** | docstring admits it passes by construction; asserts only non-empty |  |
| `test_detect_a13_top1_return_with_gap_2` | **M** | near-dup of gap_5 pinned on severity 5; fold into one gap test on gap value |  |
| `test_detect_a13_top1_return_with_gap_5` | **M** | severity 8 magic number; keep fires + gap_setmanes + str |  |
| `test_detect_a3_fall_from_top1` | **M** | asserts mostly the magic severity 4; check fires + ordinal posicio_nova |  |
| `test_hero_has_nine_codes_three_lengths_fifteen_entries_each` | **M** | exact key set + 15/6 counts break on any new detector; assert 3 tiers with ≥4 entries per code |  |

### `social/tests/test_narrative_alpha.py` — 10 tests · P 6 · D 3 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_novetats_hashtags_titlecase` | **M** | Exact list equality is tautology of the constant; keep only TitleCase/no-space/#TopQuaranta property |  |
| `test_scenario_subject_tuple` | **D** | Tests a private helper's tuple shape; no promise, pure implementation mirror |  |
| `test_select_slots_degenerate_single_subject` | **D** | dup of test_select_slots_only_two_distinct_no_forced_tertiary (weaker case) |  |
| `test_select_slots_empty` | **D** | Trivial empty-input case; no promise |  |

### `social/tests/test_narrative_scenarios_new.py` — 4 tests · P 2 · D 1 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_hero_bank_contains_four_new_scenarios` | **D** | Bank-key presence: dies the day a scenario is renamed/merged; other tests exercise them |  |
| `test_instagram_feed_uses_tertiary_when_three_scenarios_given` | **M** | Promise (tertiary surfaces on IG) but `len(phrase_ids)==3` pins internals; keep only "Third Song in text" | decisions/0008-narrative-detectors-expanded.md |

### `social/tests/test_novetats.py` — 14 tests · P 8 · D 4 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_bank_all_codes_have_three_tiers` | **M** | Promise that every code has usable tiers, but `>=2` per tier is a bank-size pin; assert non-empty |  |
| `test_composer_is_narrative_not_skeleton` | **M** | Promise (no legacy skeleton, artists named) but exact hashtag list is a tautology; drop that assert |  |
| `test_empty_items_no_scenarios` | **D** | Trivial empty case |  |
| `test_severity_order_n1_over_n2` | **D** | Pins today's severity numbers (6>5); an editorial re-weighting kills it |  |
| `test_subject_ids_album_focal` | **D** | Internal data-shape (canco_id None) pin; dedup promise already covered by test_composer_dedups_by_artist |  |
| `test_thin_wrappers_pin_tipus` | **D** | Only asserts non-empty text from thin wrappers; smoke of nothing |  |
- `test_ordinal_ca.py` — 3 tests, tot P

### `social/tests/test_payload_collab_slugs.py` — 3 tests · P 2 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_build_top_no_regression_on_legacy_keys` | **M** | Exact key-set equality dies on every additive field; assert legacy keys are a SUBSET and keep values |  |

### `social/tests/test_pollar_colaboracions_ig.py` — 5 tests · P 4 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_fresh_pending_untouched_and_no_graph_dependency` | **M** | `hasattr(mod,"instagram_client")` pins module imports; keep only "fresh pendent untouched"; dup of first test otherwise |  |

### `social/tests/test_publicar_social.py` — 26 tests · P 21 · D 2 · M 3

| test | col | raó | incident |
|---|---|---|---|
| `test_force_republishes_even_if_publicat` | **M** | --force promise but only asserts "renderitzades" in stdout; assert the post was re-rendered/re-processed |  |
| `test_kill_switch_short_circuits` | **M** | Kill-switch promise but asserts stdout text "Kill switch"; assert no SocialPost/side effect instead |  |
| `test_no_phase_gate_message` | **D** | Asserts absence of a removed feature's output text ("fase"); dead-code detector |  |
| `test_slide_alts_top_list_lists_entries_with_positions` | **M** | Alt lists entries (promise) but pins exact copy "Posicions 1 a 10"/"X de Y"; assert names+positions present |  |
| `test_slide_tags_top_alternates_x_columns` | **D** | ">=3 distinct X" pins the zigzag layout, cosmetic; bounds already checked above |  |

### `social/tests/test_publicar_social_collaboradors.py` — 6 tests · P 4 · D 0 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_flag_on_attaches_pool_and_writes_rows` | **M** | Promise (pool attached, rows written) but pins exact cold-start order [p1,c1,p2]; assert 3 from pool + rows match sent | decisions/0015-ig-collaborator-invitations.md |
| `test_guard_substitutes_bad_handle` | **M** | Non-blocking guard promise; pins exact substitute order + stdout "descartat: c1"; assert bad dropped, post publicat, rows==sent | decisions/0015-ig-collaborator-invitations.md |

### `social/tests/test_renderer_jpg_cover.py` — 3 tests · P 2 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_feed_list_slides_still_render` | **D** | dup of test_feed_top_outputs_jpeg (weaker) |  |

### `social/tests/test_renderer_ppcc_stories.py` — 17 tests · P 8 · D 4 · M 5

| test | col | raó | incident |
|---|---|---|---|
| `test_hero_slide_empty_headline_falls_back` | **M** | Empty headline must not crash and still paint; palette-pinned oracle → luminance oracle |  |
| `test_hero_slide_receives_scenario_synthesis` | **M** | Hero paints headline (promise) but "yellow>1000" pins the palette; use the luminance oracle |  |
| `test_intro_is_green_with_big_yellow_forty` | **D** | Pins today's colours (green field, yellow 40); a redesign kills it; painted-ness covered by the oracle |  |
| `test_outro_is_yellow_without_slate_card` | **D** | Pins today's colour design (yellow dominates, no slate); dup of test_story_fidelity::test_outro_is_yellow_dominant |  |
| `test_ppcc_palette_unchanged` | **D** | Exact hex/palette pin ("byte-identical" baseline); dies on any palette change |  |
| `test_ppcc_story_set_handles_short_top` | **M** | Promise: short top doesn't crash; drop the ==7 pin |  |
| `test_ppcc_story_set_outputs_8_jpeg_slides` | **M** | Format/size/weight is a promise; the hard "8 slides" is a design pin — assert story size, JPEG, weight, len>0 |  |
| `test_ppcc_story_set_skips_novetats_when_empty` | **M** | Promise: no novetats slide when empty; assert relative (one fewer than with novetats), not ==7 |  |
| `test_ppcc_story_structure` | **D** | Spies builder call ORDER; pure change detector on the orchestrator |  |

### `social/tests/test_simular_colaboradors_ig.py` — 2 tests · P 0 · D 0 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_candidate_status_reasons` | **M** | Category/eligibility promises OK; exact motiu strings ("mai convidat (B)") are copy pins — assert cat+elig only | decisions/0015-ig-collaborator-invitations.md |
| `test_dry_run_reports_and_writes_nothing` | **M** | Promise "dry-run writes nothing" is P; exact selection order + JSON keys pin the report shape — keep count==0 + P3 sense_username |  |
- `test_smoke_cycle_may23.py` — 2 tests, tot P

### `social/tests/test_sonda_canco_dia.py` — 14 tests · P 11 · D 0 · M 3

| test | col | raó | incident |
|---|---|---|---|
| `test_ladder_tiers_and_order` | **M** | Ladder ordering is a promise, but exact esglaó numbers 1/2/3 pin the encoding; assert relative priority |  |
| `test_quota_no_cat_al_torn` | **M** | Non-CAT quota is a promise; "count%6==0" is a magic mirror of the code; assert non-CAT wins on the turn |  |
| `test_topat_amb_caducada_entra_esglao_3` | **M** | Promise (topped artist re-enters only via caducada) but pins esglao==3; assert eligible + lowest tier |  |

### `social/tests/test_story_fidelity.py` — 3 tests · P 1 · D 2 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_intro_text_ink_anchored_and_green_field` | **D** | Pixel pins (ink-top y=635/561 ±6, green field); pure change detector |  |
| `test_outro_is_yellow_dominant` | **D** | Colour-design pin; dup of test_renderer_ppcc_stories::test_outro_is_yellow_without_slate_card |  |

### `social/tests/test_story_mentions.py` — 14 tests · P 8 · D 2 · M 4

| test | col | raó | incident |
|---|---|---|---|
| `test_per_story_tags_logged` | **D** | Exact log-line text pin ("story 5/7 top_ppcc PPCC media=… tags=[p3,p2]") |  |
| `test_ppcc_full_set_composition` | **M** | Promise: each story tags exactly the visible songs; but pins slide count/draw order — assert set equality per tier, ≤20 |  |
| `test_ppcc_tiers_emitted_even_when_short` | **M** | Alignment with renderer is the promise; pins ==7 and tier indices; keep via test_territorial_alignment_against_real_renderer |  |
| `test_story_slot_sends_per_story_tags` | **M** | Wiring promise (tags reach upload_story, intro/outro untagged) but pins per-index call lists + n_mencions==4; assert union == expected handles |  |
| `test_territorial_degraded_tiers_alignment` | **M** | Same: pins index positions/order of degraded tiers; assert set of usernames per emitted slide, count == renderer |  |
| `test_territorial_midsize_gets_pairs_but_no_mosaic` | **D** | dup of test_territorial_degraded_tiers_alignment (mid-size variant), pins order |  |

### `social/tests/test_story_novetats_pagination.py` — 5 tests · P 1 · D 3 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_fit_keeps_full_cover_for_four_and_shrinks_beyond` | **D** | Mirrors _novetats_fit internals (_ST tokens, cover==design at 4); layout tuning kills it |  |
| `test_pagination_exact_multiple` | **D** | dup of test_pagination_splits_into_pages_of_per_page (edge already implied) |  |
| `test_per_page_clamped_and_empty` | **M** | Empty→no pages is P; clamp bounds 1/8 are magic mirrors of the code; assert never crashes and all items appear |  |
| `test_single_page_builder_unchanged_for_weekly_set` | **D** | Only asserts size; "unchanged" no-regression pin with no property |  |

### `social/tests/test_story_synth.py` — 5 tests · P 3 · D 0 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_a13_can_mention_gap` | **M** | Same: pins "TORNA"/"DESPRÉS DE 5 SETMANES" copy; assert gap value appears in some output |  |
| `test_a2_streak_uses_data` | **M** | Data reaches the headline (promise) but pins exact template copy; assert "5" (streak) appears in some output |  |

### `social/tests/test_territori_labels.py` — 10 tests · P 7 · D 1 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_no_paisos_catalans_hashtag` | **M** | No #PaïsosCatalans is P; exact PPCC hashtag list is a tautology — drop equality |  |
| `test_no_regression_ordinal_for_cat_val_bal` | **D** | dup of test_ordinal_forms (same equality restated) |  |
| `test_ordinal_forms` | **M** | PPCC "del top general" is a copy promise; `TERRITORI_ORDINAL == {...}` exact-dict pin — drop it |  |

### `social/tests/test_top_redesign.py` — 11 tests · P 4 · D 5 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_cover_eltop_forty_gap` | **D** | Ink gap −25 ±8: change detector (owner's worked example) |  |
| `test_list_numeral_centred_on_row` | **D** | Row centre 246: change detector (owner's worked example) |  |
| `test_mosaic_footer_clear` | **M** | Promise: 3rd row never collides with footer; but asserts footer-rule ink at y≈1240 not the clearance — assert clear band above footer |  |
| `test_poster_pins` | **D** | 7-px yellow bar at y=0..7: pure design pin |  |
| `test_top_cover_pins` | **D** | Yellow "40" ink-top at y≈570 ±8: coordinate pin |  |
| `test_top_list_one_highlighted_and_rows` | **M** | Promise: #1 row visually highlighted; pins y-band 1180–1280; assert highlight exists somewhere / differs from other rows |  |
| `test_top_pills_ink_centred` | **D** | Pill centre y=1234/76: change detector (owner's worked example) |  |
- `test_utm.py` — 7 tests, tot P

## web


### `web/tests/test_analytics_ingest.py` — 9 tests · P 8 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_long_values_are_truncated_not_stored_whole` | **M** | Bound is the promise; `== 80` mirrors the column. Assert len <= field max_length and << input | docstring: audit 2026-08-15 |
- `test_artista_entrat_top.py` — 2 tests, tot P
- `test_auth_login.py` — 8 tests, tot P

### `web/tests/test_autoconfig_correu.py` — 5 tests · P 4 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_the_file_is_valid_xml` | **D** | Dup: every other test in the file parses the XML already |  |

### `web/tests/test_deezer_gate.py` — 6 tests · P 5 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_command_moves_ghosts_and_is_idempotent` | **M** | Idempotence is the promise; second run pinned by stdout "Res a fer". Assert no state change instead |  |
- `test_esborrat_remot.py` — 5 tests, tot P
- `test_export_rgpd_contingut.py` — 4 tests, tot P
- `test_gestor_artista_editar.py` — 7 tests, tot P

### `web/tests/test_gestor_artista_portal.py` — 33 tests · P 29 · D 2 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_cancons_pendents_n_verificades_total_caps_at_50` | **M** | Cap value 50 is implementation; assert len(verificades) < total and total == 55 |  |
| `test_dashboard_skips_qualitat_on_unverified_row` | **D** | Pins absence of a key for a perf reason; a cheaper qualitat compute would legitimately break it |  |
| `test_qualitat_permission` | **D** | Dup of parametrized test_non_manager_forbidden (qualitat/); anon path is DRF default |  |
| `test_qualitat_shape` | **M** | `len(indicators) == 9` breaks on adding an indicator; keep score range + per-item keys/severity |  |
- `test_home_views.py` — 7 tests, tot P
- `test_legal_endpoints.py` — 9 tests, tot P
- `test_newsletter_ondemand.py` — 11 tests, tot P

### `web/tests/test_newsletter_routine.py` — 30 tests · P 24 · D 4 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_brief_aliases_are_identical_slices` | **M** | Slice equality is the promise; drop the exact fet_lider key-set pin |  |
| `test_brief_not_ready_still_short_circuits` | **D** | Dup of test_brief_not_ready_without_consolidated_top; pins absence of keys |  |
| `test_origen_prefetch_matches_legacy_first` | **D** | Pins `.first()`-by-pk equivalence; a better origin choice would break it |  |
| `test_post_llm_sends_admin_preview` | **M** | Pins copy ("Còpia de gestió", "Del 4 al 10", absent section). Keep: one mail to ADMINS, editor link, headers |  |
| `test_post_requires_subject` | **D** | Dup of test_post_no_subject_does_not_send |  |
| `test_post_terminal_draft_is_409` | **D** | Dup of test_post_terminal_draft_does_not_send |  |
- `test_paginacio_spa.py` — 2 tests, tot P
- `test_pendent_descartar.py` — 3 tests, tot P
- `test_pujada_imatges.py` — 6 tests, tot P
- `test_search_utils.py` — 4 tests, tot P

### `web/tests/test_seo.py` — 41 tests · P 39 · D 0 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_artista_page_degrades_without_editorial_links` | **M** | Pins markup "<h2>Explora</h2>"; assert 200 + no /genere//territori links instead |  |
| `test_comunitat_musics_public_page` | **M** | Copy pin "busca grup"; keep 200/indexable/title/CollectionPage, drop marketing copy |  |

### `web/tests/test_social_master_switch.py` — 5 tests · P 4 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_estat_canals_shapes_and_states` | **M** | Exact channel set + removed-key pin break on adding a channel; assert known channels ⊆ set + states |  |
- `test_social_metrics_summary.py` — 5 tests, tot P

### `web/tests/test_social_publicacions.py` — 12 tests · P 10 · D 1 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_pagination_meta_and_default_page_size` | **M** | Pin per_page==50 mirror de la constant; comprova només claus de paginació i per_page acotat |  |
| `test_public_url_newsletter_is_empty` | **D** | Trivial; si algun dia la newsletter té arxiu públic el test obstrueix |  |
- `test_sollicituds_revisio_workbench.py` — 15 tests, tot P

### `web/tests/test_spotify_enrichment_coverage.py` — 3 tests · P 2 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_estat_endpoint_exposes_coverage` | **M** | Re-afirma els mateixos números; deixa només "la clau existeix al payload" |  |
- `test_spotify_url_parse.py` — 3 tests, tot P
- `test_staff_analytics.py` — 2 tests, tot P
- `test_staff_analytics_quickwins.py` — 3 tests, tot P
- `test_staff_artistes_descartats.py` — 4 tests, tot P

### `web/tests/test_staff_artistes_sense_ig.py` — 6 tests · P 4 · D 1 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_cancons_vives_no_double_counting_principal_and_collab` | **D** | dup de test_cancons_vives_counts_principal_or_collaborator (ja prova 2+1=3) |  |
| `test_ordering_three_keys_novetats_surface` | **M** | Pin del desempat alfabètic (ja canviat per data a instagram_revisat); conserva només tops>vives>col·lab surt |  |
- `test_staff_avisos_top.py` — 2 tests, tot P
- `test_staff_canal_youtube.py` — 5 tests, tot P

### `web/tests/test_staff_cancons_spotify_fields.py` — 3 tests · P 2 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_cancons_list_spotify_null_when_no_row_at_all` | **D** | dup de _null_when_not_enriched; parametritza-ho |  |

### `web/tests/test_staff_cancons_spotify_manual.py` — 7 tests · P 6 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_patch_uri_and_bare_id` | **D** | dup de test_spotify_url_parse::test_accepts_track_forms a nivell endpoint |  |

### `web/tests/test_staff_configuracio.py` — 4 tests · P 3 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_editorial_veu_help_text_says_blank_generates_nothing` | **D** | Pin d'un tros de help_text; copy, no contracte |  |

### `web/tests/test_staff_endpoints.py` — 20 tests · P 17 · D 1 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_legacy_staff_views_shim_still_exposes_names` | **D** | Pin d'un shim de compatibilitat; retirar-lo és millora; urls.py ja peta si trenca |  |
| `test_republicar_calls_delete_then_publish` | **M** | Ordre delete→publish és promesa; strings de call_command no; comprova ordre + estat final del post |  |
| `test_staff_estat_returns_full_payload` | **M** | Pin 12 subtiers ordre exacte + auto_approved==[] (graduar-ne un el mata); compara amb ML_SUBTIERS i subconjunt |  |

### `web/tests/test_staff_estat_spotify.py` — 3 tests · P 1 · D 0 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_estat_endpoint_exposes_spotify_enrichment` | **M** | Re-afirma comptes; deixa només "bloc present al payload" |  |
| `test_spotify_enrichment_stats_shape_and_counts` | **M** | enrich_per_day==250 mirror de la constant (ja va morir a 50→250); comprova eta=backlog/rate |  |
- `test_staff_instagram_revisat.py` — 11 tests, tot P
- `test_staff_list_query_counts.py` — 3 tests, tot P
- `test_staff_otp_gate.py` — 5 tests, tot P
- `test_staff_social_invitacions.py` — 6 tests, tot P

### `web/tests/test_staff_spotify.py` — 13 tests · P 11 · D 1 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_sync_endpoint_forwards_freq_weekly` | **D** | dup de test_sync_forwards_to_management_command; pin args==(...) de call_command |  |
| `test_sync_forwards_to_management_command` | **M** | Pin del stdout del mock; comprova que la comanda rep dry_run/only i el payload torna playlists |  |
- `test_staff_usuaris_escriptures.py` — 9 tests, tot P
- `test_throttles.py` — 5 tests, tot P

## ingesta


### `ingesta/tests/test_actualitzar_playlists_spotify.py` — 14 tests · P 11 · D 1 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_no_verificades_nulls_last_and_created_at_tiebreak` | **M** | Property: NULL scores last, scored desc; exact created_at tiebreak order is implementation. |  |
| `test_throttle_flag_propagates_to_client` | **M** | Constructor kwarg pin; check the effective throttle behaviour, not the kwarg name. |  |
| `test_window_constants_are_consistent` | **D** | Tautology mirroring two constants. |  |
- `test_album_alie_guard.py` — 7 tests, tot P
- `test_caducitat_guard.py` — 11 tests, tot P

### `ingesta/tests/test_deezer_client.py` — 18 tests · P 14 · D 3 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `TestGetAlbumTracks::test_returns_tracks_with_isrc` | **M** | Outcome fine, but mock is a positional side_effect pinned to call order; key mock by URL. |  |
| `TestNormalize::test_combined` | **D** | dup of the three above. |  |
| `TestNormalize::test_strip_accents_catalan` | **D** | dup of test_strip_accents. |  |
| `TestSearchArtist::test_empty_results` | **D** | dup of test_no_match_returns_none / test_api_error. |  |
- `test_deezer_quota.py` — 5 tests, tot P
- `test_detectar_anomalies_senyal.py` — 7 tests, tot P

### `ingesta/tests/test_enriquir_spotify.py` — 18 tests · P 17 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_collaboration_principal_artist_is_artists0` | **M** | Keep principal=artists[0] + ids list; drop get_artist call_count/assert_called_with pin. |  |
- `test_enriquir_spotify_hydrate.py` — 2 tests, tot P
- `test_enriquir_spotify_rebuigs.py` — 11 tests, tot P

### `ingesta/tests/test_exception_threshold.py` — 8 tests · P 5 · D 0 · M 3

| test | col | raó | incident |
|---|---|---|---|
| `test_obtenir_metadata_all_ok_does_not_raise` | **M** | Assert no CommandError on 0% failure; drop the exact stdout string pin. | docstring: E2 sweep 2026-05-19 silent rot |
| `test_obtenir_metadata_below_threshold_does_not_raise` | **M** | Assert no raise at 30%; drop "Artists errors: 3" log-text pin. | docstring: E2 sweep 2026-05-19 |
| `test_restaurar_command_has_logger_in_audit_except_block` | **M** | Source-grep of exact log text; rewrite: mock log_staff_action to raise, assert warning via caplog. | docstring: E2 B-1 |

### `ingesta/tests/test_lastfm_client.py` — 14 tests · P 11 · D 0 · M 3

| test | col | raó | incident |
|---|---|---|---|
| `TestGetTrackInfoRateLimit::test_rate_limit_sleep` | **M** | Asserts sleep's first arg; property = rate limit respected (≥ RATE_LIMIT_SLEEP before request), not call shape. |  |
| `TestGetTrackInfoTrackNotFound::test_track_not_found` | **M** | Promise: err 6 → None + autocorrect=1 retry attempted; `call_count == 3` pins ladder length, blocks adding a fallback. | docstring: 2026-05-07 ~12% spurious errors |
| `TestMbidFallback::test_no_extra_call_when_there_was_no_mbid` | **M** | Guards API budget but hardcodes 3; compare against a no-mbid baseline call count instead. | docstring: 2026-08-10 |

### `ingesta/tests/test_lastfm_similars.py` — 14 tests · P 13 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_replace_similars_dedup_by_target` | **M** | Claims dedup but passes unique targets; rewrite to pass duplicate targets and assert one row. |  |
- `test_netejar_caducades.py` — 1 tests, tot P

### `ingesta/tests/test_obtenir_metadata.py` — 15 tests · P 14 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `TestIngestarMetadataDeezer::test_resolves_deezer_id_via_search_and_isrc` | **M** | Outcome (link created via ISRC validation) is the promise; mocks pinned to exact call sequence — key by album id. |  |

### `ingesta/tests/test_obtenir_novetats_cooldown.py` — 4 tests · P 3 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_p3_cooldown_skips_recently_checked` | **M** | Only asserts stdout "Total crides: 0"; assert last_checked_deezer unchanged instead. | docstring: 2026-05-01 12-day hang; CLAUDE.md §6 tq-health |
- `test_obtenir_senyal.py` — 25 tests, tot P

### `ingesta/tests/test_portades.py` — 18 tests · P 15 · D 2 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_all_fallthrough` | **M** | Property: total == limit and leftover budget flows to other entities; not the exact 1/5/3. |  |
| `test_exists_keys_on_500_webp_sentinel` | **D** | Which file is the sentinel is implementation; exists() semantics covered by test_delete_removes_all_variants. |  |
| `test_no_ranking_keeps_insertion_order` | **D** | Insertion order is not a promise; any smarter ordering fails it. |  |
- `test_previously_rejected_reconsiderada.py` — 7 tests, tot P
- `test_spotify_backfill_controller.py` — 21 tests, tot P

### `ingesta/tests/test_spotify_metadata_cooldown.py` — 12 tests · P 10 · D 1 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_active_legacy_backfill_file_seen` | **D** | dup of test_active_legacy_maintenance_file_seen (same path list, other element). |  |
| `test_playlist_sync_does_not_reference_metadata_cooldown` | **M** | Source-grep; property = playlist sync still writes while metadata cooldown is active (behavioural). | docstring: separate write bucket |
- `test_suggerir_instagram.py` — 3 tests, tot P

### `ingesta/tests/test_user_spotify_client_throttle.py` — 14 tests · P 11 · D 1 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_custom_throttle_overrides_default` | **D** | Pins private attrs `_throttle_s`/`_max_retry_after_s`. |  |
| `test_get_track_throttle_applied` | **M** | Same sleep-arg pin as test_throttle_sleeps_between_calls; check spacing property. |  |
| `test_throttle_sleeps_between_calls` | **M** | Asserts sleep(0.05) in call list; property = requests spaced by ≥ throttle, not sleep args. | docstring: post-2026-05-22 |

### `ingesta/tests/test_youtube.py` — 31 tests · P 30 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `TestCarrilOficialDesacoblat::test_second_run_adds_nothing_new` | **M** | Idempotence via count==1 is the promise; drop the "vídeos del carril oficial: 0" stdout pin. |  |

## music


### `music/tests/test_artista_queryset.py` — 6 tests · P 5 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_public_chains_with_filter` | **D** | Tests Django QuerySet chaining, not our code |  |

### `music/tests/test_canco_public_manager.py` — 2 tests · P 1 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_public_manager_matches_inline_filter_exactly` | **D** | Tautology: pins manager to today's inline filter; dup of test_public_manager_has_expected_semantics |  |

### `music/tests/test_health.py` — 21 tests · P 14 · D 0 · M 7

| test | col | raó | incident |
|---|---|---|---|
| `test_coverage_ok_when_healthy` | **M** | Keep OK; drop "Coverage OK" text |  |
| `test_coverage_warn_when_all_rows_never_synced` | **M** | Keep WARN; drop "never synced" text and len(rows)==2 |  |
| `test_coverage_warn_when_no_rows` | **M** | Keep WARN when nothing configured; drop command-name-in-message |  |
| `test_premium_crit_when_no_auth_row` | **M** | Keep severity CRIT; drop message substring and payload=={} |  |
| `test_premium_ok_on_premium` | **M** | Keep OK + payload.product; drop "admin_user in msg" |  |
| `test_premium_warn_on_transient_api_error` | **M** | Keep WARN-not-CRIT on transport error; drop message text |  |
| `test_tls_certs_probes_the_configured_host_and_port` | **M** | Property: host:port parsing reaches the probe; don't pin positional call signature |  |
- `test_homonims.py` — 6 tests, tot P
- `test_homonym_unlink.py` — 5 tests, tot P

### `music/tests/test_lastfm_aliases.py` — 8 tests · P 6 · D 1 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_alias_str_states` | **D** | __str__ formatting |  |
| `test_only_confirmed_aliases_sum_into_signal` | **M** | Tautology: re-runs the filter. Should exercise obtenir_senyal with mocked lastfm and assert only confirmed alias plays are summed |  |

### `music/tests/test_lastfm_prioritari.py` — 13 tests · P 11 · D 2 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_data_migration_creates_row_when_absent` | **D** | dup of test_data_migration_idempotent |  |
| `test_reverse_sync_skipped_when_update_fields_excludes_lastfm_nom` | **D** | Pins an internal cheap-exit branch; passes trivially since lastfm_nom is "" |  |

### `music/tests/test_mb_resolve_location.py` — 16 tests · P 15 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_validate_accepts_ppcc_municipi` | **M** | Keep mismatch False; drop exact reason=="ok-ppcc" |  |

### `music/tests/test_ml_auto_decide.py` — 10 tests · P 6 · D 2 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_auto_ml_decisions_excluded_from_training` | **M** | Re-implements the exclude; should call the training-set builder and assert auto_ml rows absent |  |
| `test_no_auto_decision_today` | **D** | dup of test_no_subtier_is_currently_auto; dies the day a tier graduates |  |
| `test_no_subtier_is_currently_auto` | **M** | Pins () and blocks legit graduation; rewrite: any graduated tier must carry documented honest accuracy ≥ threshold | docstring: 2026-04-30 target leakage |
| `test_subtiers_high_to_low_order` | **D** | Mirrors the ML_SUBTIERS list literally; cover-axis test guards the real property |  |
- `test_ml_load_validation.py` — 4 tests, tot P
- `test_ml_pair_rejection_ratio.py` — 5 tests, tot P

### `music/tests/test_ml_spotify_dispersion.py` — 7 tests · P 5 · D 1 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_build_features_includes_dispersion_at_expected_index` | **M** | Index by FEATURE_NAMES.index('spotify_artist_dispersio'), not n_struct-1; current form dies on next appended feature | runbook §Inserir features ML noves |
| `test_feature_name_present` | **D** | Pins "last structured slot" — breaks the sanctioned append-at-end rule for the next feature | runbook §Inserir features ML noves |

### `music/tests/test_models.py` — 11 tests · P 7 · D 4 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_get_territoris_marala_style` | **D** | dup of test_get_territoris_multiple + main_artist_only |  |
| `test_str` | **D** | __str__ formatting |  |
| `test_str_with_territories` | **D** | __str__ formatting |  |
| `test_str_without_territories` | **D** | __str__ formatting |  |
- `test_netejar_cancons_orfes.py` — 7 tests, tot P
- `test_netejar_pendents_no_ppcc.py` — 2 tests, tot P
- `test_purgar_pendents_buits.py` — 4 tests, tot P
- `test_purgar_pendents_post_seed.py` — 3 tests, tot P

### `music/tests/test_save_normalization.py` — 6 tests · P 5 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_empty_mbid_normalises_to_none` | **D** | Mechanism; dup of test_two_artists_with_blank_mbid_dont_collide (the promise) |  |

### `music/tests/test_services.py` — 33 tests · P 28 · D 3 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_approves_and_logs_ok` | **M** | Keep verificada+historial; replace assert_called_once_with(indexnow) by "was notified" |  |
| `test_approves_over_threshold` | **M** | Keep gate+motiu; drop assert_called_once_with(indexnow) | decisions/0014-whisper-lid-eval.md |
| `test_motiu_artista_incorrecte_triggers_unlink_attempt` | **D** | dup of test_homonym_unlink.test_unlink_when_all_rejected_as_homonym |  |
| `test_no_op_when_active_canco_remains` | **D** | dup of test_homonym_unlink.test_no_unlink_when_active_tracks_remain (via private fn) |  |
| `test_no_op_when_mixed_motius` | **D** | dup of test_homonym_unlink.test_no_unlink_when_motius_mixed |  |
- `test_spotify_dispersio.py` — 6 tests, tot P

### `music/tests/test_spotify_metadata.py` — 6 tests · P 0 · D 6 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_artista_dispersion_defaults` | **D** | Django defaults; dup of test_spotify_dispersio null test |  |
| `test_backfill_migration_idempotent_on_existing_spotify_id` | **D** | Never runs the migration; tautology |  |
| `test_default_status_not_attempted` | **D** | Tests Django field defaults |  |
| `test_one_to_one_reverse_accessor` | **D** | Tests Django ORM |  |
| `test_status_transition_to_found` | **D** | Set fields, save, read back — tests Django |  |
| `test_status_transition_to_not_found` | **D** | Tests Django |  |

### `music/tests/test_titlecase_catala.py` — 31 tests · P 30 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_acute_accent_article` | **D** | dup of test_grave_accent_article + normalize acute test |  |

## comptes

- `test_admin_inbox.py` — 4 tests, tot P

### `comptes/tests/test_auth_flow.py` — 5 tests · P 4 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_invalid_token_returns_400` | **M** | claims to guard token expiry but never tests an expired token; pins "Token" copy. Rewrite: expired (max_age=1y) token → refused | CLAUDE §privacy: May-2026 audit unsubscribe token expiry |
- `test_avisos_top.py` — 4 tests, tot P

### `comptes/tests/test_community_bridge.py` — 10 tests · P 9 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_html_to_markdown_empty` | **D** | trivial edge; adds nothing over the ugly-cases test |  |

### `comptes/tests/test_comunitat_matching.py` — 3 tests · P 2 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_patch_sets_matching_fields_from_list_and_string` | **M** | pins storage format "grup,colaboradors"; property = invalid token dropped, valid ones kept (check via API/directori) |  |
- `test_comunitat_seguretat.py` — 8 tests, tot P

### `comptes/tests/test_directori_staff_visibility.py` — 5 tests · P 4 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_regular_user_cannot_dm_private_user_via_directory` | **D** | dup of test_regular_user_sees_only_public_profiles (identical assertions) |  |
- `test_esborrar_compte.py` — 6 tests, tot P

### `comptes/tests/test_limit_2fa.py` — 4 tests · P 3 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_guessing_is_cut_off_after_the_configured_number_of_tries` | **M** | hardcodes index(429)==10 mirroring config; read the configured limit and assert cutoff at N+1 | docstring: 2026-08-15 audit (unlimited 2FA guesses) |

### `comptes/tests/test_newsletter_cover_predownload.py` — 5 tests · P 4 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_downloads_when_missing` | **M** | asserts exact call tuple; property = a download for that deezer id was attempted / cover present after | docstring: informe 2c 2026-06-07 |
- `test_newsletter_destinataris.py` — 2 tests, tot P

### `comptes/tests/test_newsletter_draft.py` — 18 tests · P 17 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_send_uses_edited_text_and_rebuilds_list` | **M** | pins mock call_args positions/kwarg names; property = sent email carries edited subject/narrative and fresh top entries |  |

### `comptes/tests/test_newsletter_linkify.py` — 12 tests · P 11 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_wraps_song_em_and_artist_strong` | **M** | pins exact markup string; property = artist name inside link to ART (bold), song inside link to CANCO (italic) |  |

### `comptes/tests/test_newsletter_namelinks.py` — 10 tests · P 3 · D 5 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_enrich_entry_collab_linked_when_slug_present` | **D** | internal dict shape; dup of test_preview_links_collaborator_in_prose_and_cards |  |
| `test_enrich_entry_collab_without_slug_stays_bold` | **M** | real promise (None slug → no broken link) but pinned on internal struct; assert in rendered HTML |  |
| `test_enrich_entry_principal_linked_collab_bold_backcompat` | **D** | internal dict shape; dup of test_preview_linkifies_injected_narrative_and_cards (rendered HTML) |  |
| `test_enrich_entry_truncates_long_collab_list` | **D** | dup of test_truncation_budget_is_over_names_and_keeps_whole_artists |  |
| `test_name_map_kinds_and_urls` | **D** | internal tuple shape; dup of test_preview_linkifies_injected_narrative_and_cards |  |
| `test_name_map_links_collaborator_with_slug` | **D** | internal tuple shape; dup of test_preview_links_collaborator_in_prose_and_cards |  |
| `test_truncation_budget_is_over_names_and_keeps_whole_artists` | **M** | keep "whole names, prefix order"; drop the 80-char arithmetic (read the constant) | docstring: #17 La Fúmiga + 38 sliced-tag case |

### `comptes/tests/test_newsletter_template.py` — 26 tests · P 18 · D 1 · M 7

| test | col | raó | incident |
|---|---|---|---|
| `test_dark_mode_and_responsive_present` | **M** | pins "max-width:640px" literal; property = has dark-mode media query and a mobile @media rule |  |
| `test_gmail_cards_own_their_width_not_a_nested_table` | **M** | len(rows)==7, exact hex, radius:12px; property = each card is a block div with own inline background+border | docstring: 2026-08-01 Gmail |
| `test_gmail_column_caps_live_in_the_style_block_and_reset_on_mobile` | **M** | pins px caps per class (330/250/290/192); property = each column class has a cap in <style> and a reset in the mobile @media | comment: 2026-08-01 Gmail mobile columns |
| `test_gmail_columns_are_full_width_divs_by_default` | **M** | couples to class names, count>=8, absent "gridcell"; property = every column div is inline-block width:100% inline, no CSS-stacked td | comment: 2026-08-01 Gmail mobile columns |
| `test_gmail_hybrid_container` | **M** | regex on class="wrap"+640px; property = no fixed-width table except MSO ghost, wrapper fluid | docstring: 2026-07-05 Gmail refactor |
| `test_gmail_mso_ghost_columns_for_outlook` | **M** | keep MSO conditional balance; drop the exact ghost px widths | docstring: 2026-08-01 Outlook |
| `test_gmail_redundant_bgcolor_attributes` | **M** | counts exact hex bgcolor >=8/>=5; property = every surface pins an inline background, none relies on <style> | docstring: 2026-07-05 / 2026-08-01 Gmail |
| `test_no_full_ranking_section` | **D** | absence of a heading copy string; pure change detector |  |

### `comptes/tests/test_notificar_gestors_retroactiu.py` — 7 tests · P 5 · D 1 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_real_run_is_idempotent` | **D** | dup of sends_and_stamps + already_notified_user_is_skipped |  |
| `test_template_renders_with_real_data` | **M** | pins FAQ copy ("365 dies","Deezer") and subject word; property = renders without error and names the artist |  |

### `comptes/tests/test_notifications.py` — 9 tests · P 2 · D 0 · M 7

| test | col | raó | incident |
|---|---|---|---|
| `test_notify_admins_nou_feedback` | **M** | recipient set = promise; subject wording substring = copy detector |  |
| `test_notify_admins_nova_proposta` | **M** | recipient set = promise; subject wording substring = copy detector |  |
| `test_notify_admins_nova_solicitud` | **M** | recipient set = promise; subject wording substring = copy detector, drop it |  |
| `test_notify_user_feedback_resolt` | **M** | recipient = promise; "feedback resolt" pin = copy detector |  |
| `test_notify_user_proposta_resolta_aprovada` | **M** | recipient = promise; "acceptada" pin = copy detector |  |
| `test_notify_user_solicitud_aprovada` | **M** | recipient = promise; "verificada" subject pin = copy detector |  |
| `test_notify_user_solicitud_rebutjada` | **M** | recipient = promise; "no acceptada" pin = copy detector |  |

### `comptes/tests/test_solicitud_revisio_model.py` — 9 tests · P 0 · D 9 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_create_with_defaults` | **D** | Django field defaults tautology |  |
| `test_estat_choices_are_three` | **D** | mirrors the constant list |  |
| `test_n_pendents_and_n_rebutjades_count` | **D** | len() of a list |  |
| `test_ordering_desc_created_at` | **D** | Meta.ordering tautology |  |
| `test_reconsiderada_can_be_flipped` | **D** | BooleanField save/refresh tautology |  |
| `test_reconsiderada_default_false` | **D** | field default tautology |  |
| `test_reconsiderada_filter_used_by_cron` | **D** | sentinel that re-implements a filter; the real guard belongs in the cron test |  |
| `test_str_carries_artista_and_estat` | **D** | __str__ repr detector |  |
| `test_workbench_query_pendent_default` | **D** | re-implements the ORM filter; proves Django can filter |  |

## analytics


### `analytics/tests/test_bots.py` — 5 tests · P 4 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_no_duplicate_markers` | **D** | List hygiene, no behaviour; a duplicate marker changes nothing observable |  |

### `analytics/tests/test_digest.py` — 7 tests · P 4 · D 0 · M 3

| test | col | raó | incident |
|---|---|---|---|
| `test_calendari_situa_cada_publicacio_al_seu_dia` | **M** | Pins exact cell dict shape and 6 rows; property: each post on its day, failures visible, every channel has a row |  |
| `test_digest_dry_run_renders_sections` | **M** | Pins column-aligned text ("Visites humanes   42"); check numbers/sections present, not spacing |  |
| `test_digest_reports_a_clean_week_as_clean` | **M** | "Cap incidència" is the promise; drop the "dilluns not in body" short-form copy pin |  |
- `test_events.py` — 6 tests, tot P

### `analytics/tests/test_generar_goaccess.py` — 15 tests · P 12 · D 1 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_live_file_only` | **M** | Pins summary text "0 rotats + 1 viu"; keep only the line count |  |
| `test_rotated_pattern_accepts_real_caddy_names` | **D** | dup of test_live_plus_rotated_reads_the_whole_corpus (uses same real names) |  |
| `test_rotated_pattern_rejects` | **M** | Tests the regex object; fold the extra names into the behavioural glob test |  |

### `analytics/tests/test_health_report.py` — 41 tests · P 34 · D 3 · M 4

| test | col | raó | incident |
|---|---|---|---|
| `test_cest_label_today_yesterday` | **D** | Pins "avui"/"ahir" copy of a helper |  |
| `test_classify_crit_threshold_stays_fixed` | **M** | Display substrings; property: CRIT ceiling independent of skip_concern, check escalates/state |  |
| `test_classify_default_warn_threshold_when_unset` | **M** | Same display-string pin + default 3 mirrors constant; assert via state |  |
| `test_classify_skip_concern_lowers_warn_threshold` | **M** | Pins display substring "watchdog WARN, 1 consecutive"; assert a warn flag/state at skip_concern |  |
| `test_gather_no_orphans_when_all_registered` | **D** | dup of test_gather_surfaces_orphan_status_file (already asserts the registered row is OK) |  |
| `test_relative_age` | **D** | Pins "fa 2d 2h" formatting of a cosmetic helper |  |
| `test_render_all_ok_header_and_legend` | **M** | Pins "🟢 Tot OK", "LLEGENDA", group name, "CEST"; keep overall==0 and an OK header marker |  |

### `analytics/tests/test_incidents.py` — 5 tests · P 4 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_django_errors_missing_file_is_not_zero_errors` | **M** | Exact dict equality (self-referential hack); assert disponible False + total 0 only |  |

### `analytics/tests/test_informe_youtube.py` — 4 tests · P 3 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_report_counts_coverage_and_the_blind_spot` | **M** | Pins column-aligned copy; check that 1/2 and 50% figures appear |  |

### `analytics/tests/test_informe_yt_comparativa.py` — 17 tests · P 16 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_the_report_says_what_would_happen_to_the_chart` | **M** | `actiu is False` pins today's config; assert it mirrors ConfiguracioGlobal, keep the row counts |  |
- `test_ingest.py` — 4 tests, tot P

### `analytics/tests/test_middleware.py` — 14 tests · P 13 · D 0 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_pageview_path_truncated_to_80_chars` | **M** | Magic 80 mirrors column width; assert len ≤ field max_length and no DB error |  |
- `test_recollir_metrics_bing.py` — 3 tests, tot P
- `test_recollir_metrics_gsc.py` — 1 tests, tot P
- `test_recollir_metrics_social.py` — 5 tests, tot P
- `test_referrers.py` — 3 tests, tot P
- `test_snapshot.py` — 1 tests, tot P

## topquaranta

- `test_backup_offsite.py` — 9 tests, tot P
- `test_csp_style_hashes.py` — 3 tests, tot P

### `topquaranta/tests/test_deploy_safety.py` — 23 tests · P 20 · D 0 · M 3

| test | col | raó | incident |
|---|---|---|---|
| `test_static_social_excluded_from_security_headers` | **M** | Anchored to literal matcher syntax; property: no CSP/XFO on /static/social/* (caddy adapt or header check) | CLAUDE.md §6 static social PNG hosting (IG 9004) |
| `test_sync_infra_installs_every_file_it_declares` | **M** | Pins `case`/`*)` shape and ordering; property: run script in tmp with a novel FILES dst and assert it is installed | docstring: 2026-08-18 mail autoconfig never installed |
| `test_tq_deploy_computes_the_diff_once_outside_any_condition` | **M** | Static substring pins on how tq-deploy is written; keep only "delegates to tq-changed-files", behaviour is covered by exit-7 test | runbook §changed-file list |

### `topquaranta/tests/test_docs_coherence.py` — 39 tests · P 26 · D 10 · M 3

| test | col | raó | incident |
|---|---|---|---|
| `test_conftest_under_mapped_subsystem_is_not_a_miss` | **D** | dup of test_is_implementation_churn_unit (conftest case) |  |
| `test_enriquir_spotify_resolves_to_pipeline` | **M** | Prefix-not-substring is a real property; test it with a synthetic mapping, not the live doc name |  |
| `test_generic_ingesta_falls_back_to_pipeline` | **D** | dup of test_longest_prefix_wins_for_spotify (same resolver semantics, real-map coordinate) |  |
| `test_longest_prefix_wins_for_spotify` | **M** | Pins a concrete doc path; state longest-prefix with a synthetic mapping |  |
| `test_main_fails_with_empty_reason` | **D** | dup of parse_overrides_drops_empty_reason + main_fails_on_miss |  |
| `test_main_fails_with_override_for_nonexistent_doc` | **D** | dup of unit validator test; monkeypatches module internals |  |
| `test_main_fails_with_override_for_wrong_doc` | **D** | dup of test_override_rejected_when_doc_does_not_match_any_miss via main() |  |
| `test_main_passes_when_code_and_doc_touched_together` | **D** | dup of test_no_miss_when_doc_is_also_in_diff via main() |  |
| `test_recalcular_dispersio_spotify_resolves_to_pipeline` | **D** | dup of test_enriquir_spotify_resolves_to_pipeline |  |
| `test_web_api_staff_beats_web_api` | **D** | dup of longest-prefix family; pins live doc name (already broke once on 2026-08-17 split) |  |
| `test_web_api_still_beats_web_generic` | **D** | dup of longest-prefix family |  |
| `test_web_generic_falls_back_to_web_md` | **D** | dup of longest-prefix family |  |
| `test_web_seo_matches_both_dir_and_hypothetical_file` | **M** | Prefix matches dir or file is a property; use synthetic mapping |  |

### `topquaranta/tests/test_docs_novelty.py` — 18 tests · P 15 · D 3 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_dir_without_py_is_not_flagged` | **D** | dup of test_is_code_dir_false_for_dir_without_py end-to-end |  |
| `test_is_code_dir_true_for_django_app` | **D** | dup of test_is_code_dir_true_for_dir_with_py (apps.py is a .py) |  |
| `test_multiple_uncovered_dirs_are_all_listed` | **D** | dup of test_uncovered_new_code_dir_is_flagged |  |

### `topquaranta/tests/test_docs_size.py` — 9 tests · P 8 · D 1 · M 0

| test | col | raó | incident |
|---|---|---|---|
| `test_multiple_offenders_are_all_returned` | **D** | dup of test_doc_over_threshold_is_flagged |  |
- `test_health_spa_assets.py` — 8 tests, tot P

## ranking

- `test_algorisme_collaboradors.py` — 2 tests, tot P
- `test_calcular_ranking.py` — 3 tests, tot P
- `test_coherencia_ranking.py` — 7 tests, tot P

### `ranking/tests/test_compute_weekly_plays.py` — 26 tests · P 23 · D 1 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_calib_sx3_tots_som_supers_fresh_untouched` | **D** | dup of test_fresh_release_returns_today_playcount |  |
| `test_only_recent_signal_no_baseline_returns_zero` | **M** | hardcodes the "≥4 d back" window edge; property = no usable baseline → 0, derive dates from the window constant |  |
| `test_track_switch_with_window_match_falls_back_to_branch_3` | **M** | encodes exact [-9,-5] window and 5.0; property = different-track row in window ignored, older same-track baseline used |  |

### `ranking/tests/test_models.py` — 12 tests · P 8 · D 3 · M 1

| test | col | raó | incident |
|---|---|---|---|
| `test_create_provisional` | **D** | field echo + __str__ detector |  |
| `test_load_creates_singleton` | **M** | singleton pk=1 is the promise; min_escoltes_top==5 mirrors the default, drop it |  |
| `test_master_overrides_channel_on` | **D** | dup of test_master_off_blocks_all_six |  |
| `test_str` | **D** | __str__ detector |  |

### `ranking/tests/test_soft_cap.py` — 14 tests · P 11 · D 1 · M 2

| test | col | raó | incident |
|---|---|---|---|
| `test_above_knee_compressed` | **M** | re-implements the log formula; keep only "strictly between knee and raw" |  |
| `test_ignores_out_of_scope_rows` | **M** | hardcodes "12 weeks > 10-week window"; derive the too-old date from the window constant |  |
| `test_off_is_identity_over_all_plays` | **D** | dup of test_disabled_returns_none + test_none_knee_unchanged; stale docstring (Postgres-only) |  |
- `test_youtube_al_top.py` — 8 tests, tot P
