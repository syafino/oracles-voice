# Oracle's Voice

Voice for Claude Code. You talk (with Wispr Flow or any dictation tool), Claude Code talks back.

Oracle is one Python file wired into Claude Code's hooks. It speaks at three moments:

- **When you send a message:** a quick acknowledgement of what it's about to look into.
- **While it works:** the progress notes Claude writes between tool calls.
- **When it finishes:** the reply. Short replies are read as written; long or code-heavy ones become a one- or two-sentence casual summary that points you to the screen instead of reading code aloud.

Sending your next message cuts the voice off mid-sentence.

## Requirements

- macOS (uses the built-in `afplay` and `say`)
- Python 3.8+ (standard library only, nothing to install)
- [Claude Code](https://claude.com/claude-code)
- A [Deepgram](https://deepgram.com) API key, for the voice
- An [Anthropic](https://console.anthropic.com) API key, for the spoken summaries (Claude Haiku)

## Install

1. Clone the repo and create your key file:

   ```sh
   git clone https://github.com/syafino/oracles-voice.git
   cd oracles-voice
   cp .env.example .env
   ```

2. Put your keys in `.env`. Keep them in this file only. Don't export `ANTHROPIC_API_KEY` in your shell: Claude Code would pick it up and bill your API account instead of your subscription.

3. Check that it speaks:

   ```sh
   python3 oracle.py say "yo, this is Oracle"
   ```

4. Add the hooks to `~/.claude/settings.json`, replacing `/path/to/oracle` with where you cloned it. If you already have a `hooks` block, merge these three entries into it.

   ```json
   {
     "hooks": {
       "Stop": [
         { "hooks": [{ "type": "command", "command": "python3 /path/to/oracle/oracle.py" }] }
       ],
       "UserPromptSubmit": [
         { "hooks": [{ "type": "command", "command": "python3 /path/to/oracle/oracle.py" }] }
       ],
       "PreToolUse": [
         { "hooks": [{ "type": "command", "command": "python3 /path/to/oracle/oracle.py" }] }
       ]
     }
   }
   ```

5. Start a new Claude Code session and say something.

Optional shortcut, so you can type `oracle off` from anywhere:

```sh
echo "alias oracle='python3 /path/to/oracle/oracle.py'" >> ~/.zshrc
```

## Commands

| Command | What it does |
| --- | --- |
| `oracle.py off` | Mute, and stop whatever is playing. Stays off across sessions. |
| `oracle.py on` | Unmute. |
| `oracle.py stop` | Cut off the current line. |
| `oracle.py say "text"` | Speak any text. Use this to hook Oracle up to other tools. |
| `oracle.py test` | Run the self-check. |

## Configuration

All in `.env`:

| Key | Purpose |
| --- | --- |
| `DEEPGRAM_API_KEY` | Text to speech. |
| `ANTHROPIC_API_KEY` | Spoken summaries and acknowledgements. |
| `ORACLE_VOICE` | Any Deepgram voice model. Default `aura-2-thalia-en`. |

To change how it talks, edit the `PROMPT` and `ACK` strings at the top of `oracle.py`.

## How it works

Claude Code runs `oracle.py` on each hook and passes the event as JSON on stdin. Oracle hands the text to a detached background process and exits immediately, so Claude Code never waits on audio. The background process picks the words (verbatim for short plain text, Claude Haiku otherwise), fetches audio from Deepgram, and plays it.

State lives in `~/.oracle/`: the mute flag, the player's process ID, and a log.

## Troubleshooting

- **Robotic voice:** the Deepgram call failed and Oracle fell back to the macOS voice. Check `~/.oracle/log`.
- **It only ever says "Done, take a look at the screen.":** the Anthropic call failed. Check `~/.oracle/log`.
- **Silence:** run `oracle.py on`, then `oracle.py say "test"`. If that speaks, the hooks aren't loaded; check `~/.claude/settings.json` and start a new session.

## Limits

- macOS only for now. Linux needs a different player in `speak()`.
- The final reply is spoken after its text appears, because Claude Code only hands a reply to hooks once it is complete.
- Audio is downloaded whole and then played, not streamed. Lines are short, so the delay is small.
