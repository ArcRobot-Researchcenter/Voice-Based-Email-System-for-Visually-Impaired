import os, sys, csv, difflib, re, threading
from typing import List, Dict
from dotenv import load_dotenv
from PyQt6 import QtCore, QtGui, QtWidgets

from email_client import EmailClient
from voice_io import VoiceIO

# -------- Number parsing for voice commands --------
WORD_NUM = {
    "zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,
    "eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,"seventeen":17,
    "eighteen":18,"nineteen":19,"twenty":20
}
ORDINAL_NUM = {
    "zeroth":0,"first":1,"second":2,"third":3,"fourth":4,"fifth":5,"sixth":6,"seventh":7,"eighth":8,"ninth":9,"tenth":10,
    "eleventh":11,"twelfth":12,"thirteenth":13,"fourteenth":14,"fifteenth":15,"sixteenth":16,"seventeenth":17,
    "eighteenth":18,"nineteenth":19,"twentieth":20
}

def extract_index(text: str) -> int:
    t = (text or "").lower().strip()
    m = re.search(r"(\d+)", t)
    if m:
        try: return int(m.group(1))
        except: pass
    for w, n in ORDINAL_NUM.items():
        if re.search(rf"\b{w}\b", t): return n
    for w, n in WORD_NUM.items():
        if re.search(rf"\b{w}\b", t): return n
    return -1

# -------- Contacts helpers --------
def load_contacts(path: str = 'contacts.csv') -> Dict[str, str]:
    m = {}
    if not os.path.exists(path): return m
    with open(path, newline='', encoding='utf-8') as f:
        for row in csv.reader(f):
            if not row: continue
            name, email = row[0].strip(), row[1].strip()
            if name and email:
                m[name.lower()] = email
    return m

def resolve_contact(name: str, contacts: Dict[str, str]) -> str:
    email = contacts.get(name.lower())
    if email: return email
    choices = difflib.get_close_matches(name.lower(), list(contacts.keys()), n=1, cutoff=0.6)
    return contacts.get(choices[0], '') if choices else ''

def strip_address(frm: str) -> str:
    m = re.search(r"<([^>]+)>", frm)
    return m.group(1) if m else frm.split()[-1]

# -------- Worker infra --------
class Worker(QtCore.QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn; self.args = args; self.kwargs = kwargs
        self.signals = WorkerSignals()
    @QtCore.pyqtSlot()
    def run(self):
        try:
            res = self.fn(*self.args, **self.kwargs)
            self.signals.success.emit(res)
        except Exception as e:
            self.signals.error.emit(str(e))

class WorkerSignals(QtCore.QObject):
    success = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(str)

# -------- Settings Dialog --------
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, env_path=".env"):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.env_path = env_path

        layout = QtWidgets.QFormLayout(self)

        self.use_mic = QtWidgets.QCheckBox("Enable microphone (USE_MIC)")
        self.tts_rate = QtWidgets.QSpinBox(); self.tts_rate.setRange(80, 260); self.tts_rate.setSingleStep(10)
        self.stt_lang = QtWidgets.QLineEdit()
        self.primary_only = QtWidgets.QCheckBox("Primary Inbox only (PRIMARY_ONLY)")

        vals = self._read_env()
        self.use_mic.setChecked(vals.get("USE_MIC","1")=="1")
        self.tts_rate.setValue(int(vals.get("TTS_RATE","180")))
        self.stt_lang.setText(vals.get("STT_LANG","en-US"))
        self.primary_only.setChecked(vals.get("PRIMARY_ONLY","1")=="1")

        layout.addRow(self.use_mic)
        layout.addRow("TTS rate", self.tts_rate)
        layout.addRow("STT language", self.stt_lang)
        layout.addRow(self.primary_only)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addRow(buttons)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self.resize(420, 240)

    def _read_env(self) -> Dict[str,str]:
        vals = {}
        if os.path.exists(self.env_path):
            with open(self.env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        k,v = line.strip().split("=",1)
                        vals[k.strip()] = v.strip()
        # ensure keys exist
        for k,default in {
            "USE_MIC":"1","TTS_RATE":"180","STT_LANG":"en-US","PRIMARY_ONLY":"1",
            "IMAP_HOST":os.getenv("IMAP_HOST","imap.gmail.com"),
            "IMAP_PORT":os.getenv("IMAP_PORT","993"),
            "SMTP_HOST":os.getenv("SMTP_HOST","smtp.gmail.com"),
            "SMTP_PORT":os.getenv("SMTP_PORT","465"),
            "EMAIL_USER":os.getenv("EMAIL_USER",""),
            "EMAIL_PASS":os.getenv("EMAIL_PASS",""),
        }.items():
            vals.setdefault(k, default)
        return vals

    def _save(self):
        vals = self._read_env()
        vals["USE_MIC"] = "1" if self.use_mic.isChecked() else "0"
        vals["TTS_RATE"] = str(self.tts_rate.value())
        vals["STT_LANG"] = self.stt_lang.text().strip() or "en-US"
        vals["PRIMARY_ONLY"] = "1" if self.primary_only.isChecked() else "0"

        with open(self.env_path, "w", encoding="utf-8") as f:
            for k,v in vals.items():
                f.write(f"{k}={v}\n")
        QtWidgets.QMessageBox.information(self, "Settings saved", "Settings saved to .env.\nRestart the app to apply.")
        self.accept()

# -------- Voice-friendly Compose Dialog --------
class ComposeDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, contacts=None, voice: VoiceIO=None):
        super().__init__(parent)
        self.setWindowTitle("Compose Email")
        self.contacts = contacts or {}
        self.voice = voice

        form = QtWidgets.QFormLayout(self)

        # To
        to_row = QtWidgets.QHBoxLayout()
        self.to_edit = QtWidgets.QLineEdit()
        self.btn_to_voice = QtWidgets.QPushButton("🎙️")
        self.btn_to_voice.setToolTip("Speak recipient name or email")
        to_row.addWidget(self.to_edit, 1); to_row.addWidget(self.btn_to_voice)
        form.addRow("To (name or email)", to_row)

        # Subject
        subj_row = QtWidgets.QHBoxLayout()
        self.subj_edit = QtWidgets.QLineEdit()
        self.btn_subj_voice = QtWidgets.QPushButton("🎙️")
        self.btn_subj_voice.setToolTip("Speak subject")
        subj_row.addWidget(self.subj_edit, 1); subj_row.addWidget(self.btn_subj_voice)
        form.addRow("Subject", subj_row)

        # Body
        self.body_edit = QtWidgets.QPlainTextEdit()
        self.body_edit.setPlaceholderText("Speak or type your message…")
        form.addRow("Body", self.body_edit)

        dict_row = QtWidgets.QHBoxLayout()
        self.btn_dictate = QtWidgets.QPushButton("🎙️ Dictate Body")
        self.btn_stop = QtWidgets.QPushButton("■ Stop")
        dict_row.addWidget(self.btn_dictate); dict_row.addWidget(self.btn_stop)
        form.addRow(dict_row)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(buttons)

        # wiring
        self.btn_to_voice.clicked.connect(self._voice_to)
        self.btn_subj_voice.clicked.connect(self._voice_subject)
        self.btn_dictate.clicked.connect(self._voice_body)
        self.btn_stop.clicked.connect(self._stop_tts)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        self.resize(680, 520)

    def _speak(self, text: str):
        if self.voice: self.voice.speak(text)

    def _listen(self, prompt: str) -> str:
        if not self.voice:
            QtWidgets.QMessageBox.information(self, "Mic disabled", "Microphone is disabled (USE_MIC=0).")
            return ""
        return self.voice.listen(prompt)

    def _stop_tts(self):
        if self.voice: self.voice.stop()

    def _voice_to(self):
        heard = self._listen("Who do you want to email? You can say a name in your contacts or spell an address.")
        if not heard: return
        if '@' in heard:
            to_email = heard.replace(' at ', '@').replace(' dot ', '.').replace(' ', '')
        else:
            to_email = resolve_contact(heard, self.contacts) or heard
        self.to_edit.setText(to_email)

    def _voice_subject(self):
        heard = self._listen("What is the subject?")
        if not heard: return
        self.subj_edit.setText(heard)

    def _voice_body(self):
        if not self.voice:
            QtWidgets.QMessageBox.information(self, "Mic disabled", "Microphone is disabled (USE_MIC=0).")
            return
        self._speak("Start speaking your message. Say 'stop message' when done.")
        lines = []
        while True:
            txt = self.voice.listen()
            if not txt:
                continue
            if 'stop message' in txt.lower() or 'full stop' in txt.lower():
                break
            lines.append(txt)
            existing = self.body_edit.toPlainText()
            self.body_edit.setPlainText((existing + ("\n" if existing else "") + txt))

    def get_values(self):
        to_raw = (self.to_edit.text() or "").strip()
        if '@' in to_raw:
            to_email = to_raw.replace(' at ', '@').replace(' dot ', '.').replace(' ', '')
        else:
            to_email = resolve_contact(to_raw, self.contacts) or to_raw
        subject = (self.subj_edit.text() or "(no subject)").strip()
        body = (self.body_edit.toPlainText() or "").strip()
        return to_email, subject, body

# -------- Main Window --------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        load_dotenv()

        # Config
        self.use_mic = os.getenv('USE_MIC', '1') == '1'
        tts_rate = int(os.getenv('TTS_RATE', '180'))
        stt_lang = os.getenv('STT_LANG', 'en-US')
        self.primary_only = os.getenv('PRIMARY_ONLY', '1') == '1'

        self.voice = VoiceIO(use_mic=self.use_mic, tts_rate=tts_rate, stt_lang=stt_lang)

        imap_host = os.getenv('IMAP_HOST', 'imap.gmail.com')
        imap_port = int(os.getenv('IMAP_PORT', '993'))
        smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '465'))
        user = os.getenv('EMAIL_USER')
        pw = os.getenv('EMAIL_PASS')

        if not user or not pw:
            QtWidgets.QMessageBox.critical(self, "Missing credentials",
                "EMAIL_USER or EMAIL_PASS not set in .env.\nClose the app and fix your .env.")
            sys.exit(1)

        self.mail = EmailClient(imap_host, imap_port, smtp_host, smtp_port, user, pw)
        self.contacts = load_contacts()
        self.pool = QtCore.QThreadPool.globalInstance()

        self.setWindowTitle("VOICE BASED EMAIL SYSTEM FOR VISUALLY IMPAIRED")
        self.resize(1200, 760)
        self._build_ui()
        self._apply_style()

        self.voice_thread = None
        self._set_status_idle()
        self.voice.speak("Welcome to your voice email. Press Control plus I to check inbox, or Control plus Space to speak a command.")

    # ----- UI -----
    def _build_ui(self):
        central = QtWidgets.QWidget(self); self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        # Header: Title + Developer Info (clickable)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("<b style='font-size:20px;'>VOICE BASED EMAIL SYSTEM FOR VISUALLY IMPAIRED</b>")
        dev = QtWidgets.QLabel("Developed by <b>Abdulrahaman Raji</b>, ARC ROBOTICS Research Team. "
                               "Website: <a href='https://academicprojectworld.com'>academicprojectworld.com</a>")
        dev.setTextFormat(QtCore.Qt.TextFormat.RichText); dev.setOpenExternalLinks(True)
        header.addWidget(title, 1); header.addWidget(dev, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        root.addLayout(header)

        # Command bar (type or speak)
        cmdbar = QtWidgets.QHBoxLayout()
        self.cmd_edit = QtWidgets.QLineEdit(); self.cmd_edit.setPlaceholderText("Try: check inbox, read number two, compose to Alex…")
        self.btn_run = QtWidgets.QPushButton("Run")
        self.btn_mic = QtWidgets.QPushButton("🎙️ Speak (Ctrl+Space)")
        cmdbar.addWidget(QtWidgets.QLabel("Command:")); cmdbar.addWidget(self.cmd_edit, 1)
        cmdbar.addWidget(self.btn_run); cmdbar.addWidget(self.btn_mic)
        root.addLayout(cmdbar)

        # Status / animation
        animrow = QtWidgets.QHBoxLayout()
        self.status_dot = QtWidgets.QLabel("●"); self.status_text = QtWidgets.QLabel("Idle")
        self.status_dot.setStyleSheet("color:#10b981; font-size:18px;")
        animrow.addWidget(self.status_dot); animrow.addWidget(self.status_text); animrow.addStretch(1)
        root.addLayout(animrow)

        # Main split
        main = QtWidgets.QHBoxLayout(); root.addLayout(main, 1)

        # Sidebar buttons
        side = QtWidgets.QVBoxLayout(); main.addLayout(side, 0)
        def big_btn(text, shortcut=None, tip=None):
            b = QtWidgets.QPushButton(text); b.setMinimumHeight(48)
            f = b.font(); f.setPointSize(14); b.setFont(f)
            if shortcut: b.setShortcut(shortcut)
            if tip: b.setToolTip(tip)
            return b

        self.btn_check = big_btn("📬 Check Inbox", "Ctrl+I", "Fetch unread/latest Primary messages")
        self.btn_read  = big_btn("🔊 Read Selected", "Enter", "Read the highlighted message")
        self.btn_next  = big_btn("➡️ Read Next", None, "Read next in the list")
        self.btn_comp  = big_btn("✉️ Compose", "Ctrl+N", "Compose a new email (voice-supported)")
        self.btn_reply = big_btn("↩️ Reply", None, "Reply to selected")
        self.btn_mark  = big_btn("✅ Mark as Read", "Del", "Mark selected as read")
        self.btn_settings = big_btn("⚙️ Settings", None, "Edit .env (mic, TTS rate, language, Primary only)")
        self.btn_speak_text = big_btn("🔊 Speak Viewer", None, "Speak loaded message")
        self.btn_stop = big_btn("■ Stop", "Esc", "Stop speaking")

        for b in [self.btn_check, self.btn_read, self.btn_next, self.btn_comp, self.btn_reply, self.btn_mark, self.btn_settings, self.btn_speak_text, self.btn_stop]:
            side.addWidget(b)
        side.addStretch(1)

        # Middle: search + table + viewer
        mid = QtWidgets.QVBoxLayout(); main.addLayout(mid, 1)
        srow = QtWidgets.QHBoxLayout()
        self.search_edit = QtWidgets.QLineEdit(); self.search_edit.setPlaceholderText("Search subject/from (Ctrl+F)")
        self.search_btn = QtWidgets.QPushButton("Search"); self.search_btn.setShortcut("Ctrl+F")
        srow.addWidget(self.search_edit, 1); srow.addWidget(self.search_btn)
        mid.addLayout(srow)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "From", "Subject", "Date"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(False)
        self.table.setColumnWidth(0, 50); self.table.setColumnWidth(1, 280); self.table.setColumnWidth(2, 520)
        mid.addWidget(self.table, 2)

        self.viewer = QtWidgets.QPlainTextEdit(); self.viewer.setReadOnly(True)
        self.viewer.setPlaceholderText("Message body will appear here…")
        mid.addWidget(self.viewer, 1)

        # Connect
        self.btn_check.clicked.connect(self.on_check_inbox)
        self.btn_read.clicked.connect(self.on_read_selected)
        self.btn_next.clicked.connect(self.on_read_next)
        self.btn_comp.clicked.connect(self.on_compose)
        self.btn_reply.clicked.connect(self.on_reply)
        self.btn_mark.clicked.connect(self.on_mark_read)
        self.search_btn.clicked.connect(self.on_search)
        self.table.itemSelectionChanged.connect(lambda: self.viewer.setPlainText(""))
        self.btn_speak_text.clicked.connect(self.on_speak_viewer)
        self.btn_stop.clicked.connect(self.on_stop_speaking)
        self.btn_settings.clicked.connect(self.on_settings)
        self.btn_run.clicked.connect(self.on_run_command)
        self.btn_mic.clicked.connect(self.on_speak_command)

        # Ctrl+Space for voice command
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Space"), self, activated=self.on_speak_command)

        # Pulse animation
        self._pulse = False
        self._timer = QtCore.QTimer(self); self._timer.setInterval(300); self._timer.timeout.connect(self._tick)

        self.uid_map: Dict[int, bytes] = {}
        self.cur_list: List[Dict] = []

    def _apply_style(self):
        self.setStyleSheet("""
        QMainWindow { background: #f8fafc; }
        QLabel { font-size: 14px; }
        QPushButton {
            background: #111827; color: white; border: none; border-radius: 10px;
            padding: 10px 16px;
        }
        QPushButton:hover { background: #1f2937; }
        QLineEdit, QPlainTextEdit, QTableWidget {
            background: white; border: 1px solid #e5e7eb; border-radius: 10px;
            padding: 8px; font-size: 14px;
        }
        QHeaderView::section { background: #e5e7eb; border: none; padding: 6px; }
        """)

    # ----- Status / animation -----
    def _set_status_idle(self, text="Idle"):
        self.status_text.setText(text)
        self.status_dot.setStyleSheet("color:#10b981; font-size:18px;")
        self._timer.stop(); self.status_dot.setVisible(True)

    def _set_status_working(self, text="Working…"):
        self.status_text.setText(text)
        self.status_dot.setStyleSheet("color:#3b82f6; font-size:18px;")
        self._pulse = True; self._timer.start()

    def _set_status_listening(self, text="Listening…"):
        self.status_text.setText(text)
        self.status_dot.setStyleSheet("color:#f59e0b; font-size:18px;")
        self._pulse = True; self._timer.start()

    def _tick(self):
        self.status_dot.setVisible(not self.status_dot.isVisible())

    # ----- Core actions -----
    def on_check_inbox(self):
        self._set_status_working("Checking Inbox…")
        worker = Worker(self.mail.list_unread, 10, self.primary_only)
        worker.signals.success.connect(self._populate_table)
        worker.signals.error.connect(self._error)
        self.pool.start(worker)

    def _populate_table(self, msgs: List[Dict]):
        self.cur_list = msgs or []
        self.uid_map.clear()
        self.table.setRowCount(0)
        if not msgs:
            self.viewer.setPlainText(""); self._set_status_idle("No messages")
            QtWidgets.QMessageBox.information(self, "Inbox", "No messages found in Primary Inbox." if self.primary_only else "No messages found in Inbox.")
            return
        for it in msgs:
            r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(it['index'])))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(it['from']))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(it['subject'] or "(no subject)"))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(it.get('date', "")))
            self.uid_map[it['index']] = it['uid']
        self.table.selectRow(0); self._set_status_idle("Inbox loaded")

    def _fetch_body(self, uid):
        return self.mail.fetch_message(uid)

    def on_read_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.cur_list):
            QtWidgets.QMessageBox.information(self, "Read", "Please select a message.")
            return
        idx = int(self.table.item(row, 0).text()); uid = self.uid_map.get(idx)
        if not uid:
            QtWidgets.QMessageBox.warning(self, "Read", "Internal mapping error.")
            return
        self._set_status_working("Opening message…")
        worker = Worker(self._fetch_body, uid)
        worker.signals.success.connect(self._show_message)
        worker.signals.error.connect(self._error)
        self.pool.start(worker)

    def on_read_next(self):
        row = self.table.currentRow(); row = -1 if row < 0 else row
        nxt = row + 1
        if nxt >= len(self.cur_list):
            self.voice.speak("You are at the last message."); return
        self.table.selectRow(nxt); self.on_read_selected()

    def _show_message(self, tup):
        frm, subj, body = tup
        txt = f"From: {frm}\nSubject: {subj or '(no subject)'}\n\n{body or '(no readable body)'}"
        self.viewer.setPlainText(txt)
        self._set_status_idle("Message ready")

    def on_search(self):
        q = self.search_edit.text().strip()
        if not q:
            QtWidgets.QMessageBox.information(self, "Search", "Type a keyword to search."); return
        self._set_status_working(f"Searching for {q}…")
        worker = Worker(self.mail.search, q, 10)
        worker.signals.success.connect(self._populate_table)
        worker.signals.error.connect(self._error)
        self.pool.start(worker)

    def on_compose(self):
        dlg = ComposeDialog(self, contacts=self.contacts, voice=(self.voice if self.use_mic else None))
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            to_email, subject, body = dlg.get_values()
            if not to_email or '@' not in to_email:
                QtWidgets.QMessageBox.warning(self, "Compose", "Please provide a valid recipient email.")
                return
            self._set_status_working("Sending…")
            worker = Worker(self.mail.send, to_email, subject or "(no subject)", body or "")
            worker.signals.success.connect(lambda _: (self._set_status_idle("Sent"), QtWidgets.QMessageBox.information(self, "Compose", "Sent.")))
            worker.signals.error.connect(self._error)
            self.pool.start(worker)

    def on_reply(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.cur_list):
            QtWidgets.QMessageBox.information(self, "Reply", "Please select a message."); return
        idx = int(self.table.item(row, 0).text()); uid = self.uid_map.get(idx)
        if not uid:
            QtWidgets.QMessageBox.warning(self, "Reply", "Internal mapping error."); return
        frm, subj, _ = self.mail.fetch_message(uid)
        to_email = strip_address(frm)
        if '@' not in to_email:
            QtWidgets.QMessageBox.warning(self, "Reply", "Could not detect a valid reply address."); return
        text, ok = QtWidgets.QInputDialog.getMultiLineText(self, "Reply", f"To: {to_email}\nSubject: Re: {subj or '(no subject)'}", "")
        if not ok or not text.strip(): return
        self._set_status_working("Sending reply…")
        worker = Worker(self.mail.send, to_email, "Re: " + (subj or "(no subject)"), text.strip())
        worker.signals.success.connect(lambda _: (self._set_status_idle("Reply sent"), QtWidgets.QMessageBox.information(self, "Reply", "Reply sent.")))
        worker.signals.error.connect(self._error)
        self.pool.start(worker)

    def on_mark_read(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.cur_list):
            QtWidgets.QMessageBox.information(self, "Mark as Read", "Please select a message.")
            return
        idx_item = self.table.item(row, 0)
        if not idx_item:
            QtWidgets.QMessageBox.warning(self, "Mark as Read", "No row selected.")
            return
        try:
            idx = int(idx_item.text())
        except Exception:
            QtWidgets.QMessageBox.warning(self, "Mark as Read", "Invalid selection.")
            return

        uid = self.uid_map.get(idx)
        if not uid:
            QtWidgets.QMessageBox.warning(self, "Mark as Read", "Internal mapping error.")
            return

        self._set_status_working("Marking as read…")
        worker = Worker(self.mail.mark_seen, uid)
        worker.signals.success.connect(lambda _: (
            self._set_status_idle("Marked as read"),
            QtWidgets.QMessageBox.information(self, "Mark as Read", "Marked as read.")
        ))
        worker.signals.error.connect(self._error)
        self.pool.start(worker)

    # ----- Speak / Stop -----
    def _speak_async(self, text):
        self._set_status_working("Speaking…")
        try:
            self.voice.speak(text)
        finally:
            self._set_status_idle("Done")

    def on_speak_viewer(self):
        txt = self.viewer.toPlainText().strip()
        if not txt:
            self.voice.speak("No message loaded yet."); return
        snippet = txt[:1000]
        if self.voice_thread and self.voice_thread.is_alive(): return
        self.voice_thread = threading.Thread(target=self._speak_async, args=(snippet,), daemon=True)
        self.voice_thread.start()

    def on_stop_speaking(self):
        self.voice.stop(); self._set_status_idle("Stopped")

    # ----- Voice command bar -----
    def on_run_command(self):
        cmd = self.cmd_edit.text().strip().lower()
        if not cmd:
            self.voice.speak("Type a command or press Speak."); return
        self._execute_command(cmd)

    def on_speak_command(self):
        if not self.use_mic:
            QtWidgets.QMessageBox.information(self, "Mic disabled", "Microphone is disabled (USE_MIC=0). Enable it in .env and restart.")
            return
        self._set_status_listening("Listening… Speak a command")
        QtCore.QTimer.singleShot(100, self._listen_and_execute)

    def _listen_and_execute(self):
        try:
            cmd = self.voice.listen()
        finally:
            self._set_status_idle("Idle")
        cmd = (cmd or "").lower().strip()
        if not cmd:
            self.voice.speak("I didn't catch that."); return
        self.cmd_edit.setText(cmd); self._execute_command(cmd)

    def _execute_command(self, cmd: str):
        if self.cur_list and not any(w in cmd for w in ["read","open","compose","search","reply","mark","check","inbox","next"]):
            idx = extract_index(cmd)
            if idx != -1:
                cmd = f"read number {idx}"

        if "help" in cmd:
            self.voice.speak("You can say: check inbox, read number two, read next, compose, search for invoice, reply, or mark as read."); return
        if ("check" in cmd and "inbox" in cmd) or "unread" in cmd:
            self.on_check_inbox(); return
        if "read next" in cmd or cmd.strip()=="next":
            self.on_read_next(); return
        if "read" in cmd and ("number" in cmd or re.search(r"\bread\s+\d+\b", cmd)):
            n = extract_index(cmd)
            if n == -1:
                self.voice.speak("Please say the message number, like read number two."); return
            for r in range(self.table.rowCount()):
                if int(self.table.item(r,0).text()) == n:
                    self.table.selectRow(r); self.on_read_selected(); return
            self.voice.speak("That number is not in the current list."); return
        if "compose" in cmd or "send email" in cmd:
            self.on_compose(); return
        if "search" in cmd:
            q = cmd.split("search",1)[1].replace("for","").strip()
            if not q:
                self.voice.speak("Say search for, then a keyword."); return
            self.search_edit.setText(q); self.on_search(); return
        if "reply" in cmd:
            self.on_reply(); return
        if "mark" in cmd and "read" in cmd:
            self.on_mark_read(); return

        self.voice.speak("Sorry, I don't know that command yet.")

    # ----- Settings -----
    def on_settings(self):
        dlg = SettingsDialog(self, env_path=".env")
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            # refresh PRIMARY_ONLY immediately (others require restart)
            self.primary_only = os.getenv('PRIMARY_ONLY', '1') == '1'
            try:
                with open(".env","r",encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("PRIMARY_ONLY="):
                            self.primary_only = line.strip().split("=",1)[1] == "1"
                            break
            except Exception:
                pass
            QtWidgets.QMessageBox.information(self, "Settings", "Saved. Some changes require restart.")

    # ----- Error -----
    def _error(self, msg: str):
        self._set_status_idle("Error")
        QtWidgets.QMessageBox.critical(self, "Error", msg)

# -------- Main --------
def main():
    app = QtWidgets.QApplication(sys.argv)
    f = app.font(); f.setPointSize(12); app.setFont(f)
    w = MainWindow(); w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
