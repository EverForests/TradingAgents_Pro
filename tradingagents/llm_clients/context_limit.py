"""Deterministic final-message preparation for the NFR-02 scoped call sites.

Requirement: NFR-02 (docs/req/requirements.yaml) -- bound the final serialized
message size at the analyst-closure and neutral-risk call sites by removing
optional discussion history, and refuse requests whose required content cannot
fit.
Contract: C5 "deterministic prepared context" and the ``prepare_context``
boundary in docs/architecture/interface-contracts.md (interface v1.0).
ADR: ADR-001 "reduce optional history at the two scoped sites; reject irreducible
messages before budget reservation".
Invariant link: NFR-02 must reject *before* C4 reservation/send (INV-02 ordering),
so this module never sends anything and never calls a model.

Scope of this owner module: payload sizing and deterministic reduction only. It
does not mutate persisted state, does not summarize required content (that would
need an unmetered model call), and does not implement any request budget. The
default ``65536`` byte cap is the C5 *acceptance configuration*, not an
empirically justified production optimum, and byte counts are not token counts
(see ADR-001 "Token-budget design").

Two entry points share one reduction engine:

- :func:`prepare_context` for sites whose model input is a message array;
- :func:`prepare_text_context` for sites whose model input is one rendered prompt
  string, measured as a single user ``ChatMessage`` under the same canonical
  array form.

Both delegate to :func:`_reduce_oldest_first`, which owns the oldest-first
optional-group order, required-content preflight and ``ContextTooLarge``
behavior. Only assembly and measurement are supplied per site, so the reduction
algorithm exists once.

Blocks are classified by the caller (the scoped adapter at each call site):
``required`` blocks are role/task identity, standing rules, run/instrument
identity and current evidence; ``optional`` blocks are explicitly marked older
discussion history. Grouping metadata is never serialized into the model input.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# C5 acceptance cap for the scoped call sites (bytes of canonical UTF-8
# message). Configurable; not an empirically validated production threshold and
# not a token budget.
DEFAULT_MAX_MESSAGE_BYTES = 65536

# C0/C5 terminal execution reason for an unbounded scoped request.
CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"

READY = "READY"


class ContextTooLarge(Exception):
    """Typed terminal failure: required content cannot fit the message cap.

    C5 requires ``CONTEXT_TOO_LARGE`` with zero send, reservation and debit. This
    exception carries an identifiable reason so the graph entry can map it to the
    C0 ``CONTEXT_TOO_LARGE`` execution state without inspecting prose.
    """

    reason_code = CONTEXT_TOO_LARGE
    # Common-attribute alias so generic terminal-failure handling can read the
    # same reason without depending on this class name.
    reason = CONTEXT_TOO_LARGE

    def __init__(
        self,
        *,
        message_bytes: int,
        mandatory_bytes: int,
        max_message_bytes: int,
        site: str | None = None,
    ) -> None:
        self.message_bytes = message_bytes
        self.mandatory_bytes = mandatory_bytes
        self.max_message_bytes = max_message_bytes
        self.site = site
        location = f" at {site}" if site else ""
        super().__init__(
            f"CONTEXT_TOO_LARGE{location}: required context needs {mandatory_bytes} "
            f"bytes (full request {message_bytes} bytes) but the configured "
            f"message cap is {max_message_bytes} bytes"
        )


@dataclass(frozen=True)
class ChatMessage:
    """Provider-facing message. Mirrors the C5 ``ChatMessage`` record.

    ``content`` is preserved verbatim; no paraphrasing, splitting or trimming
    happens anywhere in this module.
    """

    role: str
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: Sequence[Mapping[str, Any]] | None = None
    reasoning_content: str | None = None

    def to_provider_message(self) -> dict[str, Any]:
        """Return the JSON-compatible provider-facing shape.

        Optional fields are omitted when absent so the serialized representation
        is stable and does not grow with explicit nulls.
        """

        message: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name is not None:
            message["name"] = self.name
        if self.tool_call_id is not None:
            message["tool_call_id"] = self.tool_call_id
        if self.tool_calls is not None:
            message["tool_calls"] = [dict(call) for call in self.tool_calls]
        if self.reasoning_content is not None:
            message["reasoning_content"] = self.reasoning_content
        return message


@dataclass(frozen=True)
class ContextBlock:
    """One reducible unit of context. C5 ``ContextBlock`` record.

    ``group_id`` and ``required`` are grouping metadata and are deliberately not
    part of the serialized model input. ``required`` applies to the whole block;
    a block is the atomic unit of removal, so an indivisible tool-call/result
    exchange must be complete inside a single block.
    """

    group_id: str
    required: bool
    messages: tuple[ChatMessage, ...]

    @classmethod
    def build(
        cls,
        group_id: str,
        messages: Iterable[ChatMessage],
        *,
        required: bool,
    ) -> ContextBlock:
        return cls(group_id=group_id, required=required, messages=tuple(messages))


@dataclass(frozen=True)
class PreparedRequest:
    """C5 ``PreparedRequest`` record.

    ``messages`` is ``None`` only when ``status`` is not ``READY``. The prepared
    messages are exactly what the caller must send: no additions may be appended
    after preparation, or the measured size stops describing the sent request.
    """

    status: str
    messages: tuple[ChatMessage, ...] | None
    message_bytes: int
    original_message_bytes: int
    dropped_group_ids: tuple[str, ...] = ()
    required_groups_ok: bool = True

    @property
    def ready(self) -> bool:
        return self.status == READY and self.messages is not None

    def as_provider_messages(self) -> list[dict[str, Any]]:
        """Provider-facing message array; the exclusive input to the transport."""

        if self.messages is None:
            raise ContextTooLarge(
                message_bytes=self.original_message_bytes,
                mandatory_bytes=self.original_message_bytes,
                max_message_bytes=0,
            )
        return [_provider_message(message) for message in self.messages]


def canonical_message_bytes(messages: Iterable[ChatMessage | Mapping[str, Any]]) -> int:
    """C5 canonical size of the final provider-facing messages, in UTF-8 bytes.

    Encoded as JSON with ``ensure_ascii=False``, ``sort_keys=True``,
    ``separators=(",", ":")``, ``allow_nan=False`` and then UTF-8. Grouping
    metadata is excluded because only provider-facing messages are measured.
    """

    encoded = json.dumps(
        [_provider_message(message) for message in messages],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return len(encoded.encode("utf-8"))


def prepare_context(
    blocks: Sequence[ContextBlock],
    max_message_bytes: int | None = None,
) -> PreparedRequest:
    """Fit ``blocks`` into ``max_message_bytes`` by dropping optional history.

    Deterministic behavior (C5):

    - A request already within the cap is returned unchanged, with no blocks
      dropped.
    - Otherwise, optional blocks are removed oldest first (stable original index
      for ties), the request is reassembled and re-measured. Required blocks are
      never removed or modified.
    - If the required blocks alone exceed the cap, ``ContextTooLarge`` is raised;
      no messages are returned, so the caller cannot send anything.
    - Identical input and configuration produce identical output.

    Args:
        blocks: Caller-classified context blocks in assembly order. Required
            blocks keep their order and content exactly.
        max_message_bytes: Configurable cap in UTF-8 bytes. Defaults to the C5
            acceptance configuration; values must be positive integers.

    Raises:
        ContextTooLarge: Required context cannot fit the configured cap.
        ValueError: Invalid configuration or a malformed block/pairing contract.
    """

    cap = _validate_cap(max_message_bytes)
    block_list = list(blocks)
    _validate_blocks(block_list)

    def assemble(retained: tuple[int, ...]) -> list[ChatMessage]:
        return _flatten_blocks(block_list, keep=set(retained))

    outcome = _reduce_oldest_first(
        block_list,
        cap,
        assemble=assemble,
        measure=canonical_message_bytes,
    )
    return PreparedRequest(
        status=READY,
        messages=tuple(outcome.messages),
        message_bytes=outcome.message_bytes,
        original_message_bytes=outcome.original_message_bytes,
        dropped_group_ids=tuple(
            block_list[index].group_id for index in outcome.dropped
        ),
        required_groups_ok=True,
    )


@dataclass(frozen=True)
class TextContextParts:
    """Caller-assembled text pieces of one scoped prompt.

    ``required_prefix`` + (retained optional turns) + ``required_suffix`` is the
    complete prompt. This shape lets a site whose model input is a single string
    use the shared reduction engine: it renders, measures the rendered prompt as
    ONE user ``ChatMessage`` (C5 canonical array), and removes optional turns
    oldest-first. Group ids for turns are ``turn-0000``, ``turn-0001``, ... in
    original order.
    """

    required_prefix: str
    optional_turns: tuple[str, ...]
    required_suffix: str

    def render(self, retained_turns: Iterable[str] = ()) -> str:
        return self.required_prefix + "".join(retained_turns) + self.required_suffix

    def render_full(self) -> str:
        return self.render(self.optional_turns)


def prepare_text_context(
    parts: TextContextParts,
    max_message_bytes: int | None = None,
) -> PreparedRequest:
    """Reduce a single-string scoped prompt via the shared C5 engine.

    Measurement is the C5 canonical UTF-8 size of ``[{role: "user", content:
    prompt}]`` -- the same :func:`canonical_message_bytes` used for structured
    sites, not a separate string standard. Reduction removes optional turns
    oldest-first, re-renders the complete prompt and re-measures; required text is
    never altered. If required text alone cannot fit, :class:`ContextTooLarge` is
    raised and no prompt is returned.

    The prepared request holds exactly one user message; the caller must send
    that message's ``content`` unchanged. Whether a provider adapter normalizes a
    bare string to one human/user message is an adapter property this module
    cannot observe and must be verified separately.
    """

    cap = _validate_cap(max_message_bytes)

    # Unit list holds ONLY the optional turns, one unit per turn, so engine
    # indices align 1:1 with ``parts.optional_turns`` and ``outcome.dropped``
    # needs no offset arithmetic. The required text is the fixed frame that
    # ``assemble`` always includes, which is also what the engine measures as
    # the required-only baseline (retained == ()).
    turn_units = [
        ContextBlock.build(f"turn-{index:04d}", [], required=False)
        for index in range(len(parts.optional_turns))
    ]

    def assemble(retained: tuple[int, ...]) -> list[ChatMessage]:
        kept = "".join(parts.optional_turns[index] for index in retained)
        prompt = parts.required_prefix + kept + parts.required_suffix
        return [ChatMessage(role="user", content=prompt)]

    outcome = _reduce_oldest_first(
        turn_units,
        cap,
        assemble=assemble,
        measure=canonical_message_bytes,
    )
    return PreparedRequest(
        status=READY,
        messages=tuple(outcome.messages),
        message_bytes=outcome.message_bytes,
        original_message_bytes=outcome.original_message_bytes,
        dropped_group_ids=tuple(
            turn_units[index].group_id for index in outcome.dropped
        ),
        required_groups_ok=True,
    )


def nonreducing_prepared_request(
    messages: Iterable[ChatMessage | Mapping[str, Any]],
) -> PreparedRequest:
    """Ready request without a size cap, for unscoped call sites.

    C5 applies the 64 KiB cap only to the two scoped sites; every other send is
    still bounded by C4. This adapter keeps the shared client boundary uniform
    without applying the cap where it is not a requirement.
    """

    provider_messages = tuple(_coerce_message(message) for message in messages)
    size = canonical_message_bytes(provider_messages)
    return PreparedRequest(
        status=READY,
        messages=provider_messages,
        message_bytes=size,
        original_message_bytes=size,
        required_groups_ok=True,
    )


# --- shared reduction engine -------------------------------------------------


@dataclass(frozen=True)
class _ReductionOutcome:
    messages: list[ChatMessage]
    message_bytes: int
    original_message_bytes: int
    dropped: tuple[int, ...]


def _reduce_oldest_first(
    units: Sequence[object],
    cap: int,
    *,
    assemble: Callable[[tuple[int, ...]], list[ChatMessage]],
    measure: Callable[[Iterable[ChatMessage | Mapping[str, Any]]], int],
) -> _ReductionOutcome:
    """The single oldest-first optional-unit reduction used by every site.

    ``units`` must implement ``required`` (they are ``ContextBlock`` instances).
    ``assemble(retained_indices)`` renders the caller's representation for the
    kept units; ``measure`` applies the caller's C5 measurement. The engine owns
    ordering, the required-only preflight and the terminal failure, so neither
    public entry point re-implements them.
    """

    full = assemble(tuple(range(len(units))))
    original_bytes = measure(full)
    if original_bytes <= cap:
        return _ReductionOutcome(full, original_bytes, original_bytes, ())

    required_only = assemble(
        tuple(index for index, unit in enumerate(units) if unit.required)
    )
    mandatory_bytes = measure(required_only)
    if mandatory_bytes > cap:
        raise ContextTooLarge(
            message_bytes=original_bytes,
            mandatory_bytes=mandatory_bytes,
            max_message_bytes=cap,
        )

    optional_order = [
        index for index, unit in enumerate(units) if not unit.required
    ]
    dropped: list[int] = []
    retained = set(range(len(units)))
    for index in optional_order:
        if measure(assemble(tuple(sorted(retained)))) <= cap:
            break
        retained.discard(index)
        dropped.append(index)

    kept = tuple(sorted(retained))
    messages = assemble(kept)
    message_bytes = measure(messages)
    if message_bytes > cap:
        raise ContextTooLarge(
            message_bytes=original_bytes,
            mandatory_bytes=mandatory_bytes,
            max_message_bytes=cap,
        )
    return _ReductionOutcome(messages, message_bytes, original_bytes, tuple(dropped))


# --- internals -------------------------------------------------------------


def _validate_cap(max_message_bytes: int | None) -> int:
    cap = DEFAULT_MAX_MESSAGE_BYTES if max_message_bytes is None else max_message_bytes
    if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
        raise ValueError(f"max_message_bytes must be a positive integer, got {cap!r}")
    return cap


def _validate_blocks(block_list: Sequence[ContextBlock]) -> None:
    """Reject malformed input before any measurement or removal happens.

    Validates only structural preconditions of the C5 algebra: unique nonempty
    ``group_id`` values and complete, unique, correctly ordered, single-block
    tool-call/result exchanges. Whether a block is required is decided by the
    caller per block; message kind (ordinary content vs tool exchange) has no
    bearing on it, so both may coexist in one block.
    """

    seen: set[str] = set()
    for block in block_list:
        if not isinstance(block, ContextBlock):
            raise TypeError(f"expected ContextBlock, got {type(block).__name__}")
        if not block.group_id:
            raise ValueError("ContextBlock.group_id must be nonempty")
        if block.group_id in seen:
            raise ValueError(f"duplicate ContextBlock.group_id {block.group_id!r}")
        seen.add(block.group_id)

    _validate_tool_pairs(block_list)


def _validate_tool_pairs(block_list: Sequence[ContextBlock]) -> None:
    """Ensure C5 tool-call/result pairs are indivisible inside one block.

    Checks actual call ids against assembly order:

    - every tool call has a nonempty string ``id`` and that id is unique across
      the whole request;
    - exactly one ``tool`` result exists for each call id;
    - the result belongs to the same block as its call (pairs cannot be split,
      so block removal drops both or neither);
    - the result appears after its call in assembly order;
    - no orphan result (result without a call) and no duplicate result id.
    """

    # call id -> (block index, message position within the flattened order)
    calls: dict[str, tuple[int, int]] = {}
    results: dict[str, tuple[int, int]] = {}
    position = 0

    for block_index, block in enumerate(block_list):
        for message in block.messages:
            for call in message.tool_calls or ():
                call_id = _tool_call_id(call)
                if call_id in calls:
                    raise ValueError(
                        f"duplicate tool call id {call_id!r}; a C5 tool-call/result "
                        "pair must be unique within the request"
                    )
                calls[call_id] = (block_index, position)
            if message.role == "tool":
                if not isinstance(message.tool_call_id, str) or not message.tool_call_id:
                    raise ValueError("a 'tool' message must carry a nonempty tool_call_id")
                if message.tool_call_id in results:
                    raise ValueError(
                        f"duplicate tool result for id {message.tool_call_id!r}"
                    )
                results[message.tool_call_id] = (block_index, position)
            position += 1

    orphans = sorted(set(results) - set(calls))
    if orphans:
        raise ValueError(f"tool result(s) without a paired tool call: {orphans!r}")

    for call_id, (call_block, call_position) in calls.items():
        if call_id not in results:
            raise ValueError(
                f"tool call {call_id!r} has no paired tool result; C5 pairs are indivisible"
            )
        result_block, result_position = results[call_id]
        if result_block != call_block:
            raise ValueError(
                f"tool call {call_id!r} and its result are in different blocks; "
                "a split pair cannot be reduced safely"
            )
        if result_position < call_position:
            raise ValueError(
                f"tool result for {call_id!r} appears before its call; "
                "pair order must be preserved"
            )


def _tool_call_id(call: Mapping[str, Any]) -> str:
    call_id = call.get("id") if isinstance(call, Mapping) else None
    if not isinstance(call_id, str) or not call_id:
        raise ValueError("each tool call must carry a nonempty string 'id'")
    return call_id


def _flatten_blocks(
    block_list: Sequence[ContextBlock],
    *,
    keep: set[int],
) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for index, block in enumerate(block_list):
        if index not in keep:
            continue
        messages.extend(block.messages)
    return messages


def _coerce_message(message: ChatMessage | Mapping[str, Any]) -> ChatMessage:
    if isinstance(message, ChatMessage):
        return message
    return ChatMessage(
        role=str(message["role"]),
        content=message["content"],
        name=message.get("name"),
        tool_call_id=message.get("tool_call_id"),
        tool_calls=message.get("tool_calls"),
        reasoning_content=message.get("reasoning_content"),
    )


def _provider_message(message: ChatMessage | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(message, Mapping):
        return message
    return message.to_provider_message()
