# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One bounded pass over a Claude process's stream: every request it names, and what it reports of the process.

A request is keyed the way the frames that name it are. An `assistant` frame is keyed by the message it names -- its
`message.id`, else its wrapper's `api_message_id` -- then by the frame's `request_id`, then by its place in the stream,
so the blocks of one message are one request. The trajectory numbers its turn the same way but reads no wrapper id, so
the turn a request links is the trajectory's own, numbered under the key the request is settled under. Every
stream event names its message through its wrapper's `api_message_id`, so it folds into the same request: a
`message_start` or `message_delta` with the usage it carries, and a content event as the message's witness alone, so a
message the stream printed but never reported usage for is still a request it knows of. A `message_start` naming no
message is a request of its own line, while a `message_delta` naming none settles nothing it could be told apart from
and is an `unindexed-frames` gap where it carries usage. A subagent hand-back -- a lead-thread `user` frame whose
`tool_use_result` carries a `usage` and either names an `agentId` or answers a call the stream already named a
subagent for -- is keyed by the call it answers, exactly as the run accounting's settlement keys it, so a repeated
hand-back of one call is one request and a resumed subagent answering a new call another, and one answering no named
call by its place in the stream. A tool's result answering any other call is no request, whatever it carries. A
frame naming a message by both its id and its `request_id` joins the two keys (`RequestIndex`), so frames naming it by
either are one request, while one naming a message on itself and another on its wrapper names no one message and folds
into neither, an `identity-conflicting` gap.

Every event is also fed to the trajectory's own `ClaudeTurnUsageBuilder`, whose turn numbering and settlement --
the run accounting's, message by message -- this collection reads rather than re-derives. Correlation is held to the
collection bounds: at most `MAX_TRACKED_STEPS` requests, past which a new request is a `correlation-limit` gap, and
every identity, model name, and timestamp through the metadata bound. The builder is held to the same bound: the first
event taking any of its correlation maps past `MAX_TRACKED_STEPS` identities drops it, a `correlation-limit` gap, and
from then on nothing is read off it -- the turns already linked stay, being the trajectory's numbering of the events
before, while no hand-back turn is numbered and nothing is settled through `modelUsage`, which both need every
message the stream printed.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from orchestrator.observability.usage import (
    claude_requests,
    claude_rows,
    protocol,
    request_coverage as coverage,
    request_models,
    request_scan,
    trajectory_claude_stream,
    trajectory_claude_turns,
)
from orchestrator.observability.usage.model_names import CLAUDE_MODEL_PATHS, nonempty_string
from orchestrator.observability.usage.request_claude_counters import malformed_usage, usage_readings
from orchestrator.observability.usage.request_claude_messages import Names, RequestFold, handback_names
from orchestrator.observability.usage.request_claude_reports import SESSION_ID, Process

TURN = "turn"
HANDBACK = "handback"
LINE = "line"
_EVENT = "event"
_AGENT_ID = "agentId"
_FRAME_AGENT_ID = "agent_id"
_API_MESSAGE_ID = "api_message_id"
_REQUEST_ID = "request_id"
_TIMESTAMP = "timestamp"
_STREAM_EVENT = "stream_event"
_MESSAGE_START = "message_start"
_MESSAGE_DELTA = "message_delta"
# The stream events that carry a message's usage; every other one only witnesses the message it names.
_USAGE_EVENTS = (_MESSAGE_START, _MESSAGE_DELTA)
_ENVELOPES = frozenset(("system", protocol.ASSISTANT, "user", _STREAM_EVENT, protocol.RESULT_KEY))
# What a frame naming its message by two different ids names it by: no one message.
_TWO_MESSAGES = object()

RequestKey = tuple[str, str | int]
SettledRows = dict[str, claude_requests.ClaudeUsageRow]
# What reads one frame of an envelope: the line it was printed on, and the frame.
FrameReader = Callable[[int, dict[str, Any]], None]


def _envelope(event: dict[str, Any], gaps: Counter[str]) -> str | None:
    """The Claude envelope an event is, None for one that is no Claude frame.

    A discriminator that is no string could have named any envelope, so it is a gap; one naming another envelope is
    simply no Claude frame.
    """
    kind = event.get(protocol.TYPE)
    if isinstance(kind, str):
        return kind if kind in _ENVELOPES else None
    gaps[coverage.MALFORMED_ENVELOPES] += kind is not None
    return None


def _named_message(
    event: dict[str, Any],
    message: dict[str, Any],
) -> Any:
    """The id one message frame names its message by, as it gave it; `_TWO_MESSAGES` where it names two.

    An `assistant` frame's message and a `message_start`'s carry the message's own id, and a stream event's wrapper
    names it as `api_message_id`; any other stream event is its own message, which carries no id. Where both name one,
    they have to agree.
    """
    wrapper = event.get(_API_MESSAGE_ID)
    nested = message.get(protocol.ID)
    if message is event.get(_EVENT) or not nested:
        return wrapper
    if not wrapper or wrapper == nested:
        return nested
    return _TWO_MESSAGES


def _message_key(
    event: dict[str, Any],
    message: dict[str, Any],
    position: int,
    kind: Any,
    gaps: Counter[str],
) -> RequestKey | None:
    """The request a stream event folds into, None for one it folds into none.

    A stream event naming its message by two different ids folds into neither, an `identity-conflicting` gap, and one
    past a message's start naming no message settles nothing it could be told apart from, an `unindexed-frames` gap
    where it carries usage.
    """
    named = _named_message(event, message)
    if named is _TWO_MESSAGES:
        gaps[coverage.IDENTITY_CONFLICTING] += 1
        return None
    # Keyed as an `assistant` frame is where it names no message: by the API request that produced it.
    named = nonempty_string(named) or nonempty_string(event.get(_REQUEST_ID))
    if named is not None:
        return TURN, named
    if kind == _MESSAGE_START:
        return LINE, position
    gaps[coverage.UNINDEXED_FRAMES] += message.get(protocol.USAGE) is not None
    return None


def _message_names(
    metadata: request_scan.Metadata,
    event: dict[str, Any],
    message: dict[str, Any],
) -> Names:
    """What one message frame names: a stream event names its message on its wrapper, as `api_message_id`.

    Its model is read where the run parsers read a Claude frame's -- its message, a stream event's message, then the
    frame itself -- so a request runs on the model its own frame names wherever that frame names it; a model named
    there that this collection refused is `REFUSED`, never one read further on, nor none.
    """
    return Names(
        message_id=metadata.text(_named_message(event, message)),
        request_id=metadata.text(event.get(_REQUEST_ID)),
        session_id=metadata.text(event.get(SESSION_ID)),
        agent_id=metadata.text(event.get(_FRAME_AGENT_ID)),
        model=metadata.first_text(event, CLAUDE_MODEL_PATHS),
        timestamp=metadata.text(event.get(_TIMESTAMP)),
    )


@dataclass
class RequestIndex:
    """The requests a stream named, each held under the key it was first named by, and the other keys naming it.

    A frame naming a message by both its id and the id of the API request that produced it joins the two keys, so a
    request first named by one is found again by the other and its frames are one request; two requests held apart until
    then are folded into the one printed first, linking the turn numbered under its message id where either was. Its
    settlement key is then its message id, the key the trajectory's turns know it by. A frame joining keys the stream
    already named apart -- a request id another message already gave, or a message another request already produced --
    joins nothing and is an `identity-conflicting` gap, so both requests stay apart, and a request id named for two
    messages names neither from then on. Only ids within `id_chars`, the metadata bound, join keys: a longer one is no
    name a request keeps, so no contradiction could ever be caught on it. A key is kept only for a request held or that
    may still be within `limit`, and a request is found by at most one key besides the one it is held under: `paired`
    holds each one already found so, and a frame that would give it another is an `identity-conflicting` gap whatever
    names its frames kept, so the keys never outnumber the requests held.
    """

    limit: int
    id_chars: int
    held: dict[RequestKey, RequestFold] = field(default_factory=dict)
    aliases: dict[RequestKey, RequestKey] = field(default_factory=dict)
    ambiguous: set[RequestKey] = field(default_factory=set)
    paired: set[RequestKey] = field(default_factory=set)
    gaps: Counter[str] = field(default_factory=Counter)

    def get(self, key: RequestKey, default: RequestFold | None = None) -> RequestFold | None:
        return self.held.get(self.aliases.get(key, key), default)

    def summable(self) -> list[RequestKey]:
        """Each request under the key a settlement sums it by; one known only by its line has none it sums."""
        return [
            (HANDBACK if request.handback else TURN, request.key or "")
            for request in self.held.values()
        ]

    @property
    def room(self) -> bool:
        """Whether one more request may be held within the bound on tracked requests."""
        return len(self.held) < self.limit

    def join(self, key: RequestKey, frame: dict[str, Any]) -> RequestKey | None:
        """The key the request `key` names is held under, joined with the API request `frame` names where one.

        None where `key` is a request id the stream named for more than one message, which names no one request. An id
        past the metadata bound joins nothing, and a key is only ever kept for a request held or that may still be, so
        the keys never outgrow the bound.
        """
        if key in self.ambiguous:
            return None
        request_id = nonempty_string(frame.get(_REQUEST_ID))
        if key[0] != TURN or request_id in {None, key[1]}:
            return self.aliases.get(key, key)
        # Only ids within the metadata bound correlate: one past it is no identity this collection keeps.
        lengths = (len(request_id), len(str(key[1])))
        if max(lengths) > self.id_chars:
            return self.aliases.get(key, key)
        return self._bridged(key, (TURN, request_id))

    def _bridged(self, message_key: RequestKey, request_key: RequestKey) -> RequestKey:
        """The key one request is held under by both keys, unless the stream already named them apart."""
        by_message = self.aliases.get(message_key, message_key)
        by_request = self.aliases.get(request_key, request_key)
        settled = request_key in self.ambiguous or by_message == by_request
        if settled or self._conflicted(message_key, request_key, by_message, by_request):
            return by_message
        if by_request not in self.held:
            if self.room or by_message in self.held:
                self.aliases[request_key] = by_message
                self.paired.add(by_message)
            return by_message
        if by_message not in self.held:
            self.aliases[message_key] = by_request
            self.paired.add(by_request)
            self.held[by_request].key = str(message_key[1])
            return by_request
        return self._merged(message_key, by_message, by_request)

    def _conflicted(
        self,
        message_key: RequestKey,
        request_key: RequestKey,
        by_message: RequestKey,
        by_request: RequestKey,
    ) -> bool:
        """Whether the stream already named the two apart: the request id another message, or the message another id.

        Either request already found by its one other key was named apart from this one, whether or not its frames kept
        the id that key is. The contradiction is an `identity-conflicting` gap, and a request id already naming a
        request names none from then on, so a frame naming it alone settles nothing rather than whichever message it
        named first.
        """
        request_fold = self.held.get(by_request)
        message_fold = self.held.get(by_message)
        apart = not self.paired.isdisjoint((by_message, by_request))
        named = request_fold.names.message_id if request_fold else None
        apart = apart or named not in {None, message_key[1]}
        named = message_fold.names.request_id if message_fold else None
        if not apart and named in {None, request_key[1]}:
            return False
        self.gaps[coverage.IDENTITY_CONFLICTING] += 1
        if request_fold is not None:
            self.ambiguous.add(request_key)
            self.aliases.pop(request_key, None)
        return True

    def _merged(self, message_key: RequestKey, by_message: RequestKey, by_request: RequestKey) -> RequestKey:
        """Fold the later-printed of two held requests into the earlier, now held under every key either was."""
        kept, gone = by_message, by_request
        if self.held[gone].position < self.held[kept].position:
            kept, gone = gone, kept
        later = self.held.pop(gone)
        if not self.held[kept].joined(later, str(message_key[1])):
            self.gaps[coverage.SUBAGENT_ATTRIBUTION_CONFLICTING] += 1
        # Neither was found by another key yet, or the two were named apart, so `gone` is the one key naming it.
        self.aliases[gone] = kept
        self.paired.add(kept)
        return kept


@dataclass
class TurnFeed:
    """The trajectory's own turn builder, fed every event while its correlation stays within the bound.

    `whole` says whether the builder saw every event the scan decoded, so its settlement and its count of turns are the
    trajectory's.
    """

    limit: int
    builder: trajectory_claude_turns.ClaudeTurnUsageBuilder = field(
        default_factory=trajectory_claude_turns.ClaudeTurnUsageBuilder,
    )
    whole: bool = True

    @property
    def correlated(self) -> int:
        """The most identities any of the builder's correlation maps holds."""
        settlement = self.builder.settlement
        held = (self.builder.turn_index, settlement.final_outputs, settlement.subagent_messages, settlement.handbacks)
        return max(map(len, held))

    def sums_all(self, requests: Iterable[RequestKey], settled: SettledRows) -> bool:
        """Whether the settlement sums every one of `requests`: each message among its rows, each hand-back its own.

        A message no `assistant` frame reported usage for, a start naming no message, and a hand-back naming no agent
        are usage the settlement never sums, so a remainder it attributes to one open message could be theirs.
        """
        summed = {(TURN, key) for key in settled}
        summed.update((HANDBACK, key) for key in self.builder.settlement.handbacks)
        return summed.issuperset(requests)

    def summed(self, model: str, settled: SettledRows) -> list[tuple[RequestKey, bool]]:
        """The requests a `modelUsage` settlement of `model` sums, each with whether it sums the request's output.

        It sums the prompt of each of the model's messages and hand-backs, and the output of each one it does not
        settle -- a message a closing report settled, and every hand-back; the open message's own output cancels out.
        """
        messages = [
            ((TURN, key), settled_row.settlement == claude_requests.SETTLED_BY_DELTA)
            for key, settled_row in settled.items()
            if settled_row.model == model
        ]
        handbacks = [
            ((HANDBACK, key), True)
            for key, handback_row in self.builder.settlement.handbacks.items()
            if handback_row.model == model
        ]
        return [*messages, *handbacks]

    def add_event(self, ordinal: int, event: dict[str, Any]) -> bool:
        """Feed one event; False for the one that takes the builder past the bound, which drops it."""
        if not self.whole:
            return True
        self.builder.add_event(ordinal, event)
        if self.correlated <= self.limit:
            return True
        self.builder = trajectory_claude_turns.ClaudeTurnUsageBuilder()
        self.whole = False
        return False


@dataclass
class StreamFold:
    """One bounded pass over a process's stream: its requests, its process reports, and the trajectory's own turns."""

    scan: request_scan.EventScan
    process: Process
    turns: TurnFeed
    requests: RequestIndex
    envelopes: int = 0
    gaps: Counter[str] = field(default_factory=Counter)

    @classmethod
    def read(cls, stdout: str) -> StreamFold:
        """Scan `stdout` and fold every event it decoded, in stream order."""
        limits = request_scan.current_limits()
        metadata = request_scan.Metadata(limits.metadata_chars)
        fold = cls(
            request_scan.scan_events(stdout, limits),
            Process(limits, metadata, checkpoints=deque(maxlen=limits.checkpoints)),
            TurnFeed(limits.tracked_steps),
            RequestIndex(limits.tracked_steps, limits.metadata_chars),
        )
        for ordinal, positioned in enumerate(fold.scan.events):
            fold.feed(ordinal, *positioned)
        return fold

    def feed(self, ordinal: int, position: int, event: dict[str, Any]) -> None:
        self.gaps[coverage.CORRELATION_LIMIT] += not self.turns.add_event(ordinal, event)
        kind = _envelope(event, self.gaps)
        if kind is None:
            return
        self.envelopes += 1
        readers: dict[str, FrameReader] = {
            "system": self.process.read_system,
            protocol.RESULT_KEY: self.process.read_result,
            "user": partial(self._handback, ordinal),
            protocol.ASSISTANT: partial(self._assistant, ordinal),
            _STREAM_EVENT: self._stream_event,
        }
        readers[kind](position, event)

    def request(
        self,
        key: RequestKey,
        position: int,
        frame: dict[str, Any],
        *,
        call: Any = None,
    ) -> RequestFold | None:
        """The fold of the request `key` names, opened on its first frame within the bound on tracked requests.

        Every frame of a request places it, whatever kind of frame it is: a message frame by the call it names as its
        parent and by the subagent's agent it names, which makes the request the subagent's even naming no call, and a
        hand-back -- always a subagent's -- by the `call` it answers. So a later frame naming the call or the agent an
        earlier one left out completes its branch, while one naming another call than an earlier one is a
        `subagent-attribution-conflicting` gap.
        """
        handback = key[0] == HANDBACK
        held = self.requests.join(key, frame)
        if held is None:
            # A frame naming a request only by an id the stream gave more than one message settles none of them.
            self.gaps[coverage.UNINDEXED_FRAMES] += 1
            return None
        request = self.requests.held.get(held)
        if request is None:
            if not self.requests.room:
                self.gaps[coverage.CORRELATION_LIMIT] += 1
                return None
            request = RequestFold(
                position,
                None if held[0] == LINE else str(held[1]),
                handback=handback,
            )
            self.requests.held[held] = request
        raw_branch = call if handback else frame.get(request_models.PARENT_TOOL_USE_ID)
        subagent = handback or raw_branch is not None or bool(frame.get(_FRAME_AGENT_ID))
        if not request.placed(self.process.metadata.text(raw_branch), subagent=subagent):
            self.gaps[coverage.SUBAGENT_ATTRIBUTION_CONFLICTING] += 1
        if subagent:
            self.process.launch(raw_branch)
        return request

    def absorb(
        self,
        request: RequestFold,
        event: dict[str, Any],
        message: dict[str, Any],
        *,
        closing: bool,
    ) -> None:
        """Fold one message frame's names and usage into its request."""
        request.names = request.names.merged(_message_names(self.process.metadata, event, message))
        usage = message.get(protocol.USAGE)
        self.gaps[coverage.MALFORMED_USAGE] += malformed_usage(usage)
        if isinstance(usage, dict):
            request.absorb(usage_readings(usage), closing=closing)

    def _assistant(self, ordinal: int, position: int, event: dict[str, Any]) -> None:
        message = event.get(protocol.MESSAGE)
        if not isinstance(message, dict):
            self.gaps[coverage.MALFORMED_ENVELOPES] += 1
            return
        named = _named_message(event, message)
        if named is _TWO_MESSAGES:
            # A frame naming its message by two different ids folds into neither of them.
            self.gaps[coverage.IDENTITY_CONFLICTING] += 1
            return
        turn_key = trajectory_claude_stream.turn_key(ordinal, event)
        # The frame folds into the message it names, on itself or on its wrapper, as its stream events do; the
        # trajectory numbers a frame naming it on the wrapper alone by its request id or its line instead.
        key = nonempty_string(named) or turn_key
        request = self.request((TURN, key), position, event)
        if request is None:
            return
        # A request is linked to the turn its canonical key -- its message id, once one is known -- was numbered under,
        # the turn holding its settled output; until one of its frames is keyed so, each relinks it under its own key.
        if self.turns.whole and request.turn_key != request.key:
            request.turn_key = turn_key
            request.turn = self.turns.builder.turn_index.get(turn_key)
        self.absorb(request, event, message, closing=False)

    def _stream_event(self, position: int, event: dict[str, Any]) -> None:
        """Fold a stream event into the message its wrapper names: its usage, or only that the message was printed."""
        inner = event.get(_EVENT)
        if not isinstance(inner, dict):
            self.gaps[coverage.MALFORMED_ENVELOPES] += 1
            return
        kind = inner.get(protocol.TYPE)
        message = inner.get(protocol.MESSAGE) if kind == _MESSAGE_START else inner
        if not isinstance(message, dict):
            self.gaps[coverage.MALFORMED_ENVELOPES] += 1
            return
        key = _message_key(event, message, position, kind, self.gaps)
        if key is None:
            return
        request = self.request(key, position, event)
        if request is None:
            return
        if kind in _USAGE_EVENTS:
            self.absorb(request, event, message, closing=kind == _MESSAGE_DELTA)
        else:
            # A content event carries no usage, but names the message's session and timestamp as any frame of it does.
            request.names = request.names.merged(_message_names(self.process.metadata, event, message))

    def _handback(self, ordinal: int, position: int, event: dict[str, Any]) -> None:
        """Fold a subagent hand-back under the call it answers, keyed as the accounting's settlement keys it.

        One naming no `agentId` is a subagent's only where the call it answers is one the stream named a subagent for.
        """
        # A subagent's own `user` frame names the call that launched it, so a hand-back answering that call is its.
        self.process.launch(event.get(request_models.PARENT_TOOL_USE_ID))
        handback = event.get("tool_use_result")
        if not isinstance(handback, dict):
            return
        call = claude_rows.claude_tool_result_id(event)
        if not handback.get(_AGENT_ID) and call not in self.process.launched:
            return
        usage = handback.get(protocol.USAGE)
        self.gaps[coverage.MALFORMED_USAGE] += malformed_usage(usage)
        if not isinstance(usage, dict):
            return
        key = (HANDBACK, call or str(ordinal))
        request = self.request(key, position, event, call=call)
        if request is None:
            return
        request.names = request.names.merged(handback_names(self.process.metadata, event, handback))
        request.absorb(usage_readings(usage), closing=True)
