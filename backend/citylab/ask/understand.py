"""Reading a question: what it is about, where, when, and what kind of answer it wants.

No language model is needed for this part. A question is matched against the
words people use for each kind of event ("born", "babies" -> births) and for each
subject the city keeps figures on (its budget, plans, doctors, happiness...), the
names of the city's neighbourhoods and people, and phrases of time ("last week",
"in January", "on 3 March"). Small spelling mistakes are forgiven ("mulicaplity"
reads as "municipality"), and people can be found by their first name alone. The
result says which records to look at and which exact numbers to work out.
"""

from __future__ import annotations

import difflib
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
    "crime": ("crime", "crimes", "theft", "thefts", "stolen goods", "thief", "thieves", "stolen", "stole", "robbed", "robbery", "burglary",
              "burglaries", "pickpocket", "pickpocketing", "shoplifting", "shoplift", "steal", "steals", "stealing", "criminal",
              "criminals", "rob", "robs", "burgled", "burglar", "burglars"),
    "arrest": ("arrest", "arrests", "arrested", "caught", "police action", "police actions"),
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
    "treated": ("doctor", "doctors", "patient", "patients", "check-up", "checkup", "treated", "treatment", "clinic", "nurse", "nurses"),
    "sick": ("sick", "ill", "illness", "illnesses", "disease", "diseases", "dengue", "fever", "pneumonia", "infection"),
    "tax_audit": ("audit", "audits", "audited", "dodge", "dodges", "dodging", "dodgers", "evade", "evades", "evasion", "evaders",
                  "cash in hand", "doesn't pay tax", "don't pay tax", "dont pay tax", "doesnt pay tax", "not paying tax", "unpaid tax"),
    "weather": ("rain", "rained", "raining", "rainy", "weather", "monsoon", "hot", "hottest", "cold", "coldest", "temperature",
                "sunny", "cloudy", "storm"),
    "policy": ("rule", "rules", "policy", "policies", "fare", "fares", "interest rate", "benefit"),
}

# subjects the city keeps figures on, beyond its diary of events
SUBJECTS: dict[str, tuple[str, ...]] = {
    "budget": ("budget", "cost", "costs", "costing", "spend", "spending", "spent", "expense", "expenses", "finances", "running the city",
               "running a city", "city money", "revenue", "income of the city", "money", "out of money", "running out", "broke", "bankrupt",
               "deficit", "afford"),
    "plans": ("municipality", "municipal", "corporation", "development", "developments", "plan", "plans", "planning", "upcoming",
              "project", "projects", "future", "department", "departments", "agency", "agencies", "government"),
    "police": ("police", "security", "safety", "safe", "patrol", "patrols", "policing", "crime rate", "law and order", "advancement"),
    "rich": ("rich", "richest", "wealthy", "wealthiest", "millionaire", "celebrity", "celebrities", "famous", "popular", "well known",
             "influential", "important people", "vip"),
    "story": ("story", "stories", "history", "tale", "journey", "so far", "biography"),
    "failed": ("failed", "failure", "failures", "fail", "problem", "problems", "issue", "issues", "wrong", "mistake", "mistakes",
               "shortage", "shortages", "struggling", "went wrong", "gone wrong", "delay", "delays", "delayed", "behind schedule"),
    "happiness": ("happy", "happiness", "unhappy", "wellbeing", "well-being", "satisfied", "satisfaction", "mood", "content", "morale",
                  "happiness index", "quality of life"),
    "feelings": ("feel", "feels", "feeling", "feelings", "emotion", "emotions", "emotional", "angry", "sad", "afraid", "scared",
                 "worried", "anxious", "joy", "joyful"),
    "opinions": ("think", "thinks", "opinion", "opinions", "view", "views", "approve", "approval", "trust", "complain", "complaints",
                 "rate", "rating", "brand", "branding", "reputation"),
    "health": ("health", "healthy", "hospital", "hospitals", "doctor", "doctors", "patient", "patients", "medical", "medicine",
               "medicines", "nurse", "nurses", "behave", "behaves", "behaviour", "behavior", "misdiagnosis", "misdiagnosed", "diagnosis"),
    "tax": ("tax", "taxes", "taxpayer", "taxpayers", "tax payer", "tax payers", "income tax"),
    "town": ("population", "how many people live", "people live in", "how many residents", "how many live", "how big", "how large",
             "residents", "census",
             "demographic", "demographics", "sex ratio", "how many households", "unemployment rate", "real india", "real world",
             "real town", "realistic", "lakh", "whole town", "town wide", "town-wide", "per capita"),
    "council": ("council", "councillor", "mayor", "leaders", "leadership"),
    "trend": ("changed", "over time", "trend", "trends", "since the first week", "since the start", "since it started", "since the beginning",
              "grown", "growth", "better or worse", "getting better", "getting worse", "first week"),
    "whatif": ("what if", "would happen", "what happens if", "suppose", "imagine if", "if we raise", "if we cut", "if income tax",
               "if the tax", "if bus fare", "if the bus fare"),
    "friends": ("friend", "friends", "friendship", "friendships", "best friend"),
}

# groups of people a question can single out ("what do unemployed people think", "how happy are doctors")
GROUPS: dict[str, tuple[str, ...]] = {
    "unemployed": ("unemployed", "jobless", "out of work", "looking for work", "job seekers", "without a job", "without jobs"),
    "retired": ("retired", "retirees", "pensioners", "elderly", "old people", "older people", "senior citizens"),
    "workers": ("workers", "employees", "working people", "employed"),
    "cash": ("cash in hand", "cash workers", "paid in cash"),
    "doctors": ("doctor", "doctors"),
    "police": ("police officers", "policemen", "officers", "cops", "constables"),
    "teachers": ("teachers", "teacher"),
    "poor": ("poor", "poorest", "poor people", "low income"),
    "rich": ("rich people", "richest people", "wealthy people", "the rich"),
}
# "who is the angriest person": the feeling a superlative asks about
EXTREMES: dict[str, tuple[str, ...]] = {
    "anger": ("angriest", "most angry", "most frustrated"),
    "joy": ("happiest", "most joyful", "most cheerful", "most upbeat"),
    "sadness": ("saddest", "most sad", "unhappiest", "most unhappy", "loneliest", "most depressed"),
    "fear": ("most worried", "most anxious", "most scared", "most afraid", "most fearful"),
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
    called: str = ""  # a first name that matched several people
    subjects: list[str] = field(default_factory=list)
    corrected: dict[str, str] = field(default_factory=dict)  # spelling slips forgiven
    faith_and_crime: bool = False
    groups: list[str] = field(default_factory=list)
    extreme: str = ""  # a feeling the question wants the most of ("the angriest person")


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


STOP = frozenset("the and are was were what who whom whose when where why which how many much does did have has had this that these those "
                 "there their they them with from about into over your you our for any all some most more less than then city "
                 "kamalnagar tell give show please".split())


def _vocabulary() -> set[str]:
    words: set[str] = set()
    for phrases in list(TOPICS.values()) + list(SUBJECTS.values()) + list(GROUPS.values()) + list(EXTREMES.values()):
        for ph in phrases:
            words.update(w for w in re.findall(r"[a-z]+", ph) if len(w) >= 4)
    return words | set(MONTHS)


VOCAB = _vocabulary()
# ordinary words that happen to look like city words ("person" is not a misspelt "prison")
COMMON = frozenset("""person persons people other others stats state states status statistics number numbers total place places
often change changes changed different great happened happen happens money month months years every those stuff today their
where house houses school schools street streets shops store stores party parties right night light price prices mother father
child children family families friend friends worker workers working works water power women woman pretty story start started
""".split())


def _correct(t: str, known: set[str]) -> tuple[str, dict[str, str]]:
    """Forgive small spelling slips by snapping unknown words to the nearest word the city knows."""
    fixes: dict[str, str] = {}
    out = []
    for w in t.split():
        if len(w) >= 5 and "'" not in w and w not in VOCAB and w not in known and w not in STOP and w not in COMMON:
            hit = difflib.get_close_matches(w, VOCAB, n=1, cutoff=0.75 if len(w) >= 6 else 0.8)
            if hit and hit[0][0] == w[0] and abs(len(hit[0]) - len(w)) <= 2:
                fixes[w] = hit[0]
                w = hit[0]
        out.append(w)
    return " ".join(out), fixes


def understand(text: str, now: int, districts: list[str], names: dict[str, list[int]], first_names: dict[str, list[int]] | None = None) -> Question:
    """``names`` maps lower-case full names to person ids; ``first_names`` maps lower-case first names to ids."""
    first_names = first_names or {}
    raw = _norm(text)
    known = {w for d in districts for w in d.lower().split()} | {w for n in names for w in n.split()}
    t, fixes = _correct(raw, known)
    q = Question(text=text.strip(), words=[w for w in t.split() if w], corrected=fixes)
    q.intent = _intent(t)
    for kind, phrases in TOPICS.items():
        if any(_has(t, p) for p in phrases):
            q.kinds.append(kind)
    for subject, phrases in SUBJECTS.items():
        if any(_has(t, p) for p in phrases):
            q.subjects.append(subject)
    if "failed" in q.subjects and "health" in q.subjects and "plans" not in q.subjects:
        q.subjects.remove("failed")  # a doctor's "mistakes" are about the hospital, not failed city plans
    q.groups = [g for g, phrases in GROUPS.items() if any(_has(t, p) for p in phrases)]
    q.extreme = next((f for f, phrases in EXTREMES.items() if any(_has(t, p) for p in phrases)), "")
    if q.extreme and "feelings" not in q.subjects:
        q.subjects.append("feelings")
    if "how_many" == q.intent and "crime" in q.kinds and "arrest" in q.kinds and not re.search(r"arrest", t):
        q.kinds.remove("arrest")  # "how many thefts were caught on camera" is still about thefts
    q.start, q.end, q.window = _window(t, now)
    q.districts = [d for d in districts if _has(t, d.lower())]
    # people by full name first; otherwise a capitalised first name ("Neha") stands for everyone of that name
    for name, ids in sorted(names.items(), key=lambda kv: -len(kv[0])):
        if " " in name and _has(t, name):
            q.people.extend(i for i in ids if i not in q.people)
    if not q.people:
        caps = re.findall(r"\b([A-Z][a-z]{2,})\b", text)
        for w in caps:
            ids = first_names.get(w.lower())
            if ids and w.lower() not in VOCAB and w.lower() not in STOP and not any(w.lower() in d.lower().split() for d in districts):
                q.people = list(ids)
                q.called = w
                break
    q.faith_and_crime = any(_has(raw, w) for w in FAITH_WORDS) and (any(k in q.kinds for k in ("crime", "arrest", "court"))
                                                                   or "police" in q.subjects)
    return q
