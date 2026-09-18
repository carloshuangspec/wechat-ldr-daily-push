import re


VALID_DAYPARTS = frozenset({"morning", "afternoon", "evening", "night"})
VALID_WEATHER_CUES = frozenset(
    {"clear", "cloudy", "rainy", "snowy", "foggy", "stormy"}
)

_LABELS = {
    "clear": "clear",
    "fair": "clear",
    "sunny": "clear",
    "ptly cloudy": "cloudy",
    "cloudy": "cloudy",
    "overcast": "cloudy",
    "rain": "rainy",
    "drizzle": "rainy",
    "showers": "rainy",
    "icy rain": "rainy",
    "icy driz": "rainy",
    "snow": "snowy",
    "snow shwr": "snowy",
    "fog": "foggy",
    "storm": "stormy",
    "hail storm": "stormy",
}


def daypart(clock: str) -> str:
    if not isinstance(clock, str) or re.fullmatch(
        r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock
    ) is None:
        raise ValueError("Invalid local clock")

    hour = int(clock[:2])
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def weather_cue(report: str) -> str | None:
    if not isinstance(report, str):
        return None

    match = re.fullmatch(r"(.+?) -?[0-9]{1,3}°C", report)
    label = match.group(1) if match else report
    return _LABELS.get(label.lower())
