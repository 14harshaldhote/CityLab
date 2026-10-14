"""Reading a question: what it is about, where, when, and what kind of answer it wants.

No language model is needed for this part. A question is matched against the
words people use for each kind of event ("born", "babies" -> births), the names
of the city's neighbourhoods and people, and phrases of time ("last week",
"in January", "on 3 March"). The result says which records to look at and which
exact numbers to work out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ..core.clock import EPOCH, MINUTES_PER_DAY

# words people use -> event kinds in the city's diary
TOPICS: dict[str, tuple[str, ...]] = {
    "birth": ("born", "birth", "births", "baby", "babies", "newborn"),
    "death": ("died", "death", "deaths", "dead", "passed away", "funeral"),
    "couple": ("couple", "couples", "married", "marriage", "wedding", "love", "romance", "partner"),
    "hired": ("hired", "job", "jobs", "employment", "work for", "started work", "found work"),
    "laid_off": ("laid off", "lay-off", "lay-offs", "layoff", "fired", "lost their job", "lost jobs", "unemployment"),
    "arrived": ("arrived", "moved in", "moved here", "newcomer", "newcomers", "migrants", "migration", "immigrants"),
    "left": ("left the city", "moved away", "emigrated", "leaving"),
    "crime": ("crime", "crimes", "theft", "thefts", "thief", "thieves", "stolen", "stole", "robbed", "robbery", "burglary",
              "burglaries", "pickpocket", "pickpocketing", "shoplifting", "shoplift", "steal", "steals", "stealing", "criminal",
              "criminals", "rob", "robs", "burgled", "burglar", "burglars"),
    "arrest": ("arrest", "arrests", "arrested", "caught", "police"),
    "court": ("court", "trial", "verdict", "guilty", "judge", "convicted", "sentence", "jail", "prison"),
    "cctv": ("cctv", "camera", "cameras"),
    "traffic": ("traffic", "jam", "jams", "jammed", "rush hour", "congestion", "late for work"),
    "buses": ("bus", "buses", "passengers", "riders"),
    "roads": ("road", "roads", "street", "streets", "widen", "widened", "roadworks"),
    "construction": ("construction", "building site", "builders", "built", "being built"),
    "opened": ("opened", "new building", "new buildings", "new shop", "new homes"),
    "zoning": ("zoned", "zoning", "town planning", "new block"),
    "loan": ("loan", "loans", "borrowed", "borrow", "mortgage", "credit"),
    "default": ("default", "defaulted", "missed payment", "bad debt"),
    "festival": ("festival", "festivals", "diwali", "eid", "christmas", "holi", "vaisakhi", "navroz", "buddha purnima", "mahavir", "ganesh"),
    "school_start": ("started school", "first day of school"),
    "graduated": ("graduated", "finished school", "graduation"),
    "retired": ("retired", "retirement", "pension"),
    "report": ("report", "reports", "how is the city", "how's the city", "how did the city", "how is kamalnagar", "how did kamalnagar",
               "overview", "summary"),
    "weather": ("rain", "rained", "raining", "rainy", "weather", "monsoon", "hot", "hottest", "cold", "coldest", "temperature",
                "sunny", "cloudy", "storm"),
    "policy": ("rule", "rules", "council", "policy", "policies", "fare", "fares", "tax", "taxes", "interest rate", "benefit", "patrols"),
}

MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
SHORT = tuple(m[:3] for m in MONTHS)
FAITH_WORDS = ("religion", "religions", "religious", "faith", "faiths", "temple", "mosque", "church", "gurdwara", "hindu", "hindus", "muslim", "muslims", "christian", "christians", "sikh", "sikhs",
               "jain", "jains", "buddhist", "buddhists", "parsi", "parsis", "zoroastrian", "zoroastrians", "caste", "castes", "community", "communities")


@dataclass
class Question:
    text: str
    words: list[str]
    kinds: list[str] = field(default_factory=list)
    intent: str = "what"  # how_many | who | why | when | where | what | which
    start: int | None = None  # minute window, inclusive start
    end: int | None = None  # exclusive end
    window: str = ""  # the window in words
    districts: list[str] = field(default_factory=list)
    people: list[int] = field(default_factory=list)
    faith_and_crime: bool = False


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9' ]+", " ", s.lower())


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _intent(t: str) -> str:
    if re.search(r"\bhow (many|much)\b|\bnumber of\b|\bcount\b|\btotal\b", t):
        return "how_many"
    for word, intent in (("why", "why"), ("who", "who"), ("when", "when"), ("where", "where"), ("which", "which")):
        if _has(t, word):
            return intent
    return "what"


def _day_of(d: date) -> int:
    return (d - EPOCH.date()).days


def _window(t: str, now: int) -> tuple[int | None, int | None, str]:
    D = MINUTES_PER_DAY
    today = now // D
    if _has(t, "today"):
        return today * D, now + 1, "today"
    if _has(t, "yesterday"):
        return (today - 1) * D, today * D, "yesterday"
    m = re.search(r"\b(last|past) (\d+) (day|days|week|weeks)\b", t)
    if m:
        n = int(m.group(2)) * (7 if m.group(3).startswith("week") else 1)
        return max(0, now - n * D), now + 1, f"in the last {n} days"
    if re.search(r"\b(last|past|this) week\b", t):
        return max(0, now - 7 * D), now + 1, "in the last 7 days"
    if re.search(r"\b(last|past) month\b|\bthis month\b", t):
        return max(0, now - 30 * D), now + 1, "in the last 30 days"
    # "on 3 March", "3rd of March", "March 3"
    cur_year = date.fromordinal(EPOCH.date().toordinal() + today).year
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?(?: of)? (" + "|".join(MONTHS + SHORT) + r")\b(?: (\d{4}))?", t) or None
    m2 = re.search(r"\b(" + "|".join(MONTHS + SHORT) + r") (\d{1,2})(?:st|nd|rd|th)?\b(?: (\d{4}))?", t)
    if m or m2:
        if m:
            dd, mon, yy = int(m.group(1)), m.group(2), m.group(3)
        else:
            mon, dd, yy = m2.group(1), int(m2.group(2)), m2.group(3)  # type: ignore[union-attr]
        month = (MONTHS.index(mon) if mon in MONTHS else SHORT.index(mon)) + 1
        try:
            d = date(int(yy) if yy else cur_year, month, dd)
        except ValueError:
            d = None
        if d is not None:
            day = _day_of(d)
            return day * D, (day + 1) * D, f"on {d:%-d %B %Y}"
    m = re.search(r"\b(" + "|".join(MONTHS) + r")\b(?: (\d{4}))?", t)
    if m:
        month = MONTHS.index(m.group(1)) + 1
        year = int(m.group(2)) if m.group(2) else cur_year
        first = date(year, month, 1)
        nxt = date(year + (month == 12), month % 12 + 1, 1)
        return _day_of(first) * D, _day_of(nxt) * D, f"in {first:%B %Y}"
    m = re.search(r"\b(?:in|during) (\d{4})\b", t)
    if m:
        y = int(m.group(1))
        return _day_of(date(y, 1, 1)) * D, _day_of(date(y + 1, 1, 1)) * D, f"in {y}"
    m = re.search(r"\bday (\d+)\b", t)
    if m:
        day = int(m.group(1))
        return day * D, (day + 1) * D, f"on day {day}"
    return None, None, ""


def understand(text: str, now: int, districts: list[str], names: dict[str, list[int]]) -> Question:
    """``names`` maps lower-case full names (and surnames) to person ids."""
    t = _norm(text)
    q = Question(text=text.strip(), words=[w for w in t.split() if w])
    q.intent = _intent(t)
    for kind, phrases in TOPICS.items():
        if any(_has(t, p) for p in phrases):
            q.kinds.append(kind)
    if "how_many" == q.intent and "crime" in q.kinds and "arrest" in q.kinds and not re.search(r"arrest", t):
        q.kinds.remove("arrest")  # "how many thefts were caught on camera" is still about thefts
    q.start, q.end, q.window = _window(t, now)
    q.districts = [d for d in districts if _has(t, d.lower())]
    # people by full name first; a bare surname only if it names a single family
    for name, ids in sorted(names.items(), key=lambda kv: -len(kv[0])):
        if " " in name and _has(t, name):
            q.people.extend(i for i in ids if i not in q.people)
    q.faith_and_crime = any(_has(t, w) for w in FAITH_WORDS) and any(k in q.kinds for k in ("crime", "arrest", "court"))
    return q
