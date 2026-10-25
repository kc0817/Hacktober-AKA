"""Claude Sonnet 5.5 (effort: medium) answering questions about recent screenshots."""
import base64

import anthropic

from .config import CONFIG
from .storage import StoredScreenshot

SYSTEM_PROMPT = """You are a patient tutor sitting next to someone who is learning the desktop software on their \
screen. It could be any application: CAD or PCB tools, IDEs, spreadsheets, design or video editors, and so on.

With each question you get the user's most recent screenshots of the window they were working in, oldest first, \
each labeled with its capture time and window title. Work out which application (and, if visible, which version) \
they're using from the title and the interface, and use the screenshots to understand what they're doing right now.

- Ground your answer in what is visible: name the exact menus, panels, toolbar buttons and shortcuts they should use.
- Give numbered steps when there's a procedure.
- If the screenshots don't show enough to answer, say what you can't see and what they should open or show you.
- If you spot a likely problem on screen (an error or warning message, a wrong setting or mode), point it out.
- If you're unsure of an app-specific detail, say so rather than guess.
- Keep answers short enough to read in a small side window."""


class Assistant:
    def __init__(self):
        self._client = None  # created on first question so a missing key shows up as a message, not a crash
        # Append-only: earlier turns are sent back unchanged so thinking blocks and the cache stay valid.
        self._history: list[dict] = []
        self.last_response = None  # full API response of the latest ask(), for usage/cost reporting

    def reset(self) -> None:
        self._history = []

    def ask(self, question: str, screenshots: list[StoredScreenshot]) -> str:
        content: list[dict] = []
        for shot in screenshots:
            content.append({
                "type": "text",
                "text": f"Screenshot at {shot.captured_at:%H:%M:%S} — window: {shot.window_title or 'unknown'}",
            })
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(shot.png_bytes).decode("utf-8"),
                },
            })
        if not screenshots:
            content.append({"type": "text", "text": "(No screenshots captured yet.)"})
        content.append({"type": "text", "text": question})

        if self._client is None:
            self._client = anthropic.Anthropic()

        user_turn = {"role": "user", "content": content}
        response = self._client.beta.messages.create(
            model=CONFIG.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            output_config={"effort": CONFIG.effort},
            # If a safety classifier declines, re-run on Anthropic's recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            cache_control={"type": "ephemeral"},
            messages=self._history + [user_turn],
        )

        self.last_response = response
        if response.stop_reason == "refusal":
            return "Sorry, I can't help with that one."

        self._history += [user_turn, {"role": "assistant", "content": response.content}]
        return "".join(b.text for b in response.content if b.type == "text")
