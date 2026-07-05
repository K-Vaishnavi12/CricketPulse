"""Squad roster + realistic player skill ratings."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Player:
    name: str
    # 0.0 (weak) to 1.0 (world-class)
    bat_skill: float = 0.5
    bowl_skill: float = 0.5
    is_bowler: bool = False
    is_wicket_keeper: bool = False


@dataclass
class Team:
    name: str
    short_code: str
    players: List[Player] = field(default_factory=list)

    @property
    def batters(self) -> List[Player]:
        return self.players

    @property
    def bowlers(self) -> List[Player]:
        return [p for p in self.players if p.is_bowler]


# Fictional squads so we don't step on real-player-name issues.
MUMBAI_MAVERICKS = Team(
    name="Mumbai Mavericks",
    short_code="MMV",
    players=[
        Player("Rohan Sharma", bat_skill=0.85, bowl_skill=0.10),
        Player("Ishan Kishan", bat_skill=0.75, bowl_skill=0.05, is_wicket_keeper=True),
        Player("Suryakumar Yadav", bat_skill=0.90, bowl_skill=0.05),
        Player("Tilak Verma", bat_skill=0.70, bowl_skill=0.30),
        Player("Hardik Pandya", bat_skill=0.72, bowl_skill=0.70, is_bowler=True),
        Player("Kieron Powell", bat_skill=0.65, bowl_skill=0.20),
        Player("Krunal Pandey", bat_skill=0.55, bowl_skill=0.65, is_bowler=True),
        Player("Piyush Chawla", bat_skill=0.25, bowl_skill=0.75, is_bowler=True),
        Player("Jasprit Boomer", bat_skill=0.15, bowl_skill=0.95, is_bowler=True),
        Player("Trent Bolt", bat_skill=0.20, bowl_skill=0.88, is_bowler=True),
        Player("Yuzvendra Chandel", bat_skill=0.30, bowl_skill=0.82, is_bowler=True),
    ],
)

CHENNAI_CHARGERS = Team(
    name="Chennai Chargers",
    short_code="CHC",
    players=[
        Player("Ruturaj Gaikward", bat_skill=0.82, bowl_skill=0.05),
        Player("Devon Cornway", bat_skill=0.75, bowl_skill=0.05, is_wicket_keeper=True),
        Player("Ajinkya Rahani", bat_skill=0.70, bowl_skill=0.10),
        Player("Shivam Duke", bat_skill=0.68, bowl_skill=0.55, is_bowler=True),
        Player("Ravindra Jadeza", bat_skill=0.72, bowl_skill=0.78, is_bowler=True),
        Player("MS Dhanraj", bat_skill=0.80, bowl_skill=0.05, is_wicket_keeper=True),
        Player("Sam Currane", bat_skill=0.60, bowl_skill=0.70, is_bowler=True),
        Player("Deepak Chaher", bat_skill=0.35, bowl_skill=0.80, is_bowler=True),
        Player("Tushar Deshpande", bat_skill=0.25, bowl_skill=0.75, is_bowler=True),
        Player("Mahesh Theekshana", bat_skill=0.20, bowl_skill=0.82, is_bowler=True),
        Player("Matheesha Pathirane", bat_skill=0.15, bowl_skill=0.85, is_bowler=True),
    ],
)


TEAMS_BY_NAME = {
    MUMBAI_MAVERICKS.name: MUMBAI_MAVERICKS,
    CHENNAI_CHARGERS.name: CHENNAI_CHARGERS,
}


def get_team(name: str) -> Team:
    """Return a team by name, or a synthetic one if unknown."""
    if name in TEAMS_BY_NAME:
        return TEAMS_BY_NAME[name]
    # synthesize an average team so custom names still work
    return Team(
        name=name,
        short_code=name[:3].upper(),
        players=[
            Player(f"{name} Player {i+1}",
                   bat_skill=0.4 + (i % 5) * 0.08,
                   bowl_skill=0.7 if i >= 6 else 0.3,
                   is_bowler=(i >= 6),
                   is_wicket_keeper=(i == 1))
            for i in range(11)
        ],
    )
