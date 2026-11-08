"""Source registry helpers: hashing, change classification, untrusted-text screening and the fetch allowlist.

Source text is untrusted data. Nothing in it is ever executed or followed; suspicious text is flagged for a human.
A changed webpage is not a changed law: a substantive change only becomes a *candidate* until a reviewer approves it.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import urlparse

# Hosts a future live collector may fetch from. Empty fetches are refused; this build never opens a network socket.
FETCH_ALLOWLIST = {"tax.gov.ae", "u.ae", "ded.ae", "dm.gov.ae", "mohre.gov.ae"}
LIVE_FETCH_ENABLED = False  # UNTESTED: no live collector in this build

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)",
    r"disregard (the )?(system|previous|above)",
    r"you are now",
    r"mark (all|every) (cases?|tasks?|items?) (as )?(resolved|closed|done|complete)",
    r"approve (this|all|every)",
    r"do not (tell|inform|show) (the )?(user|owner|reviewer)",
    r"<\s*script",
]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(text: str) -> str:
    """Remove formatting noise: case, whitespace, markdown emphasis, bullets, punctuation spacing."""
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"[*_#>`~|]+", " ", t)          # markdown and table marks
    t = re.sub(r"^\s*[-•·]\s*", " ", t, flags=re.M)  # bullets
    t = re.sub(r"[‘’]", "'", t)
    t = re.sub(r"[“”]", '"', t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s*([,.;:])\s*", r"\1 ", t)
    return t.strip()


def normalized_hash(text: str) -> str:
    return content_hash(normalize(text))


def classify_change(previous_text: str | None, new_text: str) -> str:
    if previous_text is None:
        return "first_version"
    if content_hash(previous_text) == content_hash(new_text):
        return "identical"
    if normalized_hash(previous_text) == normalized_hash(new_text):
        return "cosmetic"
    return "substantive"


def screen_untrusted(text: str) -> list[str]:
    """Return flags for instruction-like text. Flags hold a source for review; they never trigger actions."""
    low = text.lower()
    return [f"possible_instruction_injection: /{p}/" for p in INJECTION_PATTERNS if re.search(p, low)]


class FetchRefused(Exception):
    pass


def fetch_source(url: str) -> dict:
    """Live fetch is disabled. Allowlist check runs first so the refusal reason is explicit and testable."""
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname:
        raise FetchRefused(f"refused: only https URLs on the allowlist ({url})")
    host = u.hostname.lower()
    if not any(host == h or host.endswith("." + h) for h in FETCH_ALLOWLIST):
        raise FetchRefused(f"refused: host {host} is not on the source allowlist")
    if not LIVE_FETCH_ENABLED:
        return {"status": "unavailable", "reason": "live fetch disabled in this build (UNTESTED)", "url": url}
    raise FetchRefused("live fetch not implemented")  # pragma: no cover
