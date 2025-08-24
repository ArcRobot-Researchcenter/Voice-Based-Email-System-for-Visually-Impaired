import os, time
from typing import Optional

# --- Speech-to-Text (mic) ---
try:
    import speech_recognition as sr
except Exception:
    sr = None

# --- Text-to-Speech ---
try:
    import pyttsx3
except Exception:
    pyttsx3 = None


class VoiceIO:
    """
    Text-to-Speech + Speech-to-Text with graceful fallbacks.

    - If microphone/STT isn't available, listen() falls back to keyboard input.
    - speak() uses pyttsx3 (offline). stop() can interrupt ongoing speech.
    """

    def __init__(self, use_mic: bool = True, tts_rate: int = 180, stt_lang: str = "en-US", tts_lang_hint: Optional[str] = None):
        self.use_mic = bool(use_mic and (sr is not None))
        self.stt_lang = stt_lang

        # TTS engine
        self._engine = None
        if pyttsx3 is not None:
            try:
                self._engine = pyttsx3.init()
                try:
                    self._engine.setProperty('rate', int(tts_rate))
                except Exception:
                    pass
                if tts_lang_hint:
                    try:
                        target = tts_lang_hint.lower().replace("-", "_")
                        for v in self._engine.getProperty("voices") or []:
                            vid = f"{getattr(v,'id','')}".lower()
                            vnm = f"{getattr(v,'name','')}".lower()
                            vlag = f"{getattr(v,'languages',[])}".lower() if isinstance(getattr(v,'languages',[]), str) else str(getattr(v,'languages',[])).lower()
                            if target in vid or target in vnm or target in vlag:
                                self._engine.setProperty("voice", v.id)
                                break
                    except Exception:
                        pass
            except Exception:
                self._engine = None

        self._last_spoke_at = 0.0

    # ---------- TTS ----------
    def speak(self, text: str):
        if not text:
            return
        print(f"[TTS] {text}")
        if self._engine is None:
            self._last_spoke_at = time.time()
            return
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception:
            pass
        finally:
            self._last_spoke_at = time.time()

    def stop(self):
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:
            pass

    # ---------- STT ----------
    def listen(self, prompt: Optional[str] = None, timeout: int = 7) -> str:
        if prompt:
            self.speak(prompt)

        if not self.use_mic:
            try:
                return input("You (type): ").strip()
            except EOFError:
                return ""

        if sr is None:
            try:
                return input("You (type): ").strip()
            except EOFError:
                return ""

        r = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                slp = max(0.0, 0.4 - (time.time() - self._last_spoke_at))
                if slp:
                    time.sleep(slp)
                try:
                    r.adjust_for_ambient_noise(source, duration=0.6)
                except Exception:
                    pass
                try:
                    audio = r.listen(source, timeout=timeout, phrase_time_limit=12)
                except sr.WaitTimeoutError:
                    return ""
        except Exception:
            return ""

        try:
            text = r.recognize_google(audio, language=self.stt_lang)
            print(f"[STT] {text}")
            return text.strip()
        except Exception:
            return ""
