"""
Control-token-safe streaming filter.

When we stream the LLM's generation to the client token-by-token, we must never
let a control token (e.g. <TASKS_CONFIRMED>...</TASKS_CONFIRMED>) leak into the
visible text. The prompts instruct the model to place these blocks at the END
of its reply, so the rule is simple and robust: emit text until the first
character of a known control token, then suppress everything after it.

The tricky part is chunk boundaries — a delta may end mid-tag ("...<TASK"), so
we buffer any trailing run that could still become a control token until we have
enough characters to decide.
"""

KNOWN_TAGS = [
    "TASKS_CONFIRMED",
    "EVENTS_CONFIRMED",
    "PROFILE_UPDATE",
    "MARK_DONE",
    "MOVE_TASK",
    "ONBOARDING_COMPLETE",
]

_MARKERS = ["<" + tag for tag in KNOWN_TAGS]


class StreamFilter:
    """Feed raw deltas; receive only text that is safe to show the user."""

    def __init__(self) -> None:
        self._buf = ""
        self._suppressed = False

    def feed(self, delta: str) -> str:
        if self._suppressed or not delta:
            return ""

        self._buf += delta
        out = ""

        while self._buf:
            idx = self._buf.find("<")
            if idx == -1:
                out += self._buf
                self._buf = ""
                break

            out += self._buf[:idx]
            rest = self._buf[idx:]
            kind = self._classify(rest)

            if kind == "definite":
                # A control token starts here — drop it and everything after.
                self._suppressed = True
                self._buf = ""
                return out
            if kind == "partial":
                # Could still become a control token; wait for more input.
                self._buf = rest
                break
            # A literal '<' that isn't a control token (e.g. "<3"): emit and move on.
            out += "<"
            self._buf = rest[1:]

        return out

    def flush(self) -> str:
        """Emit any safe text still buffered at end of stream."""
        if self._suppressed:
            return ""
        out = self._buf
        self._buf = ""
        return out

    @staticmethod
    def _classify(rest: str) -> str:
        for marker in _MARKERS:
            if rest.startswith(marker):
                return "definite"
        for marker in _MARKERS:
            if marker.startswith(rest):
                return "partial"
        return "none"
