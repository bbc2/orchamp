from orchamp.ranking import compute_rankings

from .fixtures import (
    head_to_head_tiebreaker_state,
    multi_tie_state,
    standard_rules,
)


class TestComputeRankings:
    def test_multi_tie_state(self) -> None:
        state = multi_tie_state()
        rules = standard_rules()

        rankings = compute_rankings(state, rules)

        assert [(r.team_id, r.points) for r in rankings] == [
            ("trantor", 14),
            ("terminus", 13),
            ("kalgan", 12),
            ("tazenda", 12),
            ("santanni", 11),
            ("stars_end", 11),
            ("aurora", 11),
        ]

    def test_head_to_head_tiebreaker(self) -> None:
        state = head_to_head_tiebreaker_state()
        rules = standard_rules()

        rankings = compute_rankings(state, rules)

        # Expected: Gamma(1), Alpha(2), Delta(3), Beta(4)
        # Alpha and Gamma tied at 7 points, Gamma wins head-to-head
        # Beta and Delta tied at 5 points, Delta wins head-to-head
        assert [(r.team_id, r.points) for r in rankings] == [
            ("gamma", 7),
            ("alpha", 7),
            ("delta", 5),
            ("beta", 5),
        ]
