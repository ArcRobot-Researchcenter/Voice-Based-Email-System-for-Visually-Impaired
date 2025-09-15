# Voice-Based-Email-System-for-Visually-Impaired
A voice-controlled email client designed to empower visually impaired users with accessible communication. Built with Python, PyQt6, SpeechRecognition, and pyttsx3, the system enables users to check inbox, read emails aloud, compose, reply, search, and mark messages as read — all through voice commands.

# Watch video of how the Program works 
[![Watch the demo](https://img.youtube.com/vi/G4OzLi_CXCw/0.jpg)](https://youtu.be/G4OzLi_CXCw)

==========================================================================

✨ Features
-------------------
🎙️ Voice Interaction
--------------------
Issue commands like “check inbox”, “read number two”, “compose”, “reply”, “search invoice”, etc.

Fully supports speech-to-text (STT) via Google API.

Offline fallback: type input if no microphone.

🔊 Text-to-Speech (TTS)
-----------------------
Emails are read aloud for visually impaired users.

Adjustable TTS rate and language in Settings.

📬 Smart Inbox Handling
------------------------
Option to view only Primary Inbox (excludes Promotions, Social, Updates, etc.).

Heuristic filtering for Gmail accounts to avoid bulk/newsletters.

✉️ Email Actions
------------------
Compose new emails (voice or type).

Reply to selected messages.

Mark messages as read.

Search by subject or sender.

🖥️ Accessible GUI (PyQt6)
=
Professional, clean interface with large buttons.

Clickable developer info link.

Status dot animation (Idle / Listening / Working).

Voice-supported Compose dialog (recipient, subject, body via voice).

⚙️ Settings Dialog

Configure microphone use, TTS rate, STT language, and Primary Inbox toggle.

Stored in .env file for easy editing.

---------------------------------------------------------------------------------------
#🛠️ Tech Stack
-------------------
Python 3.9+

PyQt6– GUI

SpeechRecognition – STT

PyAudio – microphone support

pyttsx3 – TTS

python-dotenv – config
 
 ======================================================================

 ⚙️ Setup & Installation
---------------------------

Install dependencies:

pip install -r requirements.txt

Create a .env file with your credentials:

EMAIL_USER=youraddress@gmail.com
EMAIL_PASS=your_app_password
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465

USE_MIC=1
TTS_RATE=180
STT_LANG=en-US
PRIMARY_ONLY=1


⚠️ For Gmail, enable 2FA and use an App Password.

Run the app: python gui.py

============================================================

Example Voice Commands
-----------------------
check inbox

read number one

read next

compose to Alex

reply

search for invoice

mark as read

help
