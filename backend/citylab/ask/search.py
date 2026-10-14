"""Finding the right pages in the city's diary.

Two ways of searching, used together when both are available:

* **By words** (always on, nothing to install): BM25, the classic ranking used
  by search engines. Rare words that match count for more than common ones.
* **By meaning** (when a free local model is running): each event is turned into
  a list of numbers, an *embedding*, so that sentences that mean similar things
  ("a house was burgled" and "thieves broke into a home") sit close together,
  even with no words in common. The question gets one too, and the closest
  events are found by cosine similarity.

The index follows the event store: it reads new events as they are written, and
if the store's past is rewritten (a rule changed in the past), it starts again.
"""

from __future__ import annotations

import math
import re
import threading
from collections import defaultdict
from typing import Any, Callable

import numpy as np

STOP = frozenset(
    "a an and are as at be by for from has have he her his in is it its of on or she that the their they this to was were will with "
    "who what when where why which how many much did do does any there city kamalnagar tell me about happened doing going been "
    "has had our you your can could would last first latest ever".split()
)
SKIP_KINDS = frozenset({"reset"})
K1, B = 1.4, 0.75


def tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOP or len(w) < 2:
            continue
        # a light stemmer: thefts -> theft, burgled -> burgl, families -> famili
        for suf in ("ies", "ing", "ed", "es", "s"):
            if len(w) > len(suf) + 3 and w.endswith(suf):
                w = w[: -len(suf)] + ("i" if suf == "ies" else "")
                break
        out.append(w)
    return out


class Index:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.ids: list[int] = []  # event id of each document
            self.store_pos: list[int] = []  # where it sits in the store
            self.lengths: list[int] = []
            self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
            self.seen = 0  # store positions read so far
            self._last: Any = None  # the last event read, to notice if the store's past is rewritten
            self.vectors: np.ndarray | None = None  # one row per document that has been embedded
            self.embedded = 0
            self.embed_model = ""

    # ---- keeping up with the store ------------------------------------------------------

    def sync(self, events: list[Any]) -> int:
        """Read any events added to the store since last time. Returns how many were added."""
        with self.lock:
            if self.seen and (len(events) < self.seen or events[self.seen - 1] is not self._last):
                self.reset()  # the past was rewritten: read it all again
            added = 0
            for pos in range(self.seen, len(events)):
                e = events[pos]
                if e.kind in SKIP_KINDS:
                    continue
                doc = len(self.ids)
                toks = tokens(e.text)
                counts: dict[str, int] = defaultdict(int)
                for tok in toks:
                    counts[tok] += 1
                for tok, n in counts.items():
                    self.postings[tok].append((doc, n))
                self.ids.append(e.id)
                self.store_pos.append(pos)
                self.lengths.append(len(toks))
                added += 1
            self.seen = len(events)
            self._last = events[-1] if events else None
            return added

    # ---- searching ------------------------------------------------------------------------

    def by_words(self, query: str, allowed: Callable[[int], bool] | None = None, k: int = 20) -> list[tuple[int, float]]:
        """(document, score), best first."""
        with self.lock:
            n = len(self.ids)
            if not n:
                return []
            avg = sum(self.lengths) / n
            scores: dict[int, float] = defaultdict(float)
            for tok in set(tokens(query)):
                plist = self.postings.get(tok)
                if not plist:
                    continue
                idf = math.log(1 + (n - len(plist) + 0.5) / (len(plist) + 0.5))
                for doc, tf in plist:
                    if allowed is not None and not allowed(doc):
                        continue
                    scores[doc] += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * self.lengths[doc] / avg))
            return sorted(scores.items(), key=lambda kv: (-kv[1], -kv[0]))[:k]

    def add_vectors(self, vectors: list[list[float]], model: str) -> None:
        with self.lock:
            v = np.asarray(vectors, dtype=np.float32)
            v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
            self.vectors = v if self.vectors is None else np.vstack([self.vectors, v])
            self.embedded = len(self.vectors)
            self.embed_model = model

    def by_meaning(self, vector: list[float], allowed: Callable[[int], bool] | None = None, k: int = 20) -> list[tuple[int, float]]:
        with self.lock:
            if self.vectors is None or not len(self.vectors):
                return []
            q = np.asarray(vector, dtype=np.float32)
            q /= np.linalg.norm(q) + 1e-9
            sims = self.vectors @ q
            order = np.argsort(-sims)
            out = []
            for doc in order:
                if allowed is not None and not allowed(int(doc)):
                    continue
                out.append((int(doc), float(sims[doc])))
                if len(out) >= k:
                    break
            return out

    def pending_texts(self, events: list[Any], limit: int) -> list[str]:
        """Texts of documents not embedded yet, oldest first."""
        with self.lock:
            return [events[self.store_pos[d]].text for d in range(self.embedded, min(len(self.ids), self.embedded + limit))]


def blend(words: list[tuple[int, float]], meaning: list[tuple[int, float]], k: int) -> list[int]:
    """Reciprocal rank fusion: a document near the top of either list rises to the top."""
    score: dict[int, float] = defaultdict(float)
    for ranked in (words, meaning):
        for rank, (doc, _) in enumerate(ranked):
            score[doc] += 1.0 / (60 + rank)
    return [doc for doc, _ in sorted(score.items(), key=lambda kv: (-kv[1], -kv[0]))[:k]]
