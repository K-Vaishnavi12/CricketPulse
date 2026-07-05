"""Smoke test: run a full simulated match end-to-end and print highlights."""
from src.simulator.match_engine import MatchSimulator


def main() -> None:
    sim = MatchSimulator(
        team_a_name="Mumbai Mavericks",
        team_b_name="Chennai Chargers",
        venue="Wankhede Stadium",
        seed=42,
    )
    balls = list(sim.stream_balls())

    inn1 = [b for b in balls if b.innings == 1]
    inn2 = [b for b in balls if b.innings == 2]

    print(f"Match ID       : {sim.meta.match_id}")
    print(f"Toss           : {sim.meta.toss_winner} chose to {sim.meta.toss_decision}")
    print(f"Total balls    : {len(balls)}")
    print(f"Innings 1      : {inn1[-1].batting_team} {inn1[-1].innings_score}/{inn1[-1].innings_wickets} in {inn1[-1].innings_overs_completed}")
    if inn2:
        print(f"Innings 2      : {inn2[-1].batting_team} {inn2[-1].innings_score}/{inn2[-1].innings_wickets} in {inn2[-1].innings_overs_completed} (target {inn2[-1].target})")
    print(f"Result         : {sim.state.result_text}")

    print("\n--- First 3 balls ---")
    for b in balls[:3]:
        print(f"  {b.over}.{b.ball} I{b.innings}  {b.batter[:18]:<18} vs {b.bowler[:18]:<18}  "
              f"r={b.runs_batter} x={b.runs_extras}  W={b.is_wicket}  "
              f"score={b.innings_score}/{b.innings_wickets}")

    print("\n--- Last 3 balls ---")
    for b in balls[-3:]:
        print(f"  {b.over}.{b.ball} I{b.innings}  {b.batter[:18]:<18} vs {b.bowler[:18]:<18}  "
              f"r={b.runs_batter} x={b.runs_extras}  W={b.is_wicket}  "
              f"score={b.innings_score}/{b.innings_wickets}")


if __name__ == "__main__":
    main()
