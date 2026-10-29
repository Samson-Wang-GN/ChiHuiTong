"""Mainland administrative divisions, from the documented 2025 reference data."""

from functools import lru_cache
from pathlib import Path

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .identity import request_actor


@lru_cache(maxsize=1)
def region_tree():
    path = Path(__file__).resolve().parent / "data" / "administrative-divisions-2025.txt"
    rows = [
        line.strip().split(maxsplit=1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    provinces = {}
    cities = {}
    for code, name in rows:
        if int(code[:2]) > 65:
            continue
        if code.endswith("0000"):
            provinces[code[:2]] = {"name": name, "cities": []}
        elif code.endswith("00"):
            city = {"name": name, "districts": []}
            cities[code[:4]] = city
            provinces[code[:2]]["cities"].append(city)
    for code, name in rows:
        if int(code[:2]) > 65 or code.endswith("00"):
            continue
        province = provinces[code[:2]]
        city = cities.get(code[:4])
        if city is None:
            city = cities.get(code[:2] + "_direct")
            if city is None:
                city = {"name": province["name"], "districts": []}
                cities[code[:2] + "_direct"] = city
                province["cities"].append(city)
        city["districts"].append(name)
    # Some prefecture-level cities have no county-level division (e.g. 东莞).
    # Repeat the city name as the final choice rather than inventing a district.
    for province in provinces.values():
        for city in province["cities"]:
            if not city["districts"]:
                city["districts"] = [city["name"]]
    return list(provinces.values())


@api_view(["GET"])
def regions(request):
    request_actor(request)
    return Response({"version": "2025-12-31", "provinces": region_tree()})
