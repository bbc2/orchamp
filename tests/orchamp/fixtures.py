"""
Shared test fixtures for analysis tests.
"""

from orchamp.models import (
    ChampionshipState,
    CompletedMatch,
    Match,
    MatchResult,
    MatchScore,
    Rules,
    Team,
)


def C(result: MatchResult, score: MatchScore | None = None) -> CompletedMatch:
    """
    Shorthand for creating a `CompletedMatch`, with no score by default.
    """

    return CompletedMatch(result=result, score=score)


def standard_rules() -> Rules:
    """
    Standard table tennis league rules.

    - Win: 3 points
    - Draw: 2 points
    - Loss: 1 point
    - Forfeit win: 3 points
    - Forfeit loss: 0 points
    """

    return Rules(
        win_points=3,
        draw_points=2,
        loss_points=1,
        forfeit_win_points=3,
        forfeit_loss_points=0,
    )


def small_league_teams() -> list[Team]:
    return [
        Team(id="alpha", name="Alpha TTC"),
        Team(id="beta", name="Beta Ping"),
        Team(id="gamma", name="Gamma Smash"),
        Team(id="delta", name="Delta Spin"),
    ]


def head_to_head_tiebreaker_teams() -> list[Team]:
    return [
        Team(id="alpha", name="Alpha TTC"),
        Team(id="beta", name="Beta Ping"),
        Team(id="gamma", name="Gamma Smash"),
        Team(id="delta", name="Delta Spin"),
    ]


def head_to_head_tiebreaker_state() -> ChampionshipState:
    """
    A completed league where head-to-head tiebreaking is decisive.

    All matches completed, no remaining matches.

    Results:
    - Alpha vs Beta: Alpha wins
    - Alpha vs Gamma: Gamma wins
    - Alpha vs Delta: Alpha wins
    - Beta vs Gamma: Beta wins
    - Beta vs Delta: Delta wins
    - Gamma vs Delta: Gamma wins

    Final points (with Win=3, Draw=2, Loss=1):
    - Alpha: 3 + 1 + 3 = 7 points
    - Beta:  1 + 3 + 1 = 5 points
    - Gamma: 3 + 1 + 3 = 7 points
    - Delta: 1 + 3 + 1 = 5 points

    Ties: Alpha and Gamma tied at 7; Beta and Delta tied at 5.

    Head-to-head resolution:
    - Alpha vs Gamma: Gamma wins → Gamma ranks above Alpha
    - Beta vs Delta: Delta wins → Delta ranks above Beta

    Correct final ranking: Gamma (1st) > Alpha (2nd) > Delta (3rd) > Beta (4th)
    """

    return ChampionshipState(
        teams=head_to_head_tiebreaker_teams(),
        completed_matches={
            Match(home="alpha", away="beta"): C(MatchResult.HOME_WIN),
            Match(home="alpha", away="gamma"): C(MatchResult.AWAY_WIN),
            Match(home="alpha", away="delta"): C(MatchResult.HOME_WIN),
            Match(home="beta", away="gamma"): C(MatchResult.HOME_WIN),
            Match(home="beta", away="delta"): C(MatchResult.AWAY_WIN),
            Match(home="gamma", away="delta"): C(MatchResult.HOME_WIN),
        },
        remaining_matches=[],
    )


def circular_three_way_tie_state() -> ChampionshipState:
    """
    A 3-team league with a circular head-to-head tie.

    Results: A beat B, B beat C, C beat A

    Final points (with Win=3, Loss=1):
    - A: 3 + 1 = 4 points
    - B: 1 + 3 = 4 points
    - C: 3 + 1 = 4 points

    All three teams are tied on total points AND on mini-league points
    (each has 1 win and 1 loss in the mini-league = 4 points).

    Therefore, any ranking permutation is valid (6 total).
    """

    return ChampionshipState(
        teams=[
            Team(id="A", name="Team A"),
            Team(id="B", name="Team B"),
            Team(id="C", name="Team C"),
        ],
        completed_matches={
            Match(home="A", away="B"): C(MatchResult.HOME_WIN),
            Match(home="B", away="C"): C(MatchResult.HOME_WIN),
            Match(home="C", away="A"): C(MatchResult.HOME_WIN),
        },
        remaining_matches=[],
    )


def multi_tie_state() -> ChampionshipState:
    """
    A 7-team league with multiple ties requiring tiebreakers.

    Final standings (Win=3, Draw=2, Loss=1):

    - Trantor: 14 points (4W, 0D, 2L)
    - Terminus: 13 points (3W, 1D, 2L)
    - Kalgan: 12 points (3W, 0D, 3L)
    - Tazenda: 12 points (2W, 2D, 2L)
    - Santanni: 11 points (2W, 1D, 3L)
    - Star's End: 11 points (2W, 1D, 3L)
    - Aurora: 11 points (2W, 1D, 3L)

    Kalgan vs Tazenda tiebreaker (both at 12 points):

    - Kalgan beat Tazenda head-to-head → Kalgan ranks 3rd, Tazenda 4th

    Bottom three mini-league (all have 4 match points from 1W, 1L):

    - Santanni: 5 game points won, 4 lost → quotient 1.25
    - Star's End: 5 game points won, 4 lost → quotient 1.25
    - Aurora: 4 game points won, 6 lost → quotient 0.67

    Aurora is determined as 7th. Santanni/Star's End still tied on quotients.

    Sub-mini-league for Santanni vs Star's End (points from head-to-head):

    - Santanni beat Star's End 3-1
    - Santanni: 3 match points
    - Star's End: 1 match point

    Santanni ranks above Star's End.

    Final ranking: Trantor (1st), Terminus (2nd), Kalgan (3rd), Tazenda (4th),
                   Santanni (5th), Star's End (6th), Aurora (7th)
    """

    return ChampionshipState(
        teams=[
            Team(id="trantor", name="Trantor"),
            Team(id="terminus", name="Terminus"),
            Team(id="kalgan", name="Kalgan"),
            Team(id="tazenda", name="Tazenda"),
            Team(id="santanni", name="Santanni"),
            Team(id="stars_end", name="Star's End"),
            Team(id="aurora", name="Aurora"),
        ],
        completed_matches={
            Match(home="trantor", away="terminus"): C(MatchResult.AWAY_WIN),
            Match(home="trantor", away="kalgan"): C(MatchResult.HOME_WIN),
            Match(home="trantor", away="tazenda"): C(MatchResult.AWAY_WIN),
            Match(home="trantor", away="santanni"): C(MatchResult.HOME_WIN),
            Match(home="trantor", away="stars_end"): C(MatchResult.HOME_WIN),
            Match(home="trantor", away="aurora"): C(MatchResult.HOME_WIN),
            Match(home="terminus", away="kalgan"): C(MatchResult.HOME_WIN),
            Match(home="terminus", away="tazenda"): C(MatchResult.HOME_WIN),
            Match(home="terminus", away="santanni"): C(MatchResult.AWAY_WIN),
            Match(home="terminus", away="stars_end"): C(MatchResult.AWAY_WIN),
            Match(home="terminus", away="aurora"): C(MatchResult.DRAW),
            Match(home="kalgan", away="tazenda"): C(MatchResult.HOME_WIN),
            Match(home="kalgan", away="santanni"): C(MatchResult.HOME_WIN),
            Match(home="kalgan", away="stars_end"): C(MatchResult.HOME_WIN),
            Match(home="kalgan", away="aurora"): C(MatchResult.AWAY_WIN),
            Match(home="tazenda", away="santanni"): C(MatchResult.DRAW),
            Match(home="tazenda", away="stars_end"): C(MatchResult.DRAW),
            Match(home="tazenda", away="aurora"): C(MatchResult.HOME_WIN),
            Match(home="santanni", away="stars_end"): C(
                MatchResult.HOME_WIN, MatchScore(home_points=3, away_points=1)
            ),
            Match(home="santanni", away="aurora"): C(
                MatchResult.AWAY_WIN, MatchScore(home_points=2, away_points=3)
            ),
            Match(home="stars_end", away="aurora"): C(
                MatchResult.HOME_WIN, MatchScore(home_points=4, away_points=1)
            ),
        },
        remaining_matches=[],
    )


def small_league_state() -> ChampionshipState:
    """
    A small league with 4 teams, 3 completed matches, and 3 remaining.

    Current points (with Win=3, Draw=2, Loss=1):
    - Alpha: 3 (beat Beta) + 2 (drew Gamma) = 5 points
    - Beta: 1 (lost to Alpha) + 1 (lost to Gamma) = 2 points
    - Gamma: 2 (drew Alpha) + 3 (beat Beta) = 5 points
    - Delta: 0 points (hasn't played yet)
    """

    return ChampionshipState(
        teams=small_league_teams(),
        completed_matches={
            Match(home="alpha", away="beta"): C(MatchResult.HOME_WIN),
            Match(home="alpha", away="gamma"): C(MatchResult.DRAW),
            Match(home="beta", away="gamma"): C(MatchResult.AWAY_WIN),
        },
        remaining_matches=[
            Match(home="alpha", away="delta"),
            Match(home="beta", away="delta"),
            Match(home="gamma", away="delta"),
        ],
    )
