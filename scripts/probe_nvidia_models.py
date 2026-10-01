r"""Which NVIDIA models an API key can ACTUALLY call.

`list_nvidia_models()` (and the desktop Settings panel's dropdown it feeds)
returns NVIDIA's catalog -- what exists, not what a given account is entitled
to invoke. Most listed ids answer a real chat request with
`404 Function '<uuid>': Not found for account '<id>'`; see DEV_LOG Step 3.66,
which established that this is gated per-model on build.nvidia.com and is not
something this project's code can detect ahead of time.

So the only reliable way to pick a model is to try one. This script does that:
one real chat request per candidate, keeping the ones that answer.

It also reports, per surviving model:
  - whether it supports TOOL CALLING, which R.A.V.E.N needs on nearly every
    turn -- a model that chats fine but ignores `tools` is useless here, and a
    plain "ping" test would not have caught it
  - how long a warm call takes, since several catalog models answer but are
    far too slow to sit behind an interactive prompt

Usage (from the repo root, with NVIDIA_API_KEY set in the environment or .env):

    python scripts/probe_nvidia_models.py                # nemotron models only
    python scripts/probe_nvidia_models.py --all          # the whole catalog (slow)
    python scripts/probe_nvidia_models.py --filter vision

Prints a settings.json snippet for the fastest tool-capable model it found.
"""
import argparse
import json
import sys
import time

from raven.config import get_api_key
from raven.llm_provider import NvidiaProvider, list_nvidia_models

# A deliberately trivial tool. The point is only whether the model emits a
# tool_call at all, not whether it picks a sensible one.
PROBE_TOOL = [{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a text file",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}]


def _first_line(error: Exception, width: int = 100) -> str:
    return str(error).splitlines()[0][:width]


def probe(api_key: str, model: str) -> dict:
    """One model: can it answer, does it call tools, how fast is it warm?

    Returns a dict rather than raising -- a model that 404s is an ordinary,
    expected outcome here, not an error worth stopping the run for.
    """
    provider = NvidiaProvider(api_key, model=model, fallbacks=[], system_prompt="You are a helpful assistant.")
    try:
        provider.reply([{"role": "user", "content": "Reply with only: OK"}])
    except Exception as e:  # noqa: BLE001 -- every failure kind is just "can't use this one"
        return {"model": model, "ok": False, "why": _first_line(e)}

    # Second call: the first paid the TLS handshake (see the Session reuse in
    # NvidiaProvider), so timing that one would overstate every model equally.
    started = time.perf_counter()
    try:
        message = provider.reply([{"role": "user", "content": "Read the file notes.txt"}], tools=PROBE_TOOL)
    except Exception as e:  # noqa: BLE001
        return {"model": model, "ok": True, "tools": False, "why": _first_line(e), "seconds": None}
    return {
        "model": model,
        "ok": True,
        "tools": bool(message.get("tool_calls")),
        "seconds": time.perf_counter() - started,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="probe the entire catalog, not just nemotron models")
    parser.add_argument("--filter", default="nemotron", help="substring a model id must contain (default: nemotron)")
    args = parser.parse_args()

    try:
        api_key = get_api_key("nvidia")
    except RuntimeError as e:
        print(f"[stop] {e}")
        return 1

    catalog = list_nvidia_models(api_key)
    print(f"{len(catalog)} models in NVIDIA's catalog.\n")

    needle = "" if args.all else args.filter.lower()
    candidates = [m for m in catalog if needle in m.lower()]
    if not candidates:
        print(f"No model id contains {args.filter!r}. Try --all.")
        return 1

    print(f"Probing {len(candidates)} candidate(s) -- one real chat request each:\n")
    usable = []
    for model in candidates:
        result = probe(api_key, model)
        if not result["ok"]:
            print(f"  unavailable  {model}\n               {result['why']}")
            continue
        if not result["tools"]:
            detail = result.get("why", "answered, but returned no tool_call")
            print(f"  no tools     {model}\n               {detail}")
            continue
        usable.append(result)
        print(f"  usable       {model}  ({result['seconds']:.1f}s with tools)")

    if not usable:
        print(
            "\nNothing usable with this key. Open a model's page on build.nvidia.com and "
            "use its own 'Try API' panel -- that is what confirms your account is actually "
            "entitled to call it."
        )
        return 1

    usable.sort(key=lambda r: r["seconds"])
    print("\nTool-capable, fastest first:")
    for r in usable:
        print(f"  {r['seconds']:6.1f}s  {r['model']}")

    best = [r["model"] for r in usable]
    # json.dumps, not an f-string of the list: this snippet is meant to be
    # pasted straight into settings.json, and Python's own repr of a list of
    # strings uses single quotes, which is not valid JSON.
    snippet = {"model": {"provider": "nvidia", "name": best[0], "fallbacks": best[1:3]}}
    print("\nFor ~/.raven/settings.json:")
    for line in json.dumps(snippet, indent=2).splitlines():
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
