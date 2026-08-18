"""Tests for music/titlecase_catala.py."""

from music.titlecase_catala import normalize_apostrophes, titlecase_catala


class TestNormalizeApostrophes:
    def test_grave_accent_becomes_apostrophe(self):
        assert normalize_apostrophes("l\u0060home") == "l'home"

    def test_acute_accent_becomes_apostrophe(self):
        assert normalize_apostrophes("l\u00b4home") == "l'home"

    def test_smart_quotes_become_apostrophes(self):
        assert normalize_apostrophes("d\u2018ací i d\u2019allà") == "d'ací i d'allà"

    def test_modifier_letter_apostrophe(self):
        assert normalize_apostrophes("l\u02bchome") == "l'home"

    def test_plain_ascii_apostrophe_untouched(self):
        assert normalize_apostrophes("l'home") == "l'home"

    def test_precomposed_diacritics_left_alone(self):
        # é, è, ü are composed letters; normalization MUST NOT touch them.
        assert normalize_apostrophes("cafè L'Alguer") == "cafè L'Alguer"


class TestTitlecaseBasic:
    def test_empty(self):
        assert titlecase_catala("") == ""

    def test_none(self):
        assert titlecase_catala(None) == ""

    def test_single_word(self):
        assert titlecase_catala("adéu") == "Adéu"

    def test_particle_lowercased_mid_sentence(self):
        assert titlecase_catala("el noi de la mare") == "El Noi de la Mare"

    def test_particle_capitalized_at_start(self):
        assert titlecase_catala("de la terra al cel") == "De la Terra al Cel"


class TestTitlecaseApostrophe:
    def test_l_apostrophe_at_start(self):
        assert titlecase_catala("l'home de la lluna") == "L'Home de la Lluna"

    def test_d_apostrophe_mid_sentence(self):
        assert titlecase_catala("d'ací i d'allà") == "D'Ací i d'Allà"

    def test_weak_pronoun_clitic_capitalised_as_one_token(self):
        # Weak pronouns n'/m'/t'/s' attach to a verb, not an article.
        # We keep the token unsplit — only the first letter gets the
        # capital. "M'en" not "m'En".
        assert titlecase_catala("n'hi ha prou") == "N'hi Ha Prou"
        assert titlecase_catala("no s'acaba mai") == "No S'acaba Mai"
        assert titlecase_catala("a betlem m'en vull anar") == "A Betlem M'en Vull Anar"

    def test_uppercase_after_apostrophe_is_normalized(self):
        # An upstream all-caps token like "L'HOME" ends up "L'Home",
        # not "L'HOME". Fix introduced with the orphan-accent rewrite.
        assert titlecase_catala("L'HOME DE LA LLUNA") == "L'Home de la Lluna"


class TestTitlecaseOrphanAccents:
    def test_grave_accent_article(self):
        assert titlecase_catala("l\u0060home de la lluna") == "L'Home de la Lluna"

    def test_acute_accent_english_possessive(self):
        # "2001´s 99" — acute becomes plain apostrophe, "s" stays lower.
        assert titlecase_catala("2001\u00b4s 99") == "2001's 99"


class TestTitlecaseSingleLetters:
    def test_catalan_conjunction_I_becomes_lowercase_i(self):
        # The main complaint: Catalan "I" is the conjunction, not a pronoun.
        # Upstream data sometimes sends it capitalised; titlecase should fix.
        assert titlecase_catala("abans I ara") == "Abans i Ara"

    def test_numeric_title_with_I_conjunction(self):
        assert titlecase_catala("3 I 3") == "3 i 3"

    def test_first_word_A_stays_capital(self):
        # "A" at position 0 is either a preposition (capitalised as first word)
        # or part of an English title — both want the capital.
        assert titlecase_catala("A Beautiful Beast") == "A Beautiful Beast"

    def test_particles_A_O_lowercased_mid_sentence(self):
        # Mid-sentence "A", "O" are particles (preposition / conjunction) —
        # lowercased. "B" is a 1-char alpha but not in PARTICLES, so it
        # survives as "B" at start, and as "B" (capitalized first letter)
        # elsewhere.
        assert titlecase_catala("dir A o B") == "Dir a o B"


class TestTitlecaseOpeningPunctuation:
    def test_open_paren(self):
        assert (
            titlecase_catala("wish i never (original mix)")
            == "Wish i Never (Original Mix)"
        )

    def test_nested_paren_with_feat(self):
        assert (
            titlecase_catala("500 days (feat. jae luna) (acoustic version)")
            == "500 Days (Feat. Jae Luna) (Acoustic Version)"
        )

    def test_square_bracket(self):
        assert titlecase_catala("títol [bonus]") == "Títol [Bonus]"

    def test_opening_guillemet(self):
        assert titlecase_catala("l'amor «és així»") == "L'Amor «És Així»"

    def test_digit_led_word_untouched(self):
        # "3rd" must not become "3Rd".
        assert titlecase_catala("el 3rd millor disc") == "El 3rd Millor Disc"

    def test_possessive_s_untouched(self):
        # English possessive — first char is apostrophe, not in opening
        # punct, so no capitalization inside the word.
        assert titlecase_catala("2001's 99") == "2001's 99"


class TestTitlecaseAcronyms:
    def test_two_letter_acronym_preserved(self):
        assert titlecase_catala("cançons per a un DJ") == "Cançons per a un DJ"

    def test_three_letter_acronym_preserved(self):
        assert titlecase_catala("EP de la banda") == "EP de la Banda"

    def test_all_uppercase_input_not_treated_as_acronym(self):
        # If the WHOLE title is uppercase, we re-titlecase fully.
        assert titlecase_catala("EL NOI DE LA MARE") == "El Noi de la Mare"
