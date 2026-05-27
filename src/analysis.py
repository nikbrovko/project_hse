from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "input"
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
DOCS = ROOT / "docs"


def distance_km(lat1, lon1, lat2, lon2):
    radius = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def normalize(values, reverse=False):
    values = values.astype(float)
    low = values.min()
    high = values.max()
    if high == low:
        result = values * 0 + 0.5
    else:
        result = (values - low) / (high - low)
    if reverse:
        result = 1 - result
    return result


def count_nearby(points, lat, lon, radius):
    count = 0
    for row in points.itertuples():
        if distance_km(lat, lon, row.lat, row.lon) <= radius:
            count += 1
    return count


def portal_count(addresses, keywords, district):
    keys = keywords[keywords["district"] == district]["keyword"].tolist()
    count = 0
    for address in addresses["address"].dropna():
        lower_address = str(address).lower()
        for key in keys:
            if str(key).lower() in lower_address:
                count += 1
                break
    return count


def read_csv(path, columns):
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame(columns=columns)


def read_assumptions():
    path = INPUT / "unit_economics_assumptions.csv"
    data = pd.read_csv(path)
    return dict(zip(data["metric"], data["value"]))


def build_table():
    candidates = pd.read_csv(INPUT / "candidate_places.csv")
    keywords = pd.read_csv(INPUT / "portal_keywords.csv")
    osm = read_csv(RAW / "osm_car_washes.csv", ["osm_id", "name", "lat", "lon", "source"])
    portal = read_csv(RAW / "portal_addresses.csv", ["source", "address", "url"])

    candidates["osm_competitors_3km"] = candidates.apply(
        lambda row: count_nearby(osm, row["lat"], row["lon"], 3),
        axis=1,
    )
    candidates["portal_same_area"] = candidates["district"].apply(lambda name: portal_count(portal, keywords, name))
    candidates["competitors_total"] = candidates["osm_competitors_3km"] + candidates["portal_same_area"]
    candidates["density_people_km2"] = (candidates["population"] / candidates["area_km2"]).round(0)

    candidates["density_points"] = normalize(candidates["density_people_km2"])
    candidates["traffic_points"] = normalize(candidates["traffic_score"])
    candidates["rent_points"] = normalize(candidates["rent_index"], reverse=True)
    candidates["competition_points"] = normalize(candidates["competitors_total"], reverse=True)

    candidates["score"] = (
        candidates["density_points"] * 0.35
        + candidates["traffic_points"] * 0.30
        + candidates["rent_points"] * 0.15
        + candidates["competition_points"] * 0.20
    ).round(3)

    columns = [
        "district",
        "place",
        "address",
        "score",
        "population",
        "density_people_km2",
        "traffic_score",
        "rent_index",
        "osm_competitors_3km",
        "portal_same_area",
        "competitors_total",
        "source",
    ]
    return candidates.sort_values("score", ascending=False)[columns]


def build_unit_economics(table):
    assumptions = read_assumptions()
    result = table.copy()
    density = normalize(result["density_people_km2"])
    competition_load = normalize(result["competitors_total"])

    result["expected_washes_day"] = (
        assumptions["base_daily_washes"]
        + result["traffic_score"] * assumptions["traffic_weight_washes"]
        + density * assumptions["density_weight_washes"]
        - competition_load * assumptions["competition_penalty_washes"]
    ).round(0)
    result["expected_washes_day"] = result["expected_washes_day"].clip(lower=12).astype(int)
    result["price_per_wash"] = assumptions["price_per_wash"]
    result["variable_cost_per_wash"] = assumptions["variable_cost_per_wash"]
    result["contribution_per_wash"] = result["price_per_wash"] - result["variable_cost_per_wash"]
    result["monthly_revenue"] = result["expected_washes_day"] * assumptions["days_per_month"] * result["price_per_wash"]
    result["monthly_variable_cost"] = (
        result["expected_washes_day"] * assumptions["days_per_month"] * result["variable_cost_per_wash"]
    )
    result["monthly_fixed_cost"] = (
        assumptions["base_rent_month"] * result["rent_index"]
        + assumptions["service_cost_month"]
        + assumptions["equipment_payment_month"]
        + assumptions["marketing_month"]
    ).round(0)
    result["monthly_profit"] = (
        result["monthly_revenue"] - result["monthly_variable_cost"] - result["monthly_fixed_cost"]
    ).round(0)
    result["break_even_washes_day"] = (
        result["monthly_fixed_cost"] / result["contribution_per_wash"] / assumptions["days_per_month"]
    ).round(1)
    result["payback_months"] = (assumptions["investment_start"] / result["monthly_profit"]).round(1)

    columns = [
        "district",
        "place",
        "score",
        "expected_washes_day",
        "price_per_wash",
        "variable_cost_per_wash",
        "contribution_per_wash",
        "monthly_revenue",
        "monthly_variable_cost",
        "monthly_fixed_cost",
        "monthly_profit",
        "break_even_washes_day",
        "payback_months",
    ]
    return result.sort_values("monthly_profit", ascending=False)[columns]


def make_figures(table):
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "DejaVu Sans"

    top = table.head(8).sort_values("score")
    plt.figure(figsize=(10, 5))
    plt.barh(top["district"], top["score"], color="#4C8EA0")
    plt.xlabel("Итоговый балл")
    plt.title("Лучшие районы для первой точки Wash&Go")
    plt.tight_layout()
    plt.savefig(FIGURES / "top_locations.png", dpi=160)
    plt.close()

    by_competition = table.sort_values("competitors_total")
    plt.figure(figsize=(10, 5))
    plt.bar(by_competition["district"], by_competition["competitors_total"], color="#C07A50")
    plt.ylabel("Конкуренты в радиусе 3 км")
    plt.title("Конкурентная нагрузка")
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout()
    plt.savefig(FIGURES / "competition_by_district.png", dpi=160)
    plt.close()

    plt.figure(figsize=(7, 5))
    plt.scatter(table["competitors_total"], table["density_people_km2"], s=90, color="#5E8C61")
    for row in table.itertuples():
        plt.text(row.competitors_total + 0.05, row.density_people_km2, row.district, fontsize=8)
    plt.xlabel("Конкуренты")
    plt.ylabel("Плотность населения")
    plt.title("Спрос и конкуренция")
    plt.tight_layout()
    plt.savefig(FIGURES / "demand_vs_competition.png", dpi=160)
    plt.close()


def make_economics_figure(economics):
    top = economics.head(8).sort_values("monthly_profit")
    plt.figure(figsize=(10, 5))
    plt.barh(top["district"], top["monthly_profit"] / 1000, color="#D9A76A")
    plt.xlabel("Прибыль в месяц, тыс. рублей")
    plt.title("Юнит-экономика первой точки")
    plt.tight_layout()
    plt.savefig(FIGURES / "unit_economics_profit.png", dpi=160)
    plt.close()


def make_stats(table):
    median_competition = table["competitors_total"].median()
    low = table[table["competitors_total"] <= median_competition]
    high = table[table["competitors_total"] > median_competition]
    stats = pd.DataFrame(
        [
            {
                "group": "меньше конкурентов",
                "districts": len(low),
                "average_score": round(low["score"].mean(), 3),
                "average_density": round(low["density_people_km2"].mean(), 0),
            },
            {
                "group": "больше конкурентов",
                "districts": len(high),
                "average_score": round(high["score"].mean(), 3),
                "average_density": round(high["density_people_km2"].mean(), 0),
            },
        ]
    )
    stats.to_csv(PROCESSED / "stat_summary.csv", index=False)
    return stats


def write_report(table, stats, economics):
    DOCS.mkdir(parents=True, exist_ok=True)
    top = table.iloc[0]
    second = table.iloc[1]
    econ_top = economics.iloc[0]
    econ_revenue = f"{int(econ_top['monthly_revenue']):,}".replace(",", " ")
    econ_profit = f"{int(econ_top['monthly_profit']):,}".replace(",", " ")
    low_score = stats.iloc[0]["average_score"]
    high_score = stats.iloc[1]["average_score"]
    if low_score > high_score:
        idea_result = "Получилось, что районы с меньшей конкурентной нагрузкой в среднем выглядят лучше для запуска первой точки."
    else:
        idea_result = "Получилось, что низкая конкуренция сама по себе не гарантирует лучший район: плотность населения и трафик тоже сильно влияют на итоговый балл."
    text = f"""# Результаты анализа

Лучшее место по модели: **{top['district']}**, точка `{top['place']}`. Балл: `{top['score']}`.

На втором месте: **{second['district']}**, точка `{second['place']}`. Балл: `{second['score']}`.

## Что считалось

Для каждого района взяты плотность населения, простая оценка трафика, относительная стоимость аренды и число автомоек рядом. Чем выше плотность и трафик, тем лучше. Чем выше аренда и конкуренция, тем хуже.

## Юнит-экономика

Для первой точки отдельно рассчитана простая экономика: средний чек, переменная стоимость одной мойки, ожидаемое количество моек в день, фиксированные расходы, прибыль в месяц и срок окупаемости.

Лучший район по месячной прибыли: **{econ_top['district']}**. Ожидаемый поток: `{econ_top['expected_washes_day']}` моек в день. Месячная выручка: `{econ_revenue}` руб. Месячная прибыль: `{econ_profit}` руб. Окупаемость: `{econ_top['payback_months']}` месяца.

Подробная таблица лежит в `data/processed/unit_economics.csv`.

## Проверка идеи

Средний балл в группе `{stats.iloc[0]['group']}`: `{low_score}`.

Средний балл в группе `{stats.iloc[1]['group']}`: `{high_score}`.

{idea_result} Это практическая проверка на данных: она помогает выбрать район, а финальная аренда проверяется уже на конкретной площадке.

## Вывод

Для первой точки разумнее смотреть на районы с плотной жилой застройкой, нормальным автомобильным трафиком и не самым дорогим размещением. По текущей таблице лучше всего выглядят первые строки итогового рейтинга из `data/processed/location_scores.csv`.
"""
    (DOCS / "analysis_results.md").write_text(text, encoding="utf-8")


def run_analysis():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    table = build_table()
    table.to_csv(PROCESSED / "location_scores.csv", index=False)
    make_figures(table)
    economics = build_unit_economics(table)
    economics.to_csv(PROCESSED / "unit_economics.csv", index=False)
    make_economics_figure(economics)
    stats = make_stats(table)
    write_report(table, stats, economics)
    return table
