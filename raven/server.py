"""HTTP/WebSocket API server wrapping Assistant, for the desktop UI
(raven_ui/, Electron+React) -- ... (docstring unchanged) ...
"""
import asyncio
import base64
import json
import logging
import threading
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from raven import voice
from raven.assistant import Assistant
from raven.config import get_api_key, load_settings, save_settings
from raven.llm_provider import KNOWN_PROVIDERS, NvidiaProvider, OpenRouterProvider, list_nvidia_models
from raven.store import Store

log = logging.getLogger("raven.server")

app = FastAPI()

STATS_INTERVAL_S = 2.0   # Defines a 2s interval for stats refresh


def _build_assistant(confirm_run_fn, on_tool_call_fn, store) -> Assistant:
    """... (unchanged) ... Which LLMProvider subclass gets built (OpenRouter,
    NVIDIA, ...) is settings.json's model.provider -- branched directly here
    (not llm_provider.build_provider's shared PROVIDERS dict) so
    `patch.object(server, "OpenRouterProvider")` keeps working in tests,
    same tradeoff cli.py's own build_assistant makes for the same reason."""
    settings = load_settings()
    model_cfg = settings["model"]
    provider_name = model_cfg.get("provider", "openrouter")
    api_key = get_api_key(provider_name)
    provider_cls = NvidiaProvider if provider_name == "nvidia" else OpenRouterProvider
    provider = provider_cls(api_key=api_key, model=model_cfg["name"], fallbacks=model_cfg.get("fallbacks", []))
    return Assistant(
        provider, confirm_run=confirm_run_fn, on_tool_call=on_tool_call_fn,
        store=store, settings=settings,
    )


MAX_HISTORY_ITEMS = 200


def history_items(history: list[dict]) -> list[dict]:
    """... (unchanged) ..."""
    items = [
        {"role": m["role"], "text": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str) and m["content"].strip()
    ]
    return items[-MAX_HISTORY_ITEMS:]


class Session:
    """... (docstring unchanged) ..."""

    def __init__(self, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
        self.websocket = websocket
        self.loop = loop
        self._pending_confirms: dict[str, tuple[threading.Event, dict]] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self.store = Store()
        self.assistant = _build_assistant(self._confirm_run, self._on_tool_call, self.store)
        self._stats_task: asyncio.Task | None = None   # NEW

    # -- stats push ----------------------------------------------------------

    def start_stats_loop(self) -> None:                # NEW
        """Kick off the periodic statusline push. Called once from the
        endpoint right after the socket is accepted; stopped in the same
        finally block that resolves pending confirms."""
        self._stats_task = asyncio.create_task(self._stats_loop())

    def stop_stats_loop(self) -> None:                 # NEW
        if self._stats_task:
            self._stats_task.cancel()
            self._stats_task = None

    async def _stats_loop(self) -> None:               # NEW
        """Push a statusline snapshot every STATS_INTERVAL_S while the socket
        is open. Timer-driven rather than reply-driven because cpu/mem
        change on their own between turns. Runs on the event loop (unlike
        _run_ask): a fast psutil read plus an async send, nothing to offload."""
        while True:
            try:
                await self._send_stats()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("stats push failed")     # NEW -- visible in terminal
            await asyncio.sleep(STATS_INTERVAL_S)

    async def _send_stats(self) -> None:               # FIXED
        from raven import statusline
        # .get() chain so a config with no statusline block falls back to
        # every segment statusline defines, instead of raising KeyError and
        # killing the tick silently.
        names = (self.assistant.settings.get("statusline", {}).get("segments")
                 or list(statusline.SEGMENTS))
        segments = []
        for name in names:
            fn = statusline.SEGMENTS.get(name)
            if fn is None:
                log.warning("unknown statusline segment: %r", name)
                continue
            try:
                segments.append({"name": name, "text": fn(self.assistant.provider, self.assistant)})
            except Exception:                          # noqa: BLE001
                log.exception("statusline segment %r failed", name)
        await self.websocket.send_json({"type": "stats", "segments": segments})

    # -- existing methods (unchanged) ---------------------------------------

    def _send(self, message: dict) -> None:
        asyncio.run_coroutine_threadsafe(self.websocket.send_json(message), self.loop)

    def _on_tool_call(self, name: str, args: dict) -> None:
        self._send({"type": "tool_call", "name": name, "args": args})

    def _confirm_run(self, prompt: str) -> bool:
        # ... (unchanged) ...
        confirm_id = str(uuid.uuid4())
        event = threading.Event()
        answer_box: dict = {"approved": False}
        self._pending_confirms[confirm_id] = (event, answer_box)
        self._send({"type": "confirm_request", "id": confirm_id, "prompt": prompt})
        event.wait()
        self._pending_confirms.pop(confirm_id, None)
        return answer_box["approved"]

    def resolve_all_pending(self, approved: bool) -> None:
        # ... (unchanged) ...
        for event, answer_box in list(self._pending_confirms.values()):
            answer_box["approved"] = approved
            event.set()

    async def handle_message(self, data: dict) -> None:
        # ... (unchanged) ...
        msg_type = data.get("type")
        if msg_type == "confirm_response":
            confirm_id = data.get("id")
            pending = self._pending_confirms.get(confirm_id)
            if pending:
                event, answer_box = pending
                answer_box["approved"] = bool(data.get("approved"))
                event.set()
            return
        if msg_type == "get_history":
            await self._send_history()
            return
        if msg_type == "list_sessions":
            await self._send_sessions()
            return
        if msg_type in ("new_session", "open_session", "delete_session"):
            if self._background_tasks:
                await self.websocket.send_json(
                    {"type": "error", "message": "Wait for the current request to finish before switching chats."}
                )
                return
            if msg_type == "new_session":
                self._new_session()
            elif msg_type == "open_session":
                if not self._open_session(data.get("id")):
                    await self.websocket.send_json({"type": "error", "message": "That chat no longer exists."})
                    return
            else:
                self._delete_session(data.get("id"))
            await self._send_history()
            await self._send_sessions()
            return
        if msg_type == "ask":
            task = asyncio.create_task(self._run_ask(data.get("text", "")))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return
        if msg_type == "transcribe":
            # Independent of ask()/session switching -- it never touches self.assistant
            # or self.store, so it's fine to run alongside either without the
            # "wait for the current request" guard those use.
            task = asyncio.create_task(self._run_transcribe(data.get("audio", ""), data.get("id")))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return
        if msg_type == "get_model_config":
            await self._send_model_config()
            return
        if msg_type == "list_models":
            task = asyncio.create_task(self._run_list_models(data.get("provider", "")))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return
        if msg_type == "set_model":
            await self._run_set_model(data.get("provider", ""), data.get("name", ""))
            return
        await self.websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    # -- chat sessions (unchanged) ------------------------------------------

    def _switch_to(self, session_id: int) -> None:
        old = self.store
        self.store = Store(session_id=session_id)
        self.assistant = _build_assistant(self._confirm_run, self._on_tool_call, self.store)
        try:
            old.close()
        except Exception:  # noqa: BLE001
            pass

    def _new_session(self) -> None:
        if self.store.message_count() == 0:
            return
        self._switch_to(self.store.create_session())

    def _open_session(self, session_id) -> bool:
        if not any(x["id"] == session_id for x in self.store.list_sessions()):
            return False
        if session_id != self.store.session_id:
            self._switch_to(session_id)
        return True

    def _delete_session(self, session_id) -> None:
        if not any(x["id"] == session_id for x in self.store.list_sessions()):
            return
        was_current = session_id == self.store.session_id
        self.store.delete_session(session_id)
        if was_current:
            remaining = self.store.latest_session_id()
            self._switch_to(remaining if remaining is not None else self.store.create_session())

    async def _send_history(self) -> None:
        await self.websocket.send_json({
            "type": "history", "session": self.store.session_id,
            "items": history_items(self.assistant.history),
        })
        await self._send_stats()                       # NEW -- populate on connect / switch

    async def _send_sessions(self) -> None:
        await self.websocket.send_json({
            "type": "sessions", "current": self.store.session_id, "items": self.store.list_sessions(),
        })

    async def _run_ask(self, text: str) -> None:
        try:
            reply = await asyncio.to_thread(self.assistant.ask, text)
            await self.websocket.send_json({"type": "reply", "text": reply})
            await self._send_sessions()
            await self._send_stats()                   # NEW -- refresh token/context at turn end
        except Exception as e:
            await self.websocket.send_json({"type": "error", "message": str(e)})

    # -- voice input -----------------------------------------------------------
    # Push-to-talk from the desktop UI: the renderer captures raw audio (Web
    # Audio API), never a compressed format, so the exact same offline
    # faster-whisper pipeline the CLI's Ctrl+V already uses (raven/voice.py)
    # can transcribe it directly -- no ffmpeg, no cloud call, one code path for
    # both surfaces. `id` round-trips the client's request so out-of-order
    # replies (unlikely, but the client doesn't serialize push-to-talk
    # presses) still resolve the right pending promise.

    async def _run_transcribe(self, audio_b64: str, request_id) -> None:
        if not voice.is_available():
            await self.websocket.send_json({
                "type": "transcript_error", "id": request_id,
                "message": ('Voice dependencies aren\'t installed -- pip install ".[voice]" '
                            "(and on Linux: sudo apt install libportaudio2)."),
            })
            return
        if not voice.model_ready():
            await self.websocket.send_json({
                "type": "transcript_error", "id": request_id,
                "message": "Voice model not downloaded -- run: python -m raven.voice",
            })
            return
        try:
            import numpy as np
            # 16-bit PCM little-endian mono at voice.SAMPLE_RATE, exactly what the
            # renderer's AudioContext({sampleRate: voice.SAMPLE_RATE}) produces --
            # see raven_ui/src/stages/VoiceStage.tsx. Normalized to float32 in
            # [-1, 1], the same shape Recorder.stop() hands transcribe() on the CLI.
            samples = np.frombuffer(base64.b64decode(audio_b64), dtype="<i2").astype("float32") / 32768.0
            text = await asyncio.to_thread(voice.transcribe, samples)
        except voice.ModelNotDownloadedError as e:
            await self.websocket.send_json({"type": "transcript_error", "id": request_id, "message": str(e)})
            return
        except Exception as e:  # noqa: BLE001 -- always report to the UI, never drop the request silently
            await self.websocket.send_json(
                {"type": "transcript_error", "id": request_id, "message": f"Couldn't transcribe: {e}"}
            )
            return
        await self.websocket.send_json({"type": "transcript", "id": request_id, "text": text})

    # -- model provider/name (desktop Settings panel) ---------------------------
    # Lets the user pick a different provider (OpenRouter, NVIDIA) and model
    # from the UI instead of hand-editing settings.json. `set_model` persists
    # the choice (so it survives a restart, same as any other setting) AND
    # takes effect immediately in this running session by rebuilding
    # self.assistant, exactly like switching chats already does in _switch_to.

    async def _send_model_config(self) -> None:
        model_cfg = load_settings()["model"]
        await self.websocket.send_json({
            "type": "model_config", "provider": model_cfg.get("provider", "openrouter"), "name": model_cfg["name"],
        })

    async def _run_list_models(self, provider_name: str) -> None:
        if provider_name != "nvidia":
            # Only NVIDIA exposes a listable catalog via this key today; OpenRouter's
            # model is still chosen by editing settings.json directly (see README).
            await self.websocket.send_json({
                "type": "models_error", "provider": provider_name,
                "message": f"Listing models isn't supported for provider {provider_name!r}.",
            })
            return
        try:
            api_key = get_api_key("nvidia")
            models = await asyncio.to_thread(list_nvidia_models, api_key)
        except Exception as e:  # noqa: BLE001 -- always report to the UI, never drop the request silently
            await self.websocket.send_json({"type": "models_error", "provider": provider_name, "message": str(e)})
            return
        await self.websocket.send_json({"type": "models", "provider": provider_name, "items": models})

    async def _run_set_model(self, provider_name: str, name: str) -> None:
        if provider_name not in KNOWN_PROVIDERS:
            await self.websocket.send_json({
                "type": "error",
                "message": f"Unknown model provider: {provider_name!r}. Known providers: {', '.join(KNOWN_PROVIDERS)}.",
            })
            return
        if not name.strip():
            await self.websocket.send_json({"type": "error", "message": "A model name is required."})
            return
        settings = load_settings()
        was_provider = settings["model"].get("provider", "openrouter")
        # Fallbacks are model ids for the OLD provider -- carrying them across a
        # provider change would silently feed e.g. an OpenRouter id to NVIDIA's
        # API. This picker has no fallback UI of its own, so the safe default
        # is to clear them on an actual provider switch and leave them alone
        # when just picking a different model from the same provider.
        new_fallbacks = settings["model"].get("fallbacks", []) if provider_name == was_provider else []
        new_model_cfg = {**settings["model"], "provider": provider_name, "name": name, "fallbacks": new_fallbacks}
        try:
            api_key = get_api_key(provider_name)
            provider_cls = NvidiaProvider if provider_name == "nvidia" else OpenRouterProvider
            new_provider = provider_cls(api_key=api_key, model=name, fallbacks=new_fallbacks)
        except Exception as e:  # noqa: BLE001 -- validated BEFORE persisting/swapping, so a bad
            # choice (missing key, ...) leaves the current, working model untouched.
            await self.websocket.send_json({"type": "error", "message": str(e)})
            return
        settings["model"] = new_model_cfg
        save_settings(settings)
        self.assistant.provider = new_provider
        await self._send_model_config()
        await self._send_stats()  # refresh the "Current model" segment immediately


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    session = Session(websocket, asyncio.get_running_loop())
    session.start_stats_loop()                         # NEW
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue
            await session.handle_message(data)
    except WebSocketDisconnect:
        pass
    finally:
        session.stop_stats_loop()                      # NEW
        session.resolve_all_pending(approved=False)


def main() -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host="127.0.0.1", port=8756)


if __name__ == "__main__":
    main()