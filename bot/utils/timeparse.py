from __future__ import annotations

import re
from datetime import timedelta

_DURATION_RE = re.compile(r"(?P<value>\d+)\s*(?P<unit>s|sec|m|min|h|d|w)", re.IGNORECASE)
_UNIT_SECONDS = {
    "s": 1,
    "sec": 1,
    "m": 60,
    "min": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def parse_duration(raw: str, *, maximum: timedelta = timedelta(days=365)) -> timedelta:
    text = raw.strip().lower()
    matches = list(_DURATION_RE.finditer(text))
    if not matches or "".join(match.group(0).replace(" ", "") for match in matches) != text.replace(" ", ""):
        raise ValueError("Formato inválido. Usa, por ejemplo, `10m`, `2h`, `1d` o `1h30m`.")
    seconds = sum(int(match.group("value")) * _UNIT_SECONDS[match.group("unit")] for match in matches)
    if seconds < 5:
        raise ValueError("El tiempo mínimo es 5 segundos.")
    if seconds > int(maximum.total_seconds()):
        raise ValueError(f"El tiempo máximo es {maximum.days} días.")
    return timedelta(seconds=seconds)
