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

def _msg_has(header_name: str, msg) -> bool:
    v = msg.get(header_name)
    return bool(v and str(v).strip())

def _is_probably_primary(msg) -> bool:
    """
    Heuristic for Gmail 'Primary' tab using plain IMAP headers:
    - Exclude typical bulk/newsletter/automated mails.
    """
    # Hard signals of bulk/automated
    if _msg_has('List-Unsubscribe', msg):   # most newsletters/updates
        return False
    if _msg_has('List-Id', msg):            # mailing lists
        return False
    if (msg.get('Precedence', '') or '').lower() in ('bulk', 'list', 'auto_reply'):
        return False
    if (msg.get('Auto-Submitted', '') or '').lower() not in ('', 'no'):
        return False
    # Some transactional systems mark this:
    x_mailer = (msg.get('X-Mailer', '') or '').lower()
    if 'sendgrid' in x_mailer or 'mailchimp' in x_mailer or 'postmark' in x_mailer:
        return False

    # If it passed the bulk checks, treat as Primary-ish
    return True

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

    def _fetch_headers_for(self, imap, uids: List[bytes]) -> List[Tuple[bytes, email.message.Message]]:
        out = []
        for uid in uids:
            try:
                typ, d = imap.fetch(uid, '(RFC822.HEADER)')
                if typ == 'OK' and d and d[0]:
                    msg = email.message_from_bytes(d[0][1])
                    out.append((uid, msg))
            except Exception:
                continue
        return out

    def _summarize(self, pairs: List[Tuple[bytes, email.message.Message]]) -> List[Dict]:
        results: List[Dict] = []
        for i, (uid, msg) in enumerate(pairs, start=1):
            frm = _decode(msg.get('From'))
            subj = _decode(msg.get('Subject'))
            date = _decode(msg.get('Date'))
            results.append({"index": i, "uid": uid, "from": frm, "subject": subj, "date": date})
        return results

    def list_unread(self, limit: int = 10, primary_only: bool = True) -> List[Dict]:
        """
        Inbox listing with Primary-like heuristic (no X-GM-RAW dependency).

        Steps:
        1) Select INBOX.
        2) Try UNSEEN first (new mail).
        3) If primary_only=True, filter out bulk/newsletters using headers.
        4) If empty, fetch latest (SINCE 60 days) and apply same filter.
        5) If still empty, return latest (unfiltered) so the UI isn't blank.
        """
        imap = self._imap_connect()
        imap.select("INBOX")

        # --- Step 2: get unread first
        uids: List[bytes] = []
        try:
            typ, data = imap.search(None, 'UNSEEN')
            if typ == 'OK' and data and data[0]:
                uids = data[0].split()
        except Exception:
            pass

        # If no unread, get last 60 days (or ALL as fallback)
        fetched_pairs: List[Tuple[bytes, email.message.Message]] = []
        if uids:
            # newest first
            uids = list(reversed(uids))[: max(limit * 3, 40)]  # fetch a bit more for filtering headroom
            fetched_pairs = self._fetch_headers_for(imap, uids)
        else:
            try:
                since_dt = (datetime.utcnow() - timedelta(days=60)).strftime("%d-%b-%Y")
                typ, data = imap.search(None, f'(SINCE {since_dt})')
                if typ != 'OK' or not data or not data[0]:
                    typ, data = imap.search(None, 'ALL')
                if typ == 'OK' and data and data[0]:
                    uids = data[0].split()
                    uids = list(reversed(uids))[: max(limit * 3, 80)]
                    fetched_pairs = self._fetch_headers_for(imap, uids)
            except Exception:
                pass

        if not fetched_pairs:
            return []

        # --- Step 3/4: apply Primary-like filter if requested
        if primary_only:
            filtered = [(uid, msg) for (uid, msg) in fetched_pairs if _is_probably_primary(msg)]
        else:
            filtered = fetched_pairs

        # If nothing survived the filter, give back some latest messages (so user sees something)
        pairs = filtered if filtered else fetched_pairs

        # Keep newest first and cap to limit
        pairs = pairs[:limit]

        # Reindex 1..N for display order
        return self._summarize(pairs)

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

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        imap = self._imap_connect()
        imap.select("INBOX")
        typ, data = imap.search(None, f'(OR SUBJECT "{query}" FROM "{query}")')
        if typ != 'OK' or not data:
            return []
        uids = data[0].split()
        uids = list(reversed(uids))[:limit]
        pairs = self._fetch_headers_for(imap, uids)
        return self._summarize(pairs)

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
