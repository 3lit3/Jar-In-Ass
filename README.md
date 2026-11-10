# 3LIT3 — Real-Time Interview Assistant

**A JARVIS fork rebuilt to do one job: listen to a live interview and write the answer you should give — silently, on screen and on your phone.**

3LIT3 began as [JARVIS / MARK LV by FatihMakes](https://github.com/FatihMakes), a general-purpose desktop assistant with a holographic avatar, spoken replies, and system control. This fork keeps the real-time voice engine and removes the desktop-companion layer around it. What is left is a focused interview copilot: it hears the interviewer, understands the question, and streams a first-person answer grounded in your real CV and the context you supplied.

Nothing is ever spoken aloud. Answers appear as text in the app and are mirrored to a Telegram chat you configure, so only you can read them during the call.

> **Where the code lives.** The core assistant (`jarvis/`) and the distribution/licensing build (`shipping/`) live in the private repository **[3lit3/IntAssProject](https://github.com/3lit3/IntAssProject)**. This public repository hosts the packaged **3lit3 Interview Assistant** variant under `Interview Assistant/3lit3 Interview Assistant/`. The documentation below describes the assistant itself.

---

## Table of contents

- [Why this fork exists](#why-this-fork-exists)
- [How it works](#how-it-works)
- [Features](#features)
- [Quick start](#quick-start)
- [The interview workflow](#the-interview-workflow)
- [CV and interview context](#cv-and-interview-context)
- [Telegram live mirror](#telegram-live-mirror)
- [Configuration reference](#configuration-reference)
- [Repository layout](#repository-layout)
- [Design notes](#design-notes)
- [Limitations and responsible use](#limitations-and-responsible-use)
- [Credits and license](#credits-and-license)

---

## Why this fork exists

Stock JARVIS is excellent at being a desktop assistant. That is the problem in an interview: every extra skill, every spoken reply, and every personal-memory injection pulls the model back toward "helpful general assistant" instead of "answer the question the interviewer just asked."

This fork changes that in a few deliberate ways.

| Area | Stock JARVIS | This fork |
| --- | --- | --- |
| **Persona** | General desktop assistant | Hard-locked interview-answer persona; the model is explicitly told it is *not* a general assistant |
| **Voice output** | Speaks every reply | **Silent by default** — answers are text only (`speak_answers: false`). A spoken answer would be heard by the interviewer and would feed back into the call audio |
| **Avatar / desktop chrome** | Avatar-first HUD | Avatar and desktop-companion chrome are removed from the interview flow. The HUD is a suggestion surface; the legacy face renderer is optional and off the critical path |
| **Tools** | Full desktop control — apps, files, browser, settings, reminders, media | Only **screen reading** survives (`screen_process`), for shared questions or code on screen. Everything else is filtered out so the model cannot wander back into assistant mode |
| **Memory** | Personal long-term memory injected into every session | Personal-assistant memory is **not** injected in interview mode. The only context is your CV, the interview context, and the conversation itself |
| **Input** | Microphone | Microphone **or** system/call loopback (the interviewer's voice from the call), with the mic auto-muted in loopback mode |
| **Grounding** | General context | **CV upload** plus an **interview context box**, both persisted and restored across reconnects |
| **Output** | HUD + spoken audio | Streaming **suggestions panel** plus a **live Telegram mirror** |

The prompt itself (`jarvis/core/prompt.txt` in the private repo) reinforces the same idea: output only the candidate's answer, never coach or explain, never invent experience, match the interviewer's language, and keep answers concise and interview-ready.

---

## How it works

```text
        Interviewer's voice
                │
        ┌───────┴────────┐
        │                │
   microphone      system sound (loopback)
        │                │
        │         microphone auto-muted
        └───────┬────────┘
                ▼
      Gemini Live (streaming audio in / text out)
                │
   system prompt = interview persona
                 + [THE CANDIDATE'S CV]
                 + [INTERVIEW CONTEXT]
                 + current conversation
                │
                ▼
   Answer: first person, STAR for behavioural
   questions, grounded, typically < 100 words
                │
        ┌───────┴────────┐
        ▼                ▼
  Suggestions panel   Telegram mirror
      (on screen)      (your phone)
```

1. **Capture** — audio comes from the microphone, or from the system output (WASAPI loopback on Windows) so the assistant hears the interviewer through the call. In loopback mode the microphone is muted so your own voice is never streamed.
2. **Understand** — Gemini Live handles streaming speech recognition and reasoning in one session, with input and output transcription enabled.
3. **Ground** — the system prompt combines the interview persona, the text of your uploaded CV, and any interview context you typed. Both are re-sent on every reconnect, so a dropped packet does not silently erase your background.
4. **Generate** — the model returns only the answer the candidate should give. Behavioural questions follow STAR; technical questions get a direct explanation; system-design questions get a structured approach with trade-offs.
5. **Deliver** — the answer streams word by word into the suggestions panel and is mirrored to Telegram as a single live message that is edited in place.

---

## Features

### Interview core

| Feature | Description |
| --- | --- |
| **Silent answer mode** | Answers are never played through the speakers. Text only, by design (`speak_answers: false`) |
| **Interview persona** | The identity block is replaced in interview mode, and the personal-assistant memory is left out entirely |
| **CV upload** | Drag-and-drop or click to load a CV. Supports `.pdf`, `.docx`, `.txt`, and `.md`; legacy `.doc` is rejected with instructions to re-save as `.docx` or PDF |
| **Interview context box** | Type the role, company, topic, or anything else that should shape the answers. It is folded into the live session and persisted for the next reconnect |
| **Grounded answers** | Every answer is anchored to the CV. The prompt forbids inventing credentials, dates, projects, or metrics |
| **STAR for behavioural questions** | Situation, Task, Action, Result woven into spoken prose — never labelled "S:", "T:", "A:", "R:" |
| **Language matching** | Answers in the interviewer's language, never mixed |
| **Screen reading only** | In interview mode the model is restricted to the screen-reading tool, so it cannot drift into desktop-assistant behaviour |

### Audio

| Feature | Description |
| --- | --- |
| **System sound (loopback)** | Hears the interviewer's voice from the call itself. Runs in a separate process so a driver glitch becomes a one-second dropout instead of a crash |
| **Microphone mode** | Normal mic capture when you are in the room or not using a call |
| **Push-to-talk** | Hold **Ctrl+Space** to open the mic; closed the rest of the time |
| **Audio device picker** | Choose microphone and speakers by name, filtered to devices the OS actually exposes |
| **Self-echo guard** | Recognises and drops the tail of the assistant's own voice so it never answers itself |
| **Session continuity** | A dropped connection, voice change, or device change reconnects without wiping the conversation |

### Delivery and control

| Feature | Description |
| --- | --- |
| **Suggestions panel** | Streaming answer text in the HUD, updated in real time |
| **Telegram live mirror** | The same answer is sent to a chat you configure, edited in place as it grows, and deleted if the interviewer cuts in |
| **Interrupt** | **Esc** / the INTERRUPT button stops the current answer immediately |
| **Remote dashboard** | Pair your phone by QR code and control the assistant from the browser |
| **Fullscreen HUD** | **F11** for a clean, distraction-free overlay |
| **HUD theming** | Recolour the interface from the settings panel |
| **Wake word (optional)** | Local "Hey Jarvis" detection, opt-in — useful outside the call, never required during one |

---

## Quick start

### Requirements

- **Python 3.11 – 3.13**
- A **Gemini API key**
- **Windows 10/11 recommended** — system-sound (loopback) capture uses WASAPI. The base app also runs on macOS and Linux, but call-audio capture is Windows-first
- Optional: a Telegram bot for the phone mirror

### Install

```powershell
# The core app lives in the private repository — clone it first
git clone https://github.com/3lit3/IntAssProject
cd IntAssProject\jarvis
python setup.py
```

Or double-click `install.bat` to create Desktop and Start Menu shortcuts that launch `python -u main.py` with the correct working directory.

### Configure

On first launch the app asks for your Gemini API key. It is stored in `config/api_keys.json`, which is gitignored along with `config/certs/`, `config/*.pdf`, and `.env` files.

Optional integrations are configured from the in-app panels:

- **Setup → TELEGRAM** — bot token and chat ID
- **Setup → AUDIO DEVICES** — microphone and speaker selection
- **Setup → REMOTE CONTROL** — QR pairing for the phone dashboard

### Run

```powershell
python main.py
```

---

## The interview workflow

1. **Upload your CV** — drag it onto the **CV UPLOAD** zone or click to browse. The app extracts the text and confirms how many characters were loaded.
2. **Add interview context** — type the role, company, interview stage, or topics into the **INTERVIEW CONTEXT** box and press Enter. This is the extra context the CV cannot provide.
3. **Pick your audio source** — for a call, enable **SYSTEM SOUND** (the mic mutes itself). For an in-person interview, leave the microphone active.
4. **Join the interview.** Answers begin streaming into the **AI SUGGESTIONS** panel as soon as the interviewer asks a question.
5. **Read, don't speak.** The same text appears in your Telegram chat, so you can glance at your phone instead of the screen.
6. **Interrupt when needed.** Press **Esc** or the **INTERRUPT** button if the interviewer cuts in; the panel and the Telegram message are cleared.
7. **Stay hands-free.** Use **F11** for fullscreen, **Ctrl+Space** for push-to-talk, or the QR-paired dashboard on your phone.

---

## CV and interview context

Both inputs are injected as ordinary client content with `turn_complete=False`, so the model absorbs them silently instead of answering them out loud.

- **CV** — extracted to text and injected as `[THE CANDIDATE'S CV]`, capped at roughly 8,000 characters in the live session. PDF extraction handles multi-column layouts; DOCX extraction also reads table cells, where CVs often keep skills and dates.
- **Context** — injected as `[INTERVIEW CONTEXT]`, capped at roughly 3,000 characters.
- **Persistence** — both are saved to the config (`cv_path`, `interview_context`) and re-injected on every reconnect. A saved CV that fails to parse produces a visible error in the activity log instead of silently answering blind.

> Keep the CV factual. The prompt is explicit that the model must not invent experience, and a CV full of unverifiable claims will produce answers you cannot defend.

---

## Telegram live mirror

The mirror is a single-writer worker thread, which keeps message ordering sane and avoids locks.

1. Create a bot with **@BotFather** and copy the token.
2. Open **Setup → TELEGRAM**, paste the token, send any message to your bot, then press **AUTO-LINK** to fill the chat ID.
3. Answers stream into one message that is edited in place — not a new message per fragment.
4. Writes are rate-limited to roughly one per second, and queued fragments are coalesced, so a fast transcript does not flood the chat.
5. If the interviewer interrupts, the live message is deleted and the next answer starts fresh.

---

## Configuration reference

Settings live in `config/api_keys.json` (created on first run, gitignored).

| Key | Default | Purpose |
| --- | --- | --- |
| `gemini_api_key` | — | Gemini API key |
| `interview_mode` | `true` | Locks the interview persona and restricts tools to screen reading |
| `speak_answers` | `false` | Set `true` to restore spoken answers (not recommended during an interview) |
| `cv_path` | — | Path to the last uploaded CV |
| `interview_context` | — | Last context typed into the interview box |
| `telegram_bot_token` | — | Telegram bot token for the live mirror |
| `telegram_chat_id` | — | Chat that receives the mirrored answers |
| `assistant_name` | `JARVIS` | Display name (used outside interview mode) |
| `user_name` | — | How the assistant addresses you (outside interview mode) |
| `voice_name` | `Charon` | Gemini Live voice (only relevant if `speak_answers` is enabled) |
| `hud_style` | `face` | Legacy HUD centrepiece: `face` or `core`; cosmetic only |

---

## Repository layout

```text
Jar-In-Ass/                                  # this public repository
├── README.md
└── Interview Assistant/
    └── 3lit3 Interview Assistant/           # packaged variant with a Telegram-based purchase flow
        ├── main.py, ui.py                   # jarvis core bundled into the variant
        ├── actions/, core/, dashboard/, config/, memory/, plugins/
        ├── client/                          # end-user client with license gate
        ├── server/                          # license signing / key minting
        └── HANDOFF.md                       # design decisions for this variant

3lit3/IntAssProject/                         # private repository — core source
├── jarvis/                                  # the interview assistant (main app)
│   ├── main.py                              # Entry point, audio pipeline, Live session
│   ├── ui.py                                # PyQt6 HUD, suggestions panel, CV/context UI
│   ├── core/
│   │   ├── prompt.txt                       # Interview-answer prompt and quality rules
│   │   ├── gemini.py                        # Model ladder with timeouts and fallback
│   │   ├── sys_sound_capture.py             # Isolated loopback capture process
│   │   ├── echo.py                          # Self-echo guard
│   │   └── ...
│   ├── actions/                             # Bundled skills (screen reading is the only one enabled in interview mode)
│   ├── dashboard/                           # QR-paired remote dashboard
│   ├── memory/                              # Config and (disabled-in-interview) memory
│   ├── plugins/                             # Drop-in plugin system
│   ├── config/                              # api_keys.json, certificates, icon (gitignored secrets)
│   ├── requirements.txt
│   ├── setup.py
│   └── install.bat
│
└── shipping/                                # Packaged distribution build + license server
    ├── client/                              # End-user GUI wrapper and licensing gate
    ├── server/                              # FastAPI license/payment server (Render)
    ├── 3lit3/                               # PyInstaller build definition
    └── schema.sql
```

---

## Design notes

**Why answers are never spoken.** A spoken answer is audible to the interviewer and, with loopback capture on, would be fed straight back into the model's own input. Text is the only safe output channel for this use case, so it is the default and the prompt is written around it.

**Why system sound instead of a microphone.** In a video call, the interviewer's voice arrives through your speakers or headset, not through the room. Capturing the loopback hears exactly what you hear, and muting the microphone keeps your own voice out of the transcript.

**Why only screen reading survives.** Every other bundled skill — browser control, file operations, reminders, settings — is a door back into general-assistant behaviour. Removing them from the tool list removes the temptation and saves prompt tokens on every connection.

**Why the CV and context are re-sent.** Session resumption handles cover the conversation, but a reconnect that starts clean would otherwise forget the two things that make the answers yours. Re-injecting them is cheap and makes reconnects invisible.

---

## Limitations and responsible use

- **Legacy `.doc` files are not supported.** Re-save as `.docx` or PDF.
- **Loopback capture is Windows-first.** macOS and Linux can run the app, but capturing call audio reliably depends on the platform's audio stack (for example a virtual loopback device).
- **Gemini API usage is metered.** Long sessions consume quota; the model ladder falls back across models but does not make calls free.
- **Answers are suggestions, not facts.** The prompt forbids fabrication, but you remain responsible for what you say in an interview. Review the answer before repeating it, and never claim experience you do not have.
- **Use it where it is allowed.** Many employers and interview platforms prohibit live AI assistance. Check the rules you agreed to before using this in a real interview.

---

## Credits and license

This project is a fork of **JARVIS / MARK LV** by **[FatihMakes](https://github.com/FatihMakes)**, used under the **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)** license. The original copyright and license notice are retained in `jarvis/LICENSE` in the private repository.

The interview adaptation — the interview persona, silent text-only delivery, CV and context grounding, loopback-first capture, and the Telegram mirror — is built on top of that work.

Commercial use is not permitted under the inherited license. If you need commercial rights, contact the original author.
