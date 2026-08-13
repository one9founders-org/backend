from api.language import (
    description_needs_review,
    is_english_text,
    known_english_translation,
)
from api.ratings import (
    RATING_NOT_YET_RATED,
    RATING_PROVISIONAL,
    RATING_RATED,
    SECURITY_FLAGGED,
    SECURITY_NOT_ASSESSED,
    SECURITY_VERIFIED,
    coerce_overall_score,
    get_rating_status,
    get_security_status,
    get_tier_label,
)


class TestRatingStatus:
    def test_not_yet_rated_below_six(self):
        assert get_rating_status(0) == RATING_NOT_YET_RATED
        assert get_rating_status(5) == RATING_NOT_YET_RATED
        assert coerce_overall_score(5, 4.0) is None

    def test_provisional_six_to_nine(self):
        assert get_rating_status(6) == RATING_PROVISIONAL
        assert get_rating_status(9) == RATING_PROVISIONAL
        assert coerce_overall_score(7, 3.8) is not None

    def test_rated_at_ten(self):
        assert get_rating_status(10) == RATING_RATED
        assert get_tier_label(4.5) == "Outstanding"
        assert get_tier_label(4.0) == "Excellent"
        assert get_tier_label(3.7) == "Strong"
        assert get_tier_label(3.2) == "Good"
        assert get_tier_label(2.1) == "Fair"
        assert get_tier_label(1.9) == "Needs Improvement"


class TestSecurityStatus:
    def test_not_assessed_when_missing(self):
        assert get_security_status(None) == SECURITY_NOT_ASSESSED

    def test_flagged_below_twelve(self):
        assert get_security_status(11) == SECURITY_FLAGGED

    def test_verified_at_or_above_twelve(self):
        assert get_security_status(12) == SECURITY_VERIFIED
        assert get_security_status(20) == SECURITY_VERIFIED


class TestLanguageLint:
    def test_english_passes(self):
        assert is_english_text("An AI assistant for writing and research.")
        assert not description_needs_review("An AI assistant for writing and research.")

    def test_french_elevenlabs_fails(self):
        text = "Transformez des textes en voix ultra réalistes"
        assert description_needs_review(text)
        assert known_english_translation(text) == (
            "Transform text into ultra-realistic speech."
        )
