"""A free language model running on your own computer, through Ollama.

Ollama (https://ollama.com) is free and open source. It runs open models such as
Llama or Qwen on an ordinary laptop, with no account and no API key. CityLab
talks to it over plain HTTP on your own machine, so nothing ever leaves it.

If Ollama isn't running, or the model hasn't been downloaded yet, everything
still works: the city answers from its records with search and exact counts,
and just doesn't write the answer up in its own words.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger("citylab.ai")

# Least privilege: the model gets no tools and can't act on anything. The city only ever calls these three
# read-and-answer endpoints of the one server it was configured with, and doesn't follow redirects elsewhere.
PATHS = frozenset({"/api/tags", "/api/embed", "/api/chat"})
MAX_TOKENS = 300


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class LocalAI:
    def __init__(self, url: str, chat_model: str, embed_model: str, timeout: float = 120.0) -> None:
        url = url.strip().rstrip("/")
        if url and urllib.parse.urlparse(url).scheme not in ("http", "https"):
            raise ValueError(f"the local AI's address must start with http:// or https://, not {url!r}")
        self.url = url
        self._open = urllib.request.build_opener(_NoRedirects).open
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.timeout = timeout
        self._checked = 0.0
        self._models: set[str] = set()
        self._reachable = False

    def _call(self, path: str, body: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        if path not in PATHS:
            raise PermissionError(f"the city never calls {path}")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"}, method="POST" if body else "GET")
        with self._open(req, timeout=timeout or self.timeout) as res:  # noqa: S310 (an http(s) URL the owner configured)
            return json.loads(res.read())

    def status(self, force: bool = False) -> dict[str, Any]:
        """Is Ollama running, and are the two models downloaded? Checked at most every 30 seconds."""
        if self.url and (force or time.time() - self._checked > 30):
            self._checked = time.time()
            try:
                tags = self._call("/api/tags", timeout=2.0)
                self._models = {m["name"] for m in tags.get("models", [])} | {m["name"].split(":")[0] for m in tags.get("models", [])}
                self._reachable = True
            except (urllib.error.URLError, OSError, ValueError):
                self._reachable = False
                self._models = set()
        return {
            "url": self.url,
            "running": self._reachable,
            "chat_model": self.chat_model,
            "embed_model": self.embed_model,
            "can_write": self._reachable and self._has(self.chat_model),
            "can_embed": self._reachable and self._has(self.embed_model),
        }

    def _has(self, model: str) -> bool:
        return model in self._models or model.split(":")[0] in self._models and ":" not in model

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = self._call("/api/embed", {"model": self.embed_model, "input": texts})
        return out["embeddings"]

    def write(self, system: str, prompt: str) -> str:
        out = self._call(
            "/api/chat",
            {
                "model": self.chat_model,
                "stream": False,
                "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": MAX_TOKENS},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            },
        )
        return out["message"]["content"].strip()
