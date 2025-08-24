import imaplib, smtplib, ssl, email, re
from email.message import EmailMessage
from typing import List, Dict, Tuple
from email.header import decode_header, make_header
from datetime import datetime, timedelta

def _decode(h):
    if not h:
        return ""
    try:
        return str(make_header(decode_header(h)))
    except Exception:
        return h

class EmailClient:
    def __init__(self, imap_host: str, imap_port: int, smtp_host: str, smtp_port: int, user: str, password: str):
        self.imap_host = imap_host
        self.imap_port = int(imap_port)
        self.smtp_host = smtp_host
        self.smtp_port = int(smtp_port)
        self.user = user
        self.password = password
        self._imap = None

    # ---------- IMAP ----------
    def _imap_connect(self):
        if self._imap is None:
            self._imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            self._imap.login(self.user, self.password)
        return self._imap

    def list_unread(self, limit: int = 5) -> List[Dict]:
        """
        Robust 'check inbox':
        A) First try standard IMAP UNSEEN (works on all providers)
        B) If empty, try Gmail extensions for Inbox/Primary unread
        C) If still empty, fall back to latest INBOX messages (read or unread)

        This ordering fixes cases where Gmail's X-GM-RAW parsing returns zero.
        """
        imap = self._imap_connect()
        imap.select("INBOX")

        uids: List[bytes] = []

        # --- A) Standard UNSEEN (most reliable) ---
        try:
            typ, data = imap.search(None, 'UNSEEN')
            if typ == 'OK' and data and data[0]:
                uids = data[0].split()
        except Exception:
            pass

        # --- B) Gmail-specific filters if still empty ---
        if not uids:
            try:
                # Option 1: strictly Primary category
                typ1, d1 = imap.uid('SEARCH', 'X-GM-RAW', '"category:primary is:unread"')
                if typ1 == 'OK' and d1 and d1[0]:
                    uids = d1[0].split()
                else:
                    # Option 2: Inbox unread
                    typ2, d2 = imap.uid('SEARCH', 'X-GM-RAW', '"in:inbox is:unread"')
                    if typ2 == 'OK' and d2 and d2[0]:
                        uids = d2[0].split()
            except Exception:
                pass

        # --- C) Still nothing? Fall back to the latest messages (read or unread) ---
        if not uids:
            try:
                # Consider the last 30 days only, to keep results relevant
                since_dt = (datetime.utcnow() - timedelta(days=30)).strftime("%d-%b-%Y")
                # Many servers support SINCE; if not, we’ll fall back to ALL
                typ, data = imap.search(None, f'(SINCE {since_dt})')
                if typ != 'OK' or not data or not data[0]:
                    typ, data = imap.search(None, 'ALL')
                if typ == 'OK' and data and data[0]:
                    uids = data[0].split()
            except Exception:
                pass

        if not uids:
            return []

        # Trim to limit and build summaries
        uids = uids[-limit:] if limit else uids
        results: List[Dict] = []
        for i, uid in enumerate(reversed(uids), start=1):
            try:
                typ, d = imap.fetch(uid, '(RFC822.HEADER)')
                if typ != 'OK' or not d or not d[0]:
                    continue
                msg = email.message_from_bytes(d[0][1])
                frm = _decode(msg.get('From'))
                subj = _decode(msg.get('Subject'))
                date = _decode(msg.get('Date'))
                results.append({"index": i, "uid": uid, "from": frm, "subject": subj, "date": date})
            except Exception:
                continue
        return results

    def fetch_message(self, uid_bytes) -> Tuple[str, str, str]:
        imap = self._imap_connect()
        typ, d = imap.fetch(uid_bytes, '(RFC822)')
        if typ != 'OK' or not d or not d[0]:
            return ("", "", "")
        msg = email.message_from_bytes(d[0][1])
        frm = _decode(msg.get('From'))
        subj = _decode(msg.get('Subject'))
        body = self._extract_body(msg)
        return (frm, subj, body)

    def mark_seen(self, uid_bytes):
        imap = self._imap_connect()
        imap.store(uid_bytes, '+FLAGS', '\\Seen')

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        imap = self._imap_connect()
        imap.select("INBOX")
        # Simple OR search across Subject and From
        typ, data = imap.search(None, f'(OR SUBJECT "{query}" FROM "{query}")')
        if typ != 'OK' or not data:
            return []
        uids = data[0].split()
        uids = uids[-limit:] if limit else uids
        results = []
        for i, uid in enumerate(reversed(uids), start=1):
            typ, d = imap.fetch(uid, '(RFC822.HEADER)')
            if typ != 'OK' or not d or not d[0]:
                continue
            msg = email.message_from_bytes(d[0][1])
            frm = _decode(msg.get('From'))
            subj = _decode(msg.get('Subject'))
            date = _decode(msg.get('Date'))
            results.append({"index": i, "uid": uid, "from": frm, "subject": subj, "date": date})
        return results

    def _extract_body(self, msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get("Content-Disposition"))
                if ctype == 'text/plain' and 'attachment' not in disp:
                    try:
                        return part.get_payload(decode=True).decode(errors='ignore')
                    except Exception:
                        continue
            # fallback to first text/html stripped
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == 'text/html':
                    try:
                        html = part.get_payload(decode=True).decode(errors='ignore')
                        return self._html_to_text(html)
                    except Exception:
                        continue
        else:
            try:
                if msg.get_content_type() == 'text/plain':
                    return msg.get_payload(decode=True).decode(errors='ignore')
                elif msg.get_content_type() == 'text/html':
                    return self._html_to_text(msg.get_payload(decode=True).decode(errors='ignore'))
            except Exception:
                pass
        return "(no readable body)"

    def _html_to_text(self, html: str) -> str:
        # very basic HTML tag remover
        return re.sub('<[^<]+?>', '', html)

    # ---------- SMTP ----------
    def send(self, to_email: str, subject: str, body: str):
        msg = EmailMessage()
        msg["From"] = self.user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context) as server:
            server.login(self.user, self.password)
            server.send_message(msg)
