"""Grounding verifier -- the last gate before any text reaches a controller.

The LLM writes the prose. This checks the prose against the evidence ledger: every crew
id, flight id, pairing id, rule id and money figure it mentions must have been produced
by the engine. Anything else is an invented fact, and an invented fact in crew ops is
worse than no answer.

Unverified claims do not silently disappear -- the response is marked ungrounded and the
offending claims are listed, so the failure is visible rather than plausible.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.explain.ledger import EvidenceLedger

CREW_RE = re.compile(r"\bC-\d{4}\b")
FLIGHT_RE = re.compile(r"\bDX\d{3}\b")
PAIRING_RE = re.compile(r"\bP-\d{4}\b")
RULE_RE = re.compile(r"\bRULE-[A-Z]+-\d{2}\b")
MONEY_RE = re.compile(r"(?:INR|Rs\.?|₹)\s?([\d,]+)")
HOURS_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s?(?:h\b|hours?\b)")

# Small integers and round numbers appear in ordinary prose ("all 3 flights"), so only
# figures large enough to be a cost or a duty total are worth verifying.
MONEY_FLOOR = 1000


@dataclass
class GroundingResult:
    verified: bool
    unverified_claims: list[str]

    def to_dict(self) -> dict:
        return {"verified": self.verified, "unverified_claims": self.unverified_claims}


def _numeric_tokens(ledger: EvidenceLedger) -> set[str]:
    """Every number the engine produced, normalised so 18500 == 18,500 == 18500.0."""
    out: set[str] = set()
    for token in ledger.tokens:
        for match in re.findall(r"\d+(?:\.\d+)?", token.replace(",", "")):
            out.add(match)
            if match.endswith(".0"):
                out.add(match[:-2])
            out.add(match.split(".")[0])
    return out


DASHES = dict.fromkeys(
    # models routinely emit non-breaking and typographic dashes inside ids ("C‑3310")
    # and unicode minus/figure dashes inside numbers; normalise before matching or the
    # verifier silently stops seeing the claims it exists to check
    map(ord, "‐‑‒–—―−－"), "-"
)
SPACES = dict.fromkeys(map(ord, "    "), " ")


def normalise(text: str) -> str:
    return text.translate(DASHES).translate(SPACES)


def verify(text: str, ledger: EvidenceLedger) -> GroundingResult:
    """Check every checkable claim in `text` against `ledger`."""
    if not text:
        return GroundingResult(verified=True, unverified_claims=[])
    text = normalise(text)

    grounded = {t for t in ledger.tokens}
    numbers = _numeric_tokens(ledger)
    unverified: list[str] = []

    def flag(claim: str) -> None:
        if claim not in unverified:
            unverified.append(claim)

    for pattern, label in (
        (CREW_RE, "crew"),
        (PAIRING_RE, "pairing"),
        (RULE_RE, "rule"),
    ):
        for match in pattern.findall(text):
            if not any(match in token for token in grounded):
                flag(f"{label} {match} does not appear in the evidence for this answer")

    for match in FLIGHT_RE.findall(text):
        # flight ids are stored as DX412-2026-09-15; the prose usually says DX412
        if not any(match in token for token in grounded):
            flag(f"flight {match} does not appear in the evidence for this answer")

    for raw in MONEY_RE.findall(text):
        value = raw.replace(",", "")
        if value.isdigit() and int(value) >= MONEY_FLOOR and value not in numbers:
            flag(f"cost figure {raw} was not produced by the cost model")

    for raw in HOURS_RE.findall(text):
        stripped = raw.rstrip("0").rstrip(".") if "." in raw else raw
        if raw not in numbers and stripped not in numbers and raw.split(".")[0] not in numbers:
            flag(f"duration {raw}h was not produced by the rules engine")

    return GroundingResult(verified=not unverified, unverified_claims=unverified)


def redact(text: str, result: GroundingResult) -> str:
    """Append an explicit warning rather than quietly deleting a sentence."""
    if result.verified:
        return text
    return (
        text
        + "\n\n[Ungrounded content detected and flagged: "
        + "; ".join(result.unverified_claims)
        + ". Treat those specifics as unverified.]"
    )
