# Voice‑Based Email System (Starter Kit)

Accessible, voice‑first email client for visually impaired users. Works offline for text‑to‑speech and can use either microphone speech recognition or a simple keyboard fallback when a mic or internet isn’t available.

## Features in this starter
- **Voice prompts + confirmations** using offline TTS (`pyttsx3`).
- **Speech‑to‑Text** via microphone using `SpeechRecognition` (Google recognizer) with a **keyboard fallback**.
- **Inbox triage by voice**: “check inbox”, “read next”, “read number two”, “mark as read”.
- **Compose by voice** with confirmation loop: “compose email to John”, “subject …”, “message …”, “send”.
- **Search** by voice: “search for invoice”.
- **Contacts** lookup with fuzzy match (`difflib`), stored in `contacts.csv`.
- **IMAP/SMTP** for any email provider. For Gmail, use an **App Password** (recommended) or adapt to OAuth later.
- **Privacy‑aware**: no analytics, no message storage; only caches the last message list in memory.

> This is an MVP backbone you can extend with hotword wake‑up, local/offline STT engines (e.g., Vosk), Yoruba/Igbo/Hausa voices, multi‑account, attachments, and IVR/phone access later.

---

## 1) Quick Start

### A. Prerequisites
- Python 3.9+ on Windows/macOS/Linux
- A working mic (optional; you can use keyboard instead)
- For **microphone STT** on Windows: install PortAudio via `pipwin` (see below)

### B. Create a virtual environment & install packages
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

> If you see errors installing `pyaudio` on Windows, try:
```bash
pip install pipwin
pipwin install pyaudio
```

### C. Configure environment
Copy `.env.example` to `.env` and fill your email settings. For **Gmail**, enable 2‑Step Verification and create an **App Password** for “Mail”:
```
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
EMAIL_USER=you@gmail.com
EMAIL_PASS=your_16_char_app_password
USE_MIC=1
TTS_RATE=180
STT_LANG=en-US
```

> If you don’t have a mic or you’re in a noisy place, set `USE_MIC=0`. You’ll still hear the assistant speak, and you’ll type your responses.

### D. Add a few contacts
Edit `contacts.csv` (name,email). Example:
```
John Doe,john@example.com
Raji Alex,rajialex433@gmail.com
```

### E. Run
```bash
python app.py
```
You’ll hear: “Say a command: check inbox, compose, search, help, or quit.”

---

## 2) Voice Commands (Examples)
- **check inbox** → reads latest unread email summaries
- **read number two** → opens and reads message 2 in the current list
- **read next** / **read previous**
- **mark as read** (when reading a message)
- **compose** / **compose email to John** → guided flow to send
- **search for invoice** → searches subject + from + body preview
- **reply** (when reading a message) → guided flow
- **help** → lists commands
- **quit** → exit the app

The app **always confirms critical actions**: after dictating a subject or message, it repeats back, and you say “send” or “edit”. You can interrupt (type or say) **“cancel”** at any time.

---

## 3) Providers & Security
- Works with any IMAP/SMTP provider.
- For Gmail: use an **App Password** (recommended). OAuth can be added later.
- Passwords are read from `.env`. Nothing is written to disk except your `.env` and `contacts.csv`.
- Network calls happen only to your mail server and (for STT) to Google’s Web Speech endpoint **if** USE_MIC=1 and you keep the default recognizer. For fully offline STT, replace `SpeechRecognition` with **Vosk** (see `voice_io.py` stub).

---

## 4) Extending the MVP
- **Offline STT**: Install `vosk` and a small model; switch `VoiceIO` to `VoskSpeechToText` (see code comments).
- **Local languages/accents**: plug Azure TTS voices or Coqui‑TTS for Hausa/Igbo/Yoruba; set a slower `TTS_RATE`.
- **Hotword**: add Porcupine or open‑wake‑word.
- **Better NLU**: swap simple keyword regex for Rasa/LUIS/Azure CLU.
- **Attachments**: speak “attach file report.pdf” (add a file‑picker and MIME handling).
- **IVR/Phone**: move logic into a FastAPI backend; connect Twilio/Asterisk to offer phone call access.
- **Desktop UI**: keep full keyboard shortcuts for sighted helpers; ensure WCAG‑AA contrast and focus order.

---

## 5) Troubleshooting
- **Mic not working** → set `USE_MIC=0` to use keyboard.
- **Gmail login fails** → enable 2FA and create an App Password. Check IMAP is enabled in Gmail settings.
- **It hears wrong words** → move to a quieter room, use a headset mic, or reduce `TTS_RATE` to avoid echo.
- **“TLS/SSL” errors** → confirm ports: IMAP 993 (SSL), SMTP 465 (SSL) or 587 (STARTTLS).

---

## 6) License
MIT for the starter template. Use at your own risk and add appropriate privacy notices for end users.
