"""Collection receipts for pre-fetched sentiment sources (C3 evidence boundary).

A vendor fetch returns ``SourceText`` when the caller opts in with
``_with_receipt=True``. ``SourceText`` is still a plain string for every legacy
consumer (prompt blocks, ``str.startswith`` checks), but it carries a
collection-level ``SourceReceipt`` that says which source and vendor answered,
for which ticker and window, and which items the source reported.

The receipt deliberately carries item *metadata*, never raw post or article
bodies, so it can be shared as evidence. It also carries no ``run_id``: a
receipt is bound to a request (source, ticker, window); the run identity is
attached when the receipt is normalized against a specific run in
``tradingagents.agents.sentiment_coverage``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ItemMeta:
    """Metadata for one item a source returned (no raw body)."""

    item_id: str
    published_at: datetime | None
    ticker: str | None
    substantive: bool = True


@dataclass(frozen=True)
class SourceReceipt:
    """What one source collection returned for one request window."""

    source_id: str
    vendor: str
    ticker: str
    window_start: str
    window_end: str
    items: tuple[ItemMeta, ...] = ()
    reason_codes: tuple[str, ...] = ()


class SourceText(str):
    """A source result string that also carries its ``SourceReceipt``.

    Subclassing ``str`` keeps every existing consumer working unchanged; the
    receipt is read-only and attached by ``__new__``, so it cannot be swapped
    after construction.
    """

    def __new__(cls, text: str, source_receipt: SourceReceipt):
        instance = super().__new__(cls, "" if text is None else str(text))
        object.__setattr__(instance, "source_receipt", source_receipt)
        return instance

    def __setattr__(self, name, value):  # immutable receipt
        raise AttributeError("SourceText is immutable")

    def __delattr__(self, name):
        raise AttributeError("SourceText is immutable")

    def __reduce__(self):
        return (self.__class__, (str(self), self.source_receipt))
