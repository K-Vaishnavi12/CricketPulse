"""Quick test: does Gemini + LangChain + text-to-SQL work end-to-end?"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.genai.sql_agent import ask


def main() -> None:
    q = "Who has the highest strike rate in this match?"
    print(f"\nQ: {q}")
    print("-" * 70)
    answer = ask(q)
    print(f"SQL: {answer.sql}")
    print(f"Rows returned: {len(answer.results)}")
    if not answer.results.empty:
        print(f"Data:\n{answer.results.head().to_string(index=False)}")
    print(f"\nAI Answer: {answer.natural_answer}")


if __name__ == "__main__":
    main()
