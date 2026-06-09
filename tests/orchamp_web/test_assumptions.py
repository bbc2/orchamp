from orchamp_web.assumptions import (
    MAX_ASSUMPTIONS,
    AssumptionEntry,
    parse_assumptions,
    serialize_assumption,
)


class TestParseAssumptions:
    def test_empty_list(self) -> None:
        result = parse_assumptions([])

        assert result.entries == []
        assert not result.excess

    def test_valid_single_entry(self) -> None:
        result = parse_assumptions(["alpha:beta:3:1"])

        assert result.entries == [
            AssumptionEntry(home_id="alpha", away_id="beta", home_score=3, away_score=1)
        ]

    def test_valid_multiple_entries(self) -> None:
        result = parse_assumptions(["alpha:beta:3:1", "gamma:delta:0:0"])

        assert result.entries == [
            AssumptionEntry(
                home_id="alpha", away_id="beta", home_score=3, away_score=1
            ),
            AssumptionEntry(
                home_id="gamma", away_id="delta", home_score=0, away_score=0
            ),
        ]

    def test_boundary_scores(self) -> None:
        result = parse_assumptions(["a:b:0:20"])

        assert result.entries == [
            AssumptionEntry(home_id="a", away_id="b", home_score=0, away_score=20)
        ]

    def test_too_few_parts_is_skipped(self) -> None:
        result = parse_assumptions(["alpha:beta:3"])

        assert result.entries == []

    def test_too_many_parts_is_skipped(self) -> None:
        result = parse_assumptions(["alpha:beta:3:1:extra"])

        assert result.entries == []

    def test_non_integer_score_is_skipped(self) -> None:
        result = parse_assumptions(["alpha:beta:three:1"])

        assert result.entries == []

    def test_score_above_max_is_skipped(self) -> None:
        result = parse_assumptions(["alpha:beta:21:1"])

        assert result.entries == []

    def test_negative_score_is_skipped(self) -> None:
        result = parse_assumptions(["alpha:beta:-1:1"])

        assert result.entries == []

    def test_invalid_entries_are_filtered_keeping_valid(self) -> None:
        result = parse_assumptions(["alpha:beta:3:1", "bad", "gamma:delta:0:0"])

        assert result.entries == [
            AssumptionEntry(
                home_id="alpha", away_id="beta", home_score=3, away_score=1
            ),
            AssumptionEntry(
                home_id="gamma", away_id="delta", home_score=0, away_score=0
            ),
        ]
        assert not result.excess

    def test_excess_entries_are_listed_but_not_applied(self) -> None:
        raw = [f"home{i}:away{i}:1:0" for i in range(MAX_ASSUMPTIONS + 5)]

        result = parse_assumptions(raw)

        assert len(result.entries) == MAX_ASSUMPTIONS + 5
        assert result.applied == result.entries[:MAX_ASSUMPTIONS]
        assert result.excess

    def test_exactly_at_the_cap_is_not_excess(self) -> None:
        raw = [f"home{i}:away{i}:1:0" for i in range(MAX_ASSUMPTIONS)]

        result = parse_assumptions(raw)

        assert result.applied == result.entries
        assert not result.excess

    def test_invalid_entries_do_not_count_towards_the_cap(self) -> None:
        raw = ["bad"] * MAX_ASSUMPTIONS + ["alpha:beta:3:1"]

        result = parse_assumptions(raw)

        assert result.entries == [
            AssumptionEntry(home_id="alpha", away_id="beta", home_score=3, away_score=1)
        ]
        assert not result.excess


class TestSerializeAssumption:
    def test_basic(self) -> None:
        entry = AssumptionEntry(
            home_id="alpha", away_id="beta", home_score=3, away_score=1
        )

        result = serialize_assumption(entry)

        assert result == "alpha:beta:3:1"

    def test_round_trip(self) -> None:
        entry = AssumptionEntry(
            home_id="team-1", away_id="team-2", home_score=10, away_score=7
        )

        parsed = parse_assumptions([serialize_assumption(entry)])

        assert parsed.entries == [entry]
