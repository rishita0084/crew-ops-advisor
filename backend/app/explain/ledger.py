"""Evidence ledger.

Every fact the engine establishes is recorded here with its source. Two jobs:
  - it is what the controller expands to audit an answer, and
  - it is the whitelist the grounding verifier checks the LLM's prose against.

If a fact is not in the ledger, the system is not allowed to say it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvidenceItem:
    source: str
    fact: str
    value: str

    def to_dict(self) -> dict:
        return {"source": self.source, "fact": self.fact, "value": self.value}


@dataclass
class EvidenceLedger:
    items: list[EvidenceItem] = field(default_factory=list)
    _tokens: set[str] = field(default_factory=set)

    def add(self, source: str, fact: str, value) -> None:
        text = str(value)
        self.items.append(EvidenceItem(source=source, fact=fact, value=text))
        self._tokens.add(text)
        self._tokens.add(fact)

    def allow(self, *values) -> None:
        """Register a value as grounded without showing it as a separate evidence row."""
        for value in values:
            if value is None:
                continue
            self._tokens.add(str(value))

    @property
    def tokens(self) -> set[str]:
        return self._tokens

    def to_list(self) -> list[dict]:
        return [i.to_dict() for i in self.items]

    def __len__(self) -> int:
        return len(self.items)
