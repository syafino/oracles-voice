#!/usr/bin/env python3
"""Oracle: speaks Claude Code replies. Usage: oracle.py [stop|on|off|say TEXT|test] (no args = Stop hook, JSON on stdin)."""
import json, os, re, signal, subprocess, sys, tempfile, urllib.request, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path.home() / ".oracle"
PID, OFF, LOG, MP3, LAST = HOME / "pid", HOME / "off", HOME / "log", HOME / "out.mp3", HOME / "last"
FALLBACK = "Done, take a look at the screen."
PROMPT = (
    "You are the voice of a coding assistant talking out loud to a friend. You get the assistant's "
    "written reply; say what happened in one or two short, casual spoken sentences, first person. "
    "If the substance is code, a diff, a table, a list or a long write-up, don't read it out: say "
    "in a few words what it is and tell them to look at the screen. If it asks the user a question, "
    "ask it. No markdown, no file paths, no symbols. Output only the words to speak."
)
ACK = (
    "The user just said this to their coding assistant, which is now starting to work on it. You are "
    "its voice: say one short, casual spoken sentence acknowledging what you're about to look into. "
    "Don't answer the question or promise a result. Output only the words to speak."
)


def env(key, default=""):
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == key and v.strip():
                return v.strip().strip("\"'")
    return os.environ.get(key, default)


def post(url, headers, body):
    req = urllib.request.Request(
        url, json.dumps(body).encode(), {"Content-Type": "application/json", "User-Agent": "oracle/1", **headers}
    )
    return urllib.request.urlopen(req, timeout=20).read()


def last_text(path):
    """Final assistant text in a Claude Code transcript JSONL."""
    out = ""
    for line in open(path):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") != "assistant" or d.get("isSidechain"):
            continue
        content = (d.get("message") or {}).get("content")
        if isinstance(content, list):
            text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            out = text or out
    return out


def plain(text):
    """Short enough and prose enough to read aloud as is."""
    return len(text) < 300 and not re.search(r"```|^\s*([-*#|]|\d+\.)\s", text, re.M)


def clean(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"[`*_#]", "", text).strip()


def haiku(system, text, max_tokens):
    try:
        r = post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
            {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": max_tokens,
                "system": system,
                # ponytail: head of the text only; summarise head+tail if long replies get misread
                "messages": [{"role": "user", "content": text[:6000]}],
            },
        )
        return json.loads(r)["content"][0]["text"].strip()
    except Exception as e:
        log(f"haiku: {e}")
        return ""


def spoken(text):
    return clean(text) if plain(text) else haiku(PROMPT, text, 120) or FALLBACK


def playing():
    try:
        os.killpg(int(PID.read_text()), 0)
        return True
    except (OSError, ValueError):
        return False


def seen(text):
    """True if this text was already handled; remembers it either way."""
    h = str(zlib.crc32(text.encode()))
    old = LAST.read_text() if LAST.exists() else ""
    LAST.write_text(h)
    return h == old


def spawn(kind, text):
    # detached, so Claude Code never waits on audio
    p = subprocess.Popen(
        [sys.executable, __file__, "_speak", kind],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=open(LOG, "a"),
        start_new_session=True, text=True,
    )
    p.stdin.write(text)
    p.stdin.close()


def stop():
    try:
        os.killpg(int(PID.read_text()), signal.SIGTERM)
    except (OSError, ValueError):
        pass
    PID.unlink(missing_ok=True)


def speak(line):
    stop()
    try:
        os.setpgrp()  # own group, so stop() takes the player down with us
    except OSError:
        pass
    PID.write_text(str(os.getpgrp()))
    try:
        audio = post(
            f"https://api.deepgram.com/v1/speak?model={env('ORACLE_VOICE', 'aura-2-thalia-en')}",
            {"Authorization": f"Token {env('DEEPGRAM_API_KEY')}"},
            {"text": line[:1500]},
        )
        # ponytail: whole clip then afplay; pipe the stream into ffplay if the delay is noticeable
        MP3.write_bytes(audio)
        subprocess.run(["afplay", str(MP3)])
    except Exception as e:
        log(f"deepgram: {e}")
        subprocess.run(["say", line])  # free offline voice so a bad key is never silent
    PID.unlink(missing_ok=True)


def log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")


def test():
    assert plain("Yep, that's fixed now.")
    assert not plain("Here:\n```py\nx = 1\n```")
    assert not plain("Changes:\n- one\n- two")
    assert not plain("word " * 100)
    assert clean("Fixed `foo` in [bar](a/b.py), **done**.") == "Fixed foo in bar, done."
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        rows = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "old"}]}},
            {"type": "user", "message": {"content": "hi"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "new"}]}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use"}]}},
            {"type": "assistant", "isSidechain": True, "message": {"content": [{"type": "text", "text": "sub"}]}},
        ]
        f.write("not json\n" + "\n".join(map(json.dumps, rows)))
    assert last_text(f.name) == "new"
    os.unlink(f.name)
    LAST.unlink(missing_ok=True)
    assert not seen("a") and seen("a") and not seen("b")
    LAST.unlink(missing_ok=True)
    print("ok")


def main():
    HOME.mkdir(exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "hook"
    if cmd == "stop":
        stop()
    elif cmd == "off":
        stop()
        OFF.touch()
    elif cmd == "on":
        OFF.unlink(missing_ok=True)
    elif cmd == "test":
        test()
    elif cmd == "say":
        speak(" ".join(sys.argv[2:]))
    elif cmd == "_speak":
        kind, text = sys.argv[2], sys.stdin.read()
        if kind == "ack":
            line = haiku(ACK, text, 40)
        elif kind == "narrate" and playing():
            line = ""  # don't cut off a line mid-sentence for a progress note
        else:
            line = spoken(text)
        if line:
            speak(line)
    elif cmd == "hook" and not OFF.exists():
        d = json.load(sys.stdin)
        event, path = d.get("hook_event_name"), d.get("transcript_path") or ""
        prior = last_text(path) if os.path.exists(path) else ""
        if event == "UserPromptSubmit":
            stop()
            seen(prior)  # last turn's reply is old news
            if not d.get("prompt", "").startswith("/"):
                spawn("ack", d.get("prompt", ""))
        elif event == "PreToolUse":
            # ponytail: rereads the whole transcript per tool call; tail it if sessions get huge
            if prior and not seen(prior):
                spawn("narrate", prior)
        else:
            text = d.get("last_assistant_message") or prior
            if text.strip():
                spawn("final", text)


if __name__ == "__main__":
    main()
