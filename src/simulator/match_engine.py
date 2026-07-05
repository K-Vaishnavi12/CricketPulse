"""Realistic ball-by-ball T20 simulation engine.

Uses a probabilistic outcome model influenced by:
- batter skill vs bowler skill
- match phase (powerplay / middle / death)
- current pressure (target chase, wickets in hand)

Not perfect cricket, but produces plausible, varied matches every run.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, List, Optional

from src.common.schemas import BallEvent, MatchMeta
from src.simulator.teams import Player, Team, get_team


@dataclass
class InningsState:
    batting: Team
    bowling: Team
    score: int = 0
    wickets: int = 0
    over: int = 0
    ball_in_over: int = 0
    legal_balls: int = 0  # for over completion
    striker: Optional[Player] = None
    non_striker: Optional[Player] = None
    next_batter_idx: int = 2
    bowler: Optional[Player] = None
    bowlers_used: List[Player] = field(default_factory=list)
    balls_bowled_by_bowler: dict = field(default_factory=dict)
    dismissed: set = field(default_factory=set)
    target: Optional[int] = None

    @property
    def overs_completed(self) -> float:
        return round(self.over + self.ball_in_over / 6.0, 3)


@dataclass
class MatchState:
    meta: MatchMeta
    innings1: InningsState
    innings2: Optional[InningsState] = None
    is_finished: bool = False
    winner: Optional[str] = None
    result_text: Optional[str] = None


PHASE_POWERPLAY = "powerplay"   # overs 0-5
PHASE_MIDDLE = "middle"         # overs 6-14
PHASE_DEATH = "death"           # overs 15-19


def _phase(over: int) -> str:
    if over < 6:
        return PHASE_POWERPLAY
    if over < 15:
        return PHASE_MIDDLE
    return PHASE_DEATH


def _pick_new_bowler(state: InningsState, rng: random.Random) -> Player:
    """Choose a bowler who hasn't bowled 4 overs and isn't the previous one."""
    available = [
        b for b in state.bowling.bowlers
        if state.balls_bowled_by_bowler.get(b.name, 0) < 24
        and b != state.bowler
    ]
    if not available:
        # extreme edge case (all bowlers exhausted) - pick anyone
        available = [b for b in state.bowling.bowlers if b != state.bowler] or state.bowling.bowlers
    # weight by bowling skill
    weights = [max(0.1, b.bowl_skill) for b in available]
    return rng.choices(available, weights=weights, k=1)[0]


def _outcome_probs(batter: Player, bowler: Player, phase: str,
                   required_rr: Optional[float], wickets_left: int) -> dict:
    """Return probability distribution over outcomes for a single ball.

    Outcomes:
        'W' wicket, '0','1','2','3','4','6', 'wd' (wide), 'nb' (no ball), 'bye'
    """
    # base T20 empirical-ish distribution
    base = {
        "0":  0.35,
        "1":  0.30,
        "2":  0.09,
        "3":  0.01,
        "4":  0.11,
        "6":  0.05,
        "W":  0.045,
        "wd": 0.02,
        "nb": 0.005,
        "bye": 0.005,
    }

    # skill differential (-1 .. +1) - positive means batter dominant
    skill_diff = batter.bat_skill - bowler.bowl_skill

    # boundary boost from batter skill
    base["4"] += 0.06 * skill_diff
    base["6"] += 0.04 * skill_diff
    base["W"] -= 0.02 * skill_diff  # good batters get out less
    base["0"] -= 0.03 * skill_diff

    # phase adjustments
    if phase == PHASE_POWERPLAY:
        base["4"] += 0.02
        base["6"] += 0.01
        base["W"] += 0.005
    elif phase == PHASE_DEATH:
        base["4"] += 0.04
        base["6"] += 0.06
        base["W"] += 0.03
        base["1"] -= 0.03
        base["0"] -= 0.04

    # chase pressure
    if required_rr is not None:
        if required_rr > 12:
            base["6"] += 0.05
            base["4"] += 0.03
            base["W"] += 0.04
            base["0"] += 0.02
        elif required_rr > 9:
            base["4"] += 0.02
            base["6"] += 0.02
            base["W"] += 0.02
        elif required_rr < 6 and wickets_left >= 6:
            base["0"] += 0.04
            base["1"] += 0.04
            base["4"] -= 0.02
            base["6"] -= 0.02

    # tail-ender penalty
    if batter.bat_skill < 0.35:
        base["W"] += 0.03
        base["4"] -= 0.02
        base["6"] -= 0.02

    # normalize (clip negatives)
    for k in base:
        if base[k] < 0:
            base[k] = 0.001
    total = sum(base.values())
    return {k: v / total for k, v in base.items()}


def _sample_dismissal(rng: random.Random) -> str:
    kinds = ["caught", "bowled", "lbw", "run out", "stumped", "caught and bowled", "hit wicket"]
    weights = [0.55, 0.20, 0.10, 0.08, 0.04, 0.02, 0.01]
    return rng.choices(kinds, weights=weights, k=1)[0]


class MatchSimulator:
    """Yields BallEvent objects one at a time until the match ends."""

    def __init__(self, team_a_name: str, team_b_name: str, venue: str, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        team_a = get_team(team_a_name)
        team_b = get_team(team_b_name)

        toss_winner = self.rng.choice([team_a.name, team_b.name])
        toss_decision = self.rng.choice(["bat", "field"])

        # figure out who bats first
        if toss_winner == team_a.name:
            bat_first = team_a if toss_decision == "bat" else team_b
        else:
            bat_first = team_b if toss_decision == "bat" else team_a
        bowl_first = team_b if bat_first is team_a else team_a

        self.meta = MatchMeta(
            match_id=f"m_{uuid.uuid4().hex[:8]}",
            team_a=team_a.name,
            team_b=team_b.name,
            venue=venue,
            toss_winner=toss_winner,
            toss_decision=toss_decision,
            start_ts=datetime.now(timezone.utc),
        )

        self.state = MatchState(
            meta=self.meta,
            innings1=self._new_innings(bat_first, bowl_first),
        )

    def _new_innings(self, batting: Team, bowling: Team, target: Optional[int] = None) -> InningsState:
        innings = InningsState(batting=batting, bowling=bowling, target=target)
        innings.striker = batting.batters[0]
        innings.non_striker = batting.batters[1]
        innings.bowler = self.rng.choices(
            bowling.bowlers,
            weights=[max(0.1, b.bowl_skill) for b in bowling.bowlers],
            k=1,
        )[0]
        return innings

    def _end_of_over(self, innings: InningsState) -> None:
        innings.over += 1
        innings.ball_in_over = 0
        innings.striker, innings.non_striker = innings.non_striker, innings.striker
        if innings.over < 20:
            innings.bowler = _pick_new_bowler(innings, self.rng)

    def _wicket(self, innings: InningsState) -> Optional[Player]:
        """Bring in the next batter. Returns dismissed player."""
        dismissed = innings.striker
        innings.wickets += 1
        innings.dismissed.add(dismissed.name)
        if innings.next_batter_idx < len(innings.batting.batters):
            innings.striker = innings.batting.batters[innings.next_batter_idx]
            innings.next_batter_idx += 1
        else:
            innings.striker = None  # all out
        return dismissed

    def _current_innings(self) -> InningsState:
        return self.state.innings2 or self.state.innings1

    def _innings_over(self, innings: InningsState) -> bool:
        if innings.wickets >= 10:
            return True
        if innings.over >= 20:
            return True
        if innings.target is not None and innings.score >= innings.target:
            return True
        return False

    def _required_rr(self, innings: InningsState) -> Optional[float]:
        if innings.target is None:
            return None
        balls_left = (20 - innings.over) * 6 - innings.ball_in_over
        if balls_left <= 0:
            return None
        runs_needed = innings.target - innings.score
        return round((runs_needed / balls_left) * 6, 2)

    def stream_balls(self) -> Iterator[BallEvent]:
        while not self.state.is_finished:
            innings_num = 2 if self.state.innings2 else 1
            innings = self._current_innings()

            if self._innings_over(innings):
                if innings_num == 1:
                    # start innings 2
                    self.state.innings2 = self._new_innings(
                        batting=innings.bowling,
                        bowling=innings.batting,
                        target=innings.score + 1,
                    )
                    continue
                else:
                    self._finalize()
                    break

            phase = _phase(innings.over)
            probs = _outcome_probs(
                batter=innings.striker,
                bowler=innings.bowler,
                phase=phase,
                required_rr=self._required_rr(innings),
                wickets_left=10 - innings.wickets,
            )
            outcome = self.rng.choices(list(probs.keys()), weights=list(probs.values()), k=1)[0]

            runs_batter = 0
            runs_extras = 0
            extras_kind = None
            is_wicket = False
            dismissal_kind = None
            player_out = None
            legal_ball = True

            if outcome == "wd":
                runs_extras = 1
                extras_kind = "wide"
                legal_ball = False
            elif outcome == "nb":
                runs_extras = 1
                extras_kind = "no ball"
                # batter still faces a free hit worth ~0 avg here (simplified)
                legal_ball = False
            elif outcome == "bye":
                runs_extras = self.rng.choice([1, 1, 1, 2, 4])
                extras_kind = "bye"
            elif outcome == "W":
                is_wicket = True
                dismissal_kind = _sample_dismissal(self.rng)
                player_out = innings.striker.name
            else:
                runs_batter = int(outcome)

            innings.ball_in_over += 1
            if legal_ball:
                innings.legal_balls += 1
                innings.balls_bowled_by_bowler[innings.bowler.name] = (
                    innings.balls_bowled_by_bowler.get(innings.bowler.name, 0) + 1
                )
            innings.score += runs_batter + runs_extras

            dismissed_name = None
            if is_wicket:
                dismissed_player = self._wicket(innings)
                dismissed_name = dismissed_player.name if dismissed_player else None
            else:
                # rotate strike on odd runs
                if runs_batter in (1, 3):
                    innings.striker, innings.non_striker = innings.non_striker, innings.striker

            event = BallEvent(
                match_id=self.meta.match_id,
                innings=innings_num,
                over=innings.over,
                ball=innings.ball_in_over,
                batting_team=innings.batting.name,
                bowling_team=innings.bowling.name,
                batter=(innings.striker.name if innings.striker
                        else (dismissed_name or "unknown")),
                non_striker=innings.non_striker.name if innings.non_striker else "unknown",
                bowler=innings.bowler.name,
                runs_batter=runs_batter,
                runs_extras=runs_extras,
                extras_kind=extras_kind,
                is_wicket=is_wicket,
                dismissal_kind=dismissal_kind,
                player_out=dismissed_name,
                innings_score=innings.score,
                innings_wickets=innings.wickets,
                innings_overs_completed=innings.overs_completed,
                target=innings.target,
                event_ts=datetime.now(timezone.utc),
            )
            yield event

            # end of over
            if legal_ball and innings.ball_in_over % 6 == 0:
                if innings.over + 1 < 20 and not self._innings_over(innings):
                    self._end_of_over(innings)
                else:
                    # still count the over completion for the state
                    innings.over += 1
                    innings.ball_in_over = 0

            # check innings end after ball
            if self._innings_over(innings):
                if innings_num == 1:
                    self.state.innings2 = self._new_innings(
                        batting=innings.bowling,
                        bowling=innings.batting,
                        target=innings.score + 1,
                    )
                else:
                    self._finalize()

    def _finalize(self) -> None:
        i1 = self.state.innings1
        i2 = self.state.innings2
        self.state.is_finished = True
        if i2 is None:
            return
        if i2.score >= (i2.target or 0):
            wickets_left = 10 - i2.wickets
            self.state.winner = i2.batting.name
            self.state.result_text = f"{i2.batting.name} won by {wickets_left} wickets"
        elif i2.score < (i2.target or 0) - 1:
            margin = (i2.target or 0) - 1 - i2.score
            self.state.winner = i1.batting.name
            self.state.result_text = f"{i1.batting.name} won by {margin} runs"
        else:
            self.state.result_text = "Match tied"
