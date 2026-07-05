"""Unit tests for the match simulator."""
from src.simulator.match_engine import MatchSimulator


def test_full_match_reaches_result():
    sim = MatchSimulator("Team A", "Team B", "Ground", seed=1)
    balls = list(sim.stream_balls())
    assert len(balls) > 100
    assert sim.state.is_finished
    assert sim.state.result_text is not None


def test_ball_score_is_monotonic_within_innings():
    sim = MatchSimulator("Team A", "Team B", "Ground", seed=2)
    prev_score = {1: -1, 2: -1}
    for b in sim.stream_balls():
        assert b.innings_score >= prev_score[b.innings]
        prev_score[b.innings] = b.innings_score


def test_wickets_never_exceed_ten():
    sim = MatchSimulator("Team A", "Team B", "Ground", seed=3)
    for b in sim.stream_balls():
        assert 0 <= b.innings_wickets <= 10


def test_innings_two_has_target():
    sim = MatchSimulator("Team A", "Team B", "Ground", seed=4)
    inn2 = [b for b in sim.stream_balls() if b.innings == 2]
    assert all(b.target is not None for b in inn2)
