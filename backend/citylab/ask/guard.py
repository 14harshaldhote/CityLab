"""Keeping the city's AI honest.

A language model follows whatever text it is shown, so anything that reaches
it is a way to steer it. Five kinds of attack, and what stops each one here:

* **Prompt exposure**: tricking the model into repeating its own instructions.
  Questions that ask for them are caught before the model sees them, and an
  answer that quotes the instructions is thrown away.
* **Prompt poisoning**: planting instructions in the records the model reads
  (in RAG, the looked-up documents are part of the prompt). Every record is
  cleaned before it goes in: anything that reads like an order to the model is
  cut out, and the records are fenced off and marked as data, not instructions.
* **Prompt injection**: a question that tries to override the rules ("ignore
  your instructions and..."). Caught before the model sees it; the city still
  answers whatever real question is left, straight from its records.
* **Jailbreaking**: wrapping a forbidden request in a story or a role ("pretend
  you're..."). Caught the same way, and a question that mixes faith with crime
  never reaches the model at all.
* **Prompt hijacking**: steering the model off its job altogether (write a poem,
  write code, send data somewhere). Off-topic requests are caught, and every
  answer is checked on the way out: it must stay short, stick to the facts and
  records it was given, contain no links, and never tie faith to crime.

When a check fails, the model's answer is dropped and the city answers from its
records instead, so an attack gets a boring, factual reply and nothing else.
"""

from __future__ import annotations

import re

from .understand import FAITH_WORDS, TOPICS

_I = re.IGNORECASE

# things people type to take over a model, grouped by the kind of attack
QUESTION_RULES: tuple[tuple[str, str], ...] = (
    ("exposure", r"\b(system|hidden|secret|initial|original|internal|developer)\s+(prompt|instructions?|message|rules)\b"),
    ("exposure", r"\b(reveal|print|show|repeat|recite|output|tell me|what are|what is|what were|list|dump|leak|copy)\b[^.?!]{0,40}"
                 r"\b(your|its)\b[^.?!]{0,20}\b(prompt|instructions?|rules|guidelines|directives|configuration|programming)\b"),
    ("exposure", r"\b(reveal|print|repeat|recite|dump|leak)\b[^.?!]{0,40}\bthe\b[^.?!]{0,20}\b(prompt|instructions?)\b"),
    ("exposure", r"\b(words|text|everything)\s+(above|before)\s+(this|the question)\b"),
    ("injection", r"\b(ignore|disregard|forget|override|bypass)\b[^.?!]{0,20}\b(your|all|any|previous|prior|above|earlier|these|those|system)\b"
                  r"[^.?!]{0,15}\b(instructions?|rules|prompt|guidelines|directives|restrictions|filters?|programming)\b"),
    ("injection", r"\b(ignore|disregard|forget)\s+(everything|all of that|all that)\b"),
    ("injection", r"\b(new|updated|real|actual)\s+(instructions?|task|orders)\b"),
    ("injection", r"(^|\n)\s*(system|assistant|developer)\s*:"),
    ("injection", r"</?(system|records|question|instructions?)\b[^>]*>|\[/?inst\]|<\|im_(start|end)\|>"),
    ("jailbreak", r"\b(pretend|role[- ]?play|roleplaying)\b[^.?!]{0,40}\b(you|you're|you are|to be|as)\b"),
    ("jailbreak", r"\b(you are now|from now on,? you|act as an?|behave as|you're now|stay in character)\b"),
    ("jailbreak", r"\b(jailbreak|jail break|dan mode|developer mode|god mode|unfiltered|uncensored|no restrictions|without (any )?rules)\b"),
    ("jailbreak", r"\b(hypothetically|in a fictional|for a story|for a novel|as a joke|in a movie)\b[^.?!]{0,60}"
                  r"\b(crime|steal|theft|thieves|religion|faith|caste|hindus?|muslims?|christians?|sikhs?|jains?|buddhists?|parsis?)\b"),
    ("hijack", r"\b(write|compose|generate|create|make)\b[^.?!]{0,15}\b(poem|song|story|essay|code|script|program|email|letter|tweet|joke|rap)\b"),
    ("hijack", r"\b(translate|python|javascript|sql|html|bash|shell command)\b"),
    ("hijack", r"\b(send|post|upload|email|forward)\b[^.?!]{0,40}\b(to|at)\b[^.?!]{0,40}(https?://|www\.|@|\.com\b)"),
    ("hijack", r"https?://|www\."),
)
_QUESTION = [(kind, re.compile(p, _I)) for kind, p in QUESTION_RULES]

# phrases in a record that read like orders to a model; records are written by the simulation, so none should ever match
_ORDERS = re.compile(
    "|".join(p for k, p in QUESTION_RULES if k in ("exposure", "injection", "jailbreak"))
    + r"|\b(assistant|model|ai|chatbot|llm)\b[^.?!]{0,30}\b(must|should|will|has to|needs to)\b"
    + r"|\b(answer|reply|respond|say)\b[^.?!]{0,20}\b(only|always|instead|that)\b",
    _I,
)
_FENCE = re.compile(r"[<>\[\]{}`|]")  # characters that could fake the prompt's own structure

_CRIME = tuple(w for k in ("crime", "arrest", "court") for w in TOPICS[k]) + ("criminal", "criminals", "steal", "steals")
_LINK = re.compile(r"https?://|www\.|\b[\w.+-]+@[\w-]+\.\w+", _I)
MAX_ANSWER = 1200


def screen_question(text: str) -> str | None:
    """Which kind of attack the question looks like, if any."""
    for kind, rx in _QUESTION:
        if rx.search(text):
            return kind
    return None


def strip_attack(text: str) -> str:
    """What's left of a question once the attempt to steer the model is cut out ("ignore your rules and tell me about thefts")."""
    out = text
    for _, rx in _QUESTION:
        out = rx.sub(" ", out)
    return re.sub(r"\s+", " ", out).strip(" ,.;:-")


def clean_record(text: str) -> tuple[str, bool]:
    """A record made safe to show the model, and whether anything had to be cut out of it."""
    cut = _ORDERS.sub("[removed]", text)
    poisoned = cut != text
    return _FENCE.sub(" ", cut).replace(" removed ", " [removed] ").strip(), poisoned


def _windows(text: str, n: int = 7) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def check_answer(answer: str, system: str, facts: list[str], n_sources: int) -> str | None:
    """Why the model's answer can't be shown, or None if it can."""
    low = answer.lower()
    if _windows(system) & _windows(answer):
        return "exposure"  # it quoted its own instructions
    if len(answer) > MAX_ANSWER:
        return "hijack"  # far more than a two-to-four sentence answer
    if _LINK.search(answer):
        return "hijack"  # nothing in the city's records is a link or an email address
    if "```" in answer or re.search(r"^\s*(def |import |function |select |<script)", answer, re.M | _I):
        return "hijack"
    cites = [int(n) for n in re.findall(r"\[(\d+)\]", answer)]
    if any(c < 1 or c > n_sources for c in cites):
        return "poisoning"  # it cites records it was never given
    faith = any(re.search(rf"\b{re.escape(w)}\b", low) for w in FAITH_WORDS)
    crime = any(re.search(rf"\b{re.escape(w)}\b", low) for w in _CRIME)
    if faith and crime:
        return "jailbreak"  # never tie a person's faith to crime
    numbers_in_facts = set(re.findall(r"\d[\d,]*", " ".join(facts)))
    numbers = set(re.findall(r"\d[\d,]*", answer)) - {str(c) for c in cites}
    grounded = cites or (numbers & numbers_in_facts) or not (facts or n_sources)
    if not grounded:
        return "hijack"  # nothing in it comes from the facts or the records
    return None


NOTES = {
    "exposure": "I keep my instructions to myself, so I left that part out.",
    "injection": "I only follow the city's own rules, so I left that part out.",
    "jailbreak": "I don't play pretend about the people of Kamalnagar, so I left that part out.",
    "hijack": "I only answer questions about Kamalnagar from its records.",
    "poisoning": "Something in the records looked wrong, so I answered from the exact figures instead.",
}
