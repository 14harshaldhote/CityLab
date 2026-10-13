"""Places of worship, when people go to them, and the festivals of the year.

Each faith has its own place (a mandir, a masjid, a church, a gurudwara, a Buddha
vihar, a Jain derasar, a Parsi agiary) and its own rhythm:

* Hindus visit the temple in the morning or for the evening aarti.
* Muslims may pray at the masjid at dawn or sunset, and many join Friday's midday
  prayer (Jumu'ah).
* Christians go to Sunday morning Mass.
* Sikhs visit the gurudwara morning or evening and eat at its free kitchen (langar).
* Buddhists gather at the vihar on Sunday mornings.
* Jains visit the derasar in the morning.
* Parsis visit the agiary in the morning or evening.

How often a person goes depends on their own devotion (some go daily, many weekly,
some only on festival days). Festivals bring far more people, all day. Festival days
follow the 2026 calendar; lunar dates drift a little in later years, which a
simulation can live with.
"""

from __future__ import annotations

from dataclasses import dataclass

from .clock import MINUTES_PER_HOUR as H

FRIDAY, SUNDAY = 4, 6  # SimTime.weekday: 0 = Monday


@dataclass(frozen=True, slots=True)
class Service:
    weekday: int | None  # None: every day
    start: int  # window in which people arrive, minute of day
    end: int
    weight: float
    stay: int  # minutes


@dataclass(frozen=True, slots=True)
class Faith:
    place: str | None  # building kind
    services: tuple[Service, ...]


FAITHS: dict[str, Faith] = {
    "hindu": Faith("temple", (Service(None, 6 * H, 9 * H, 1.0, 30), Service(None, 18 * H, 20 * H + 30, 1.0, 40))),
    "muslim": Faith("mosque", (
        Service(FRIDAY, 12 * H + 15, 14 * H, 3.4, 60),
        Service(None, 5 * H, 6 * H + 30, 1.0, 25),
        Service(None, 18 * H + 15, 19 * H + 30, 1.0, 25),
    )),
    "christian": Faith("church", (Service(SUNDAY, 8 * H, 10 * H + 30, 2.6, 90), Service(None, 18 * H, 19 * H, 0.3, 30))),
    "sikh": Faith("gurudwara", (Service(None, 5 * H, 8 * H, 1.0, 60), Service(None, 18 * H, 20 * H + 30, 1.0, 60))),
    "buddhist": Faith("vihara", (Service(SUNDAY, 8 * H, 11 * H, 2.0, 75), Service(None, 18 * H, 20 * H, 0.6, 40))),
    "jain": Faith("derasar", (Service(None, 6 * H, 9 * H, 1.4, 40),)),
    "parsi": Faith("agiary", (Service(None, 7 * H, 9 * H, 1.0, 30), Service(None, 17 * H, 19 * H, 0.7, 30))),
    "none": Faith(None, ()),
}

PLACE_KINDS = ("temple", "mosque", "church", "gurudwara", "vihara", "derasar", "agiary")
FESTIVAL_SERVICE = Service(None, 7 * H, 21 * H, 3.0, 90)

# day of year (0 = 1 January) -> (faith, festival, what happens)
FESTIVALS: dict[int, tuple[str, str, str]] = {
    13: ("hindu", "Makar Sankranti", "families share tilgul and fly kites"),
    62: ("hindu", "Holi", "the streets fill with colour"),
    78: ("muslim", "Eid al-Fitr", "the month of Ramadan ends with prayers and sheer khurma shared with neighbours"),
    89: ("jain", "Mahavir Jayanti", "the Jain community celebrates the birth of Lord Mahavira"),
    105: ("sikh", "Vaisakhi", "the gurudwara holds a special kirtan and a big langar"),
    120: ("buddhist", "Buddha Purnima", "the vihar is lit with lamps for the Buddha's birth, enlightenment and passing"),
    146: ("muslim", "Eid al-Adha", "families pray together and share food with the needy"),
    226: ("parsi", "Navroz", "the Parsi community celebrates its new year at the agiary"),
    256: ("hindu", "Ganesh Chaturthi", "Ganpati arrives in homes and pandals across the city"),
    311: ("hindu", "Diwali", "every street glows with diyas and lanterns"),
    327: ("sikh", "Guru Nanak Jayanti", "the gurudwara celebrates Guru Nanak's birth with prayers and langar for all"),
    358: ("christian", "Christmas", "the church holds midnight Mass and homes put up stars"),
}


def festival_on(day_of_year: int) -> tuple[str, str, str] | None:
    return FESTIVALS.get(day_of_year)
