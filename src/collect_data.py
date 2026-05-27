from pathlib import Path
import html
import re

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

PORTAL_URL = "https://portalwash.ru/adress"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def get_page(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def clean_address(value):
    value = BeautifulSoup(value, "html.parser").get_text(" ")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    for marker in ["', class", '", class', '"">', '">', "#rec", ".t-btn", "</", "Подробнее", "Адреса", "Клиентам"]:
        value = value.split(marker)[0]
    value = value.replace("ул.", "ул. ")
    value = value.replace('"', "")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ,;:-'")


def collect_portal_addresses():
    text = get_page(PORTAL_URL)
    patterns = [
        r"Москва,\s*(?:ул\.|улица|МКАД|Северный бульвар|Ярославское ш\.|Ярославское шоссе|3-я Хорошёвская улица)[^<]{3,90}",
        r"Московская область,\s*[^<]{3,110}",
    ]
    addresses = []
    used = set()
    for pattern in patterns:
        for item in re.findall(pattern, text):
            address = clean_address(item)
            key_text = address.lower().replace("ё", "е").replace("ул.", "улица").replace("ш.", "шоссе")
            key = re.sub(r"[\s\"'>.,-]", "", key_text)
            if 12 <= len(address) <= 130 and key not in used:
                used.add(key)
                addresses.append(address)

    table = pd.DataFrame({"source": "PortalWash", "address": addresses, "url": PORTAL_URL})
    path = RAW / "portal_addresses.csv"
    table.to_csv(path, index=False)
    return table


def collect_osm_car_washes():
    query = """
    [out:json][timeout:40];
    (
      node["amenity"="car_wash"](55.48,37.25,55.98,38.05);
      way["amenity"="car_wash"](55.48,37.25,55.98,38.05);
      relation["amenity"="car_wash"](55.48,37.25,55.98,38.05);
    );
    out center tags;
    """
    columns = ["osm_id", "name", "lat", "lon", "source"]
    try:
        headers = {"User-Agent": "WashGo student project"}
        response = requests.get(OVERPASS_URL, params={"data": query}, headers=headers, timeout=70)
        response.raise_for_status()
        data = response.json()["elements"]
    except Exception:
        old_path = RAW / "osm_car_washes.csv"
        if old_path.exists():
            return pd.read_csv(old_path)
        table = pd.DataFrame(columns=columns)
        table.to_csv(old_path, index=False)
        return table

    rows = []
    used = set()
    for item in data:
        lat = item.get("lat") or item.get("center", {}).get("lat")
        lon = item.get("lon") or item.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = item.get("tags", {})
        osm_id = str(item.get("id"))
        if osm_id in used:
            continue
        used.add(osm_id)
        rows.append(
            {
                "osm_id": osm_id,
                "name": tags.get("name", "Автомойка"),
                "lat": lat,
                "lon": lon,
                "source": "OpenStreetMap Overpass API",
            }
        )

    table = pd.DataFrame(rows, columns=columns)
    table.to_csv(RAW / "osm_car_washes.csv", index=False)
    return table


def collect_all():
    RAW.mkdir(parents=True, exist_ok=True)
    portal = collect_portal_addresses()
    osm = collect_osm_car_washes()
    print(f"PortalWash адресов: {len(portal)}")
    print(f"OSM автомоек: {len(osm)}")
