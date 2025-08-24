import os, time
from typing import Optional

try:
    import speech_recognition as sr
except Exception:
    sr = None

import pyttsx3

class VoiceIO:
    """Text-to-Speech + Speech-to-Text with graceful fallbacks."""
    def __init__(self, use_mic: bool = True, tts_rate: int = 180, stt_lang: str = "en-US"):
        self.use_mic = use_mic and (sr is not None)
        self.stt_lang = stt_lang
        self._engine = pyttsx3.init()
        try:
            self._engine.setProperty('rate', int(tts_rate))
        except Exception:
            pass

        # Prevent feedback loops on some systems by pausing between speak and listen
        self._last_spoke_at = 0.0

    def speak(self, text: str):
        print(f"[TTS] {text}")
        self._engine.say(text)
        self._engine.runAndWait()
        self._last_spoke_at = time.time()

    def listen(self, prompt: Optional[str] = None, timeout: int = 7) -> str:
        if prompt:
            self.speak(prompt)

        # If mic not available, fallback to keyboard
        if not self.use_mic:
            return input("You (type): ").strip()

        r = sr.Recognizer()
        with sr.Microphone() as source:
            # brief pause to avoid self-echo
            slp = max(0, 0.4 - (time.time() - self._last_spoke_at))
            if slp:
                time.sleep(slp)
            r.adjust_for_ambient_noise(source, duration=0.6)
            try:
                audio = r.listen(source, timeout=timeout, phrase_time_limit=12)
            except sr.WaitTimeoutError:
                return ""
        try:
            text = r.recognize_google(audio, language=self.stt_lang)
            print(f"[STT] {text}")
            return text.strip()
        except Exception:
            return ""

# --- Optional: Vosk offline STT (commented stub) ---
# from vosk import Model, KaldiRecognizer
# import pyaudio, json
# class VoskSpeechToText:
#     def __init__(self, model_path="models/vosk-small-en" ):
#         assert os.path.isdir(model_path), "Download a Vosk model and set model_path"
#         self.model = Model(model_path)
#     def listen(self) -> str:
#         # implement streaming recognition
#         pass
