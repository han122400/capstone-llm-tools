"""Decode Foundation-Sec's MiniMax M2 thinking protocol from Ollama deltas.

The model's official card specifies minimax_m2: it can omit the opening
<think> tag and end its reasoning with </think>. Some Ollama versions return
that trace in message.content instead of a separate message.thinking field.
"""


class ThinkingSplitter:
    opening = "<think>"
    closing = "</think>"

    def __init__(self):
        self.mode = "initial"
        self.pending = ""

    def native_thinking(self):
        if self.mode != "initial" or self.pending.strip():
            raise ValueError("Mixed native and raw reasoning protocols")
        self.mode = "native"
        pending, self.pending = self.pending, ""
        return [("content", pending)] if pending else []

    def push(self, text: str):
        if not text:
            return []
        if self.mode in {"native", "content"}:
            return [("content", text)]
        self.pending += text
        if self.mode == "initial":
            visible = self.pending.lstrip()
            if not visible or (self.opening.startswith(visible) and visible != self.opening):
                return []
            # A model may answer directly without a thinking trace.
            if visible.startswith("{"):
                self.mode = "content"
                pending, self.pending = self.pending, ""
                return [("content", pending)]
            if visible.startswith(self.opening):
                tag_start = len(self.pending) - len(visible)
                self.pending = self.pending[:tag_start] + visible[len(self.opening):]
            self.mode = "thinking"

        end = self.pending.find(self.closing)
        if end >= 0:
            thinking = self.pending[:end]
            content = self.pending[end + len(self.closing):]
            self.pending = ""
            self.mode = "content"
            return [(field, value) for field, value in [("thinking", thinking), ("content", content)] if value]

        # Retain only a possible partial delimiter across network/token boundaries.
        keep = max((length for length in range(1, len(self.closing)) if self.pending.endswith(self.closing[:length])), default=0)
        emitted = self.pending[:-keep] if keep else self.pending
        self.pending = self.pending[-keep:] if keep else ""
        return [("thinking", emitted)] if emitted else []

    def finish(self):
        if self.mode == "thinking" or self.pending.strip():
            raise ValueError("Reasoning trace ended without a final answer delimiter")

