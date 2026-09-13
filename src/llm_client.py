"""
llm_client.py
-------------
Thin wrapper around the Ollama /api/chat endpoint.

Ollama runs locally at http://localhost:11434 by default.
Set OLLAMA_BASE_URL or OLLAMA_MODEL as environment variables to override.

Available models (from `ollama list`):
  - gemma4:latest   (default, 8B — good balance of speed and quality)
  - qwen3:30b       (slower but more thorough)

Thinking mode:
  Both gemma4 and qwen3 support extended thinking. When enabled, the model
  produces an internal reasoning trace streamed live to the terminal before
  its final answer.

  Enable with:
      OLLAMA_THINKING=true python3 run_demo.py

Usage:
    from llm_client import chat_json

    result = chat_json(
        system="You are ...",
        user="Here is the case: ...",
        label="Stage 1",
    )
    # result is a parsed dict — raises ValueError if the model didn't return valid JSON
"""

import json
import os
import urllib.request
import urllib.error

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "gemma4:latest")
OLLAMA_TIMEOUT  = int(os.environ.get("OLLAMA_TIMEOUT", "120"))
OLLAMA_THINKING = os.environ.get("OLLAMA_THINKING", "false").lower() == "true"

_console = Console()


def chat_json(system: str, user: str, model=None, label: str = "") -> dict:
    """
    Send a chat request to Ollama and return the response as a parsed dict.

    If OLLAMA_THINKING=true:
      - Streams the response chunk by chunk.
      - Prints the thinking trace to the terminal in real time as it arrives.
      - Collects the final JSON content and parses it before returning.

    If OLLAMA_THINKING=false:
      - Non-streaming request (faster, no live output).

    Raises:
        ConnectionError  — Ollama is not running or unreachable
        ValueError       — model responded but output is not valid JSON
        RuntimeError     — any other non-200 response from Ollama
    """
    if OLLAMA_THINKING:
        return _chat_streaming(system, user, model, label)
    else:
        return _chat_blocking(system, user, model)


# ---------------------------------------------------------------------------
# Blocking (non-streaming) — used when thinking is off
# ---------------------------------------------------------------------------

def _chat_blocking(system: str, user: str, model=None) -> dict:
    payload = {
        "model": model or OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    }

    raw = _post(payload)

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned non-JSON envelope: {raw[:200]}") from exc

    if "error" in envelope:
        raise RuntimeError(f"Ollama error: {envelope['error']}")

    content = envelope.get("message", {}).get("content", "")
    return _parse_content(content)


# ---------------------------------------------------------------------------
# Streaming — used when thinking is on, prints thinking trace live
# ---------------------------------------------------------------------------

def _chat_streaming(system: str, user: str, model=None, label: str = "") -> dict:
    payload = {
        "model": model or OLLAMA_MODEL,
        "stream": True,
        "think": True,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    }

    url  = f"{OLLAMA_BASE_URL}/api/chat"
    body = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    thinking_buf  = []
    content_buf   = []
    thinking_done = False

    title = f"[bold cyan]{label} thinking[/bold cyan]" if label else "[bold cyan]LLM thinking[/bold cyan]"

    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            with Live(
                _thinking_panel("", title),
                console=_console,
                refresh_per_second=15,
                vertical_overflow="visible",
            ) as live:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue

                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if "error" in chunk:
                        raise RuntimeError(f"Ollama error: {chunk['error']}")

                    message        = chunk.get("message", {})
                    thinking_piece = message.get("thinking", "")
                    content_piece  = message.get("content", "")

                    if thinking_piece:
                        thinking_buf.append(thinking_piece)
                        # Re-render the panel with the latest accumulated text
                        live.update(_thinking_panel("".join(thinking_buf), title))

                    # Thinking is done once content starts arriving
                    if content_piece and not thinking_done:
                        thinking_done = True
                        # Final render of the complete thinking block
                        live.update(_thinking_panel("".join(thinking_buf), title))

                    if content_piece:
                        content_buf.append(content_piece)

                    if chunk.get("done"):
                        break

    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Cannot reach Ollama at {OLLAMA_BASE_URL}. "
            f"Is it running? (ollama serve)  Detail: {exc}"
        ) from exc

    _console.print()
    content = "".join(content_buf)
    return _parse_content(content)


def _thinking_panel(text: str, title: str):
    """Build a rich Panel containing rendered markdown for the thinking text."""
    from rich.panel import Panel
    content = Markdown(text) if text.strip() else Markdown("*thinking...*")
    return Panel(content, title=title, border_style="cyan", padding=(1, 2))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _post(payload: dict) -> str:
    url  = f"{OLLAMA_BASE_URL}/api/chat"
    body = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Cannot reach Ollama at {OLLAMA_BASE_URL}. "
            f"Is it running? (ollama serve)  Detail: {exc}"
        ) from exc


def _parse_content(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Model did not return valid JSON in message content.\n"
            f"Raw content: {content[:400]}"
        ) from exc
