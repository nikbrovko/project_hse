import sys
from pathlib import Path

import pandas as pd

from src.analysis import run_analysis
from src.collect_data import collect_all


ROOT = Path(__file__).resolve().parent


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "run"

    if command not in ["run", "collect", "analyze"]:
        print("Команды: python main.py, python main.py collect, python main.py analyze")
        return

    if command in ["run", "collect"]:
        collect_all()

    if command in ["run", "analyze"]:
        result = run_analysis()
        economics = pd.read_csv(ROOT / "data" / "processed" / "unit_economics.csv")
        print("Топ мест для Wash&Go:")
        print(result[["district", "score", "competitors_total", "traffic_score"]].head(5).to_string(index=False))
        print()
        print("Юнит-экономика лидеров:")
        print(economics[["district", "expected_washes_day", "monthly_profit", "payback_months"]].head(5).to_string(index=False))
        print()
        print("Графики сохранены в папку figures, таблицы в data/processed.")


if __name__ == "__main__":
    main()
