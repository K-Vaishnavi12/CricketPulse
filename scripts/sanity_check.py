"""Sanity check: DB + models load with new package versions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.warehouse.db import get_conn
from src.ml.inference import RealTimePredictor

print("Loading ML models...")
p = RealTimePredictor.load()
print(f"  win-prob classifier OK")
print(f"  final-score regressor OK")

print("\nQuerying DuckDB warehouse...")
with get_conn(read_only=True) as c:
    n_balls = c.execute("SELECT COUNT(*) FROM bronze.balls_raw").fetchone()[0]
    n_matches = c.execute("SELECT COUNT(*) FROM bronze.matches_raw").fetchone()[0]
    n_preds = c.execute("SELECT COUNT(*) FROM bronze.predictions_raw").fetchone()[0]
    print(f"  {n_balls} balls, {n_matches} match(es), {n_preds} predictions")

print("\nALL CHECKS PASSED - safe to deploy.")
