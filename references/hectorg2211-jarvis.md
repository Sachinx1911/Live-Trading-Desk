# hectorg2211/jarvis — "double clap → JARVIS welcome"

- Source: https://github.com/hectorg2211/jarvis (studied commit `4d80831`, 2026-06-21)
- Size: one Python file, `jarvis.py` (1,051 lines), README, requirements. No tests.
- **Licence: none.** No LICENSE file means all rights reserved: ideas only, no code copied.

## What it is

Not an assistant. A desk "start-up ritual" for Windows: the script listens to the microphone,
and on a **double clap** it plays a song, opens Chrome windows on chosen monitors in fullscreen,
speaks a JARVIS-style welcome line, and focuses the code editor. No LLM, no commands, no memory.

## Stack

`numpy` + `sounddevice` (mic), `elevenlabs` (text-to-speech), `python-dotenv`; Windows APIs via
`ctypes` (`EnumDisplayMonitors`, `EnumWindows`, `SetWindowPos`); Chrome command-line flags
(`--new-window`, `--window-position`, `--start-fullscreen`).

## How it works

1. **Clap detection**: RMS of 40 ms blocks against an adaptive noise floor (slow moving
   average updated only when the room is quiet). A clap is a spike ≥ 7× the floor; two spikes
   0.05–0.35 s apart = double clap; cooldown against repeats.
2. **Mic selection**: probes the default input for 0.5 s; if silent, auto-picks the loudest
   working device; override by index or name substring.
3. **Actions** (one sequence, once per process): song (Spotify/YouTube URL) → Chrome window per
   site on a configured monitor (monitors sorted left-to-right, top-to-bottom) → welcome speech
   → focus the editor and send F11.
4. **Window placement**: records Chrome's top-level windows, launches a new one, waits for the
   new window handle to appear, then snaps it to the monitor's rectangle with `SetWindowPos`.
5. **Speech**: ElevenLabs PCM, played in a background thread so the rest does not wait; the
   audio is **cached as WAV keyed by a hash of phrase + voice + model + format**, so the API is
   called only the first time.

## What we can take (ideas)

| Idea | Where it fits for us |
|---|---|
| One trigger runs a fixed bundle of actions, including **where each window goes** | Exactly our *protocol with a layout* (Mark 1 plan §2.4 and §4). "Market Open" = check session/feed + open option chain on screen 2 + chart on screen 1 |
| Monitor list sorted spatially, windows addressed by monitor index | Screen manager (plan §4): our shell needs the same "screen 1 / screen 2" model; on macOS via the shell's monitor API, not Win32 |
| Detect the *new* window, then place it | Same problem our desktop shell will have when JARVIS opens a panel |
| Cache fixed spoken phrases by hash of (text, voice, model, format) | Mark 2 voice: greetings, protocol confirmations and alerts are repeated phrases; cache them to save cost and latency |
| Speak in the background, never block actions | Voice must never delay an alert or a kill-switch action |
| Mic probe + fallback to the loudest working device | Mark 2 voice robustness |
| Clap / gesture as a wake trigger | Low value for us; a keyboard shortcut or wake word fits better. Interesting only as a "no-screen" trigger for Clean Slate |

## What to avoid

- Everything in one file with global constants; hard-coded URLs and a song; runs once per process.
- Windows-only window control; our shell is macOS (plan §4).
- Opens a crypto exchange page with the normal browser profile; no notion of risk or confirmation.
- Committed `__pycache__`, no tests, no licence.

## Verdict

Small, single-purpose demo. Useful as a concrete picture of **protocol + screen layout + cached
voice** for Mark 1 Stage 3–4 and Mark 2. Nothing for the trading engine, memory or tool catalogue.
