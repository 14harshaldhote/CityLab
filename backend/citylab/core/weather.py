"""Weather and daylight for the city.

Daylight comes from the NOAA solar position (``solar.py``, carried over from
LotusLab). Weather is a deterministic synthetic generator with a seasonal climate
(defaults: a monsoon city like Pune). Each day's weather is generated from its own
seed, so asking about any day, in any order, always gives the same answer; that is
what lets the city be rewound and replayed exactly.

Real Open-Meteo weather can be plugged in later behind the same ``WeatherNow`` shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .clock import EPOCH, MINUTES_PER_DAY, SimTime
from .rng import stable_hash
from .solar import solar_position

# Monthly climate: mean temperature (C), daily temperature range (C), chance a day has rain.
PUNE_CLIMATE = (
    (21.0, 17.0, 0.02), (23.0, 18.0, 0.02), (27.0, 18.0, 0.04), (30.0, 17.0, 0.07),
    (30.0, 14.0, 0.15), (27.0, 9.0, 0.55), (25.0, 6.0, 0.80), (24.5, 6.0, 0.75),
    (25.0, 8.0, 0.55), (25.5, 12.0, 0.25), (23.0, 15.0, 0.08), (21.0, 16.0, 0.03),
)


@dataclass(frozen=True, slots=True)
class WeatherNow:
    temperature_c: float
    rain_mm_h: float
    cloud_pct: float
    sun_elevation_deg: float
    sun_azimuth_deg: float  # clockwise from north
    phase: int  # 0 night, 1 twilight, 2 golden, 3 day (same codes as LotusLab)

    @property
    def raining(self) -> bool:
        return self.rain_mm_h > 0.2

    @property
    def dark(self) -> bool:
        return self.phase <= 1

    def to_dict(self) -> dict:
        return {
            "temperature_c": round(self.temperature_c, 1),
            "rain_mm_h": round(self.rain_mm_h, 2),
            "cloud_pct": round(self.cloud_pct),
            "sun_elevation_deg": round(self.sun_elevation_deg, 2),
            "sun_azimuth_deg": round(self.sun_azimuth_deg, 1),
            "phase": self.phase,
        }


class Weather:
    def __init__(self, seed: int, lat: float = 18.52, lon: float = 73.86, utc_offset_min: int = 330) -> None:
        self.seed = seed
        self.lat = lat
        self.lon = lon
        self.utc_offset_min = utc_offset_min
        self._day = lru_cache(maxsize=64)(self._generate_day)
        self._last_t = -1
        self._last: WeatherNow | None = None

    def at(self, t: int) -> WeatherNow:
        if t == self._last_t:
            return self._last
        self._last_t, self._last = t, self._at(t)
        return self._last

    def _at(self, t: int) -> WeatherNow:
        day = self._day(t // MINUTES_PER_DAY)
        m = t % MINUTES_PER_DAY
        h = m // 60
        f = (m % 60) / 60.0
        h2 = min(h + 1, 24)
        temp = day["temp"][h] * (1 - f) + day["temp"][h2] * f
        elev = day["elev"][h] * (1 - f) + day["elev"][h2] * f
        a0, a1 = day["azim"][h], day["azim"][h2]
        da = (a1 - a0 + 180.0) % 360.0 - 180.0
        azim = (a0 + da * f) % 360.0
        return WeatherNow(
            temperature_c=float(temp),
            rain_mm_h=float(day["rain"][h]),
            cloud_pct=float(day["cloud"][h]),
            sun_elevation_deg=float(elev),
            sun_azimuth_deg=float(azim),
            phase=0 if elev < -6.0 else 1 if elev < 0.0 else 2 if elev < 6.0 else 3,
        )

    def _generate_day(self, day: int) -> dict[str, np.ndarray]:
        rng = np.random.default_rng(stable_hash("weather", self.seed, day))
        start = SimTime(day * MINUTES_PER_DAY)
        month = start.datetime.month
        mean, rng_c, p_rain = PUNE_CLIMATE[month - 1]
        # 25 hourly points (00:00 .. 24:00) so interpolation never runs off the end
        local_unix = EPOCH.timestamp() + day * 86400 + 3600 * np.arange(25)
        sun = solar_position(local_unix - self.utc_offset_min * 60, self.lat, self.lon)
        mean += rng.normal(0.0, 1.5)
        temp = mean + 0.5 * rng_c * np.cos(np.radians(sun.hour_angle_deg - 45.0))
        rain = np.zeros(25)
        cloud = np.clip(25.0 + 100 * p_rain * 0.6 + rng.normal(0, 12, 25), 0, 100)
        if rng.random() < p_rain:
            start_h = int(rng.integers(0, 24))
            length = int(rng.integers(1, 6))
            total = float(rng.gamma(2.0, 5.0))
            rain[start_h : start_h + length] = total / length
            cloud[max(0, start_h - 2) : start_h + length + 1] = np.maximum(cloud[max(0, start_h - 2) : start_h + length + 1], 85.0)
            temp[start_h : start_h + length] -= 2.0
        return {"temp": temp, "rain": rain, "cloud": cloud, "elev": sun.elevation_deg, "azim": sun.azimuth_deg}
