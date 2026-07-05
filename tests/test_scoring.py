from scoring import (
    AI_LABEL,
    HUMAN_LABEL,
    UNCERTAIN_LABEL,
    combine_scores,
    decide,
)


def test_combine_scores_uses_documented_weights():
    assert combine_scores(1.0, 0.0) == 0.65
    assert combine_scores(0.0, 1.0) == 0.35


def test_all_three_label_variants_are_reachable():
    human = decide(0.20)
    uncertain = decide(0.60)
    ai = decide(0.90)

    assert human.attribution == "likely_human"
    assert human.label == HUMAN_LABEL

    assert uncertain.attribution == "uncertain"
    assert uncertain.label == UNCERTAIN_LABEL

    assert ai.attribution == "likely_ai"
    assert ai.label == AI_LABEL


def test_confidence_reflects_distance_from_midpoint():
    assert decide(0.51).confidence == 0.02
    assert decide(0.95).confidence == 0.9
    assert decide(0.10).confidence == 0.8
