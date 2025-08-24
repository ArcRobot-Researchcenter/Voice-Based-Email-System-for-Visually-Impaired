import os, re, sys, difflib, csv
from typing import List, Dict
from dotenv import load_dotenv

from voice_io import VoiceIO
from email_client import EmailClient

# -------- Helpers --------
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

def summarize_list(items: List[Dict]) -> str:
    lines = []
    for it in items:
        who = it['from']
        subj = it['subject'] or '(no subject)'
        lines.append(f"{it['index']}. {who} — {subj}")
    return " | ".join(lines) if lines else "No messages found."

def extract_index(text: str) -> int:
    """Return a 1-based index from text like 'read 2', 'read number two', 'second', or just 'two'."""
    t = (text or "").lower().strip()
    # 1) any digits anywhere
    m = re.search(r"(\d+)", t)
    if m:
        try:
            return int(m.group(1))
        except:
            pass
    # 2) ordinals
    for w, n in ORDINAL_NUM.items():
        if re.search(rf"\b{w}\b", t):
            return n
    # 3) cardinals
    for w, n in WORD_NUM.items():
        if re.search(rf"\b{w}\b", t):
            return n
    return -1

def hear_or_retry(v: VoiceIO, prompt: str, retries: int = 2) -> str:
    for i in range(retries + 1):
        txt = v.listen(prompt if i == 0 else "Sorry, I didn't catch that. " + prompt)
        if txt:
            return txt
    v.speak("I couldn't hear you. Cancelled.")
    return ""

def confirm(v: VoiceIO, phrase: str) -> bool:
    ans = hear_or_retry(v, phrase + " Say yes or no.")
    if not ans: 
        return False
    ans = ans.lower().strip()
    return 'yes' in ans or ans == 'y'

# -------- Main App --------
def main():
    load_dotenv()
    use_mic = os.getenv('USE_MIC', '1') == '1'
    tts_rate = int(os.getenv('TTS_RATE', '180'))
    stt_lang = os.getenv('STT_LANG', 'en-US')

    v = VoiceIO(use_mic=use_mic, tts_rate=tts_rate, stt_lang=stt_lang)

    imap_host = os.getenv('IMAP_HOST', 'imap.gmail.com')
    imap_port = int(os.getenv('IMAP_PORT', '993'))
    smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '465'))
    user = os.getenv('EMAIL_USER')
    pw = os.getenv('EMAIL_PASS')

    if not user or not pw:
        v.speak("Email credentials missing. Please create a .env file. Exiting.")
        print("Missing EMAIL_USER or EMAIL_PASS in .env")
        sys.exit(1)

    mail = EmailClient(imap_host, imap_port, smtp_host, smtp_port, user, pw)
    contacts = load_contacts()

    v.speak("Welcome to your voice email. Say a command: check inbox, compose, search, help, or quit.")

    cache = { 'list': [], 'map': {} }  # index->uid

    while True:
        cmd = v.listen()
        cmd = (cmd or "").lower().strip()

        if not cmd:
            v.speak("I didn't catch that. Say help for options.")
            continue

        # ---- HELP ----
        if 'help' in cmd or 'what can' in cmd:
            v.speak("Commands are: check inbox, read number N, read next, compose, search for WORDS, reply, mark as read, or quit.")
            continue

        # ---- QUIT ----
        if 'quit' in cmd or 'exit' in cmd or 'close' in cmd:
            v.speak("Goodbye.")
            break

        # ---- CHECK INBOX ----
        if 'check inbox' in cmd or 'check my inbox' in cmd or 'unread' in cmd:
            msgs = mail.list_unread(limit=10)
            cache['list'] = msgs
            cache['map'] = { it['index']: it['uid'] for it in msgs }

            if not msgs:
                v.speak("I didn't find any messages in your Inbox. You can say 'compose' to send a new email or 'search for ...'.")
                continue

            v.speak(f"I found {len(msgs)} messages. Say 'read number 1' or just say the number.")
            v.speak(summarize_list(msgs))
            continue

        # ---- DIRECT NUMBER after listing (e.g., just "one", "first") ----
        if cache['list']:
            # If user just says a number/ordinal without "read"
            idx_only = extract_index(cmd)
            if idx_only != -1 and ('read' not in cmd and 'open' not in cmd):
                cmd = f"read number {idx_only}"

        # ---- READ NUMBER N ----
        if 'read number' in cmd or 'read message' in cmd or 'open number' in cmd or re.search(r"\bread\s+\d+\b", cmd):
            if not cache['list']:
                v.speak("No list yet. Say 'check inbox' or 'search' first.")
                continue
            n = extract_index(cmd)
            if n == -1:
                v.speak("Please say the message number, like 'read number two' or 'read number 2'.")
                continue
            uid = cache['map'].get(n)
            if not uid:
                v.speak("That number isn't in the current list. Say 'check inbox' or 'search' first.")
                continue
            frm, subj, body = mail.fetch_message(uid)
            v.speak(f"From {frm}. Subject: {subj or 'no subject'}. Here is the message:")
            v.speak((body or "(no readable body)")[:1200])
            if confirm(v, "Mark this as read?"):
                mail.mark_seen(uid)
                v.speak("Marked as read.")
            continue

        # ---- READ NEXT ----
        if 'read next' in cmd or cmd.strip() == 'next':
            if not cache['list']:
                v.speak("No list yet. Say check inbox first.")
                continue
            it = cache['list'].pop(0)
            uid = it['uid']
            frm, subj, body = mail.fetch_message(uid)
            v.speak(f"From {frm}. Subject: {subj or 'no subject'}. Here is the message:")
            v.speak((body or "(no readable body)")[:1200])
            if confirm(v, "Mark this as read?"):
                mail.mark_seen(uid)
                v.speak("Marked as read.")
            continue

        # ---- SEARCH ----
        if 'search for' in cmd or cmd.startswith('search '):
            q = cmd.split('search', 1)[1].replace('for', '').strip()
            if not q:
                v.speak("Say search for, then a keyword.")
                continue
            msgs = mail.search(q, limit=10)
            cache['list'] = msgs
            cache['map'] = { it['index']: it['uid'] for it in msgs }

            if not msgs:
                v.speak(f"I didn't find any messages for '{q}'.")
                continue

            v.speak(f"Search found {len(msgs)} messages. Say 'read number 1' or just say the number.")
            v.speak(summarize_list(msgs))
            continue

        # ---- COMPOSE ----
        if 'compose' in cmd or 'new email' in cmd or 'send email' in cmd:
            who = hear_or_retry(v, "Who do you want to email? You can say a name in your contacts or spell an address.")
            if not who:
                continue
            to_email = ''
            if '@' in who:
                to_email = who.replace(' at ', '@').replace(' dot ', '.').replace(' ', '')
            else:
                to_email = resolve_contact(who, contacts)
            if not to_email:
                to_email = hear_or_retry(v, "I could not find that contact. Please say or type the email address.")
                if not to_email:
                    continue
                to_email = to_email.replace(' at ', '@').replace(' dot ', '.').replace(' ', '')
            if '@' not in to_email:
                to_email = hear_or_retry(v, "I need a full email address. Please say it, like alex at gmail dot com.")
                if not to_email:
                    continue
                to_email = to_email.replace(' at ', '@').replace(' dot ', '.').replace(' ', '')
                if '@' not in to_email:
                    v.speak("Still not a valid email. Cancelled.")
                    continue

            subject = hear_or_retry(v, "What is the subject?")
            if not subject: subject = "(no subject)"
            v.speak(f"You said subject: {subject}.")

            v.speak("Speak your message. Say 'stop message' when you are done.")
            body_lines = []
            while True:
                line = v.listen()
                if not line:
                    continue
                if 'stop message' in line.lower() or 'full stop' in line.lower():
                    break
                body_lines.append(line)
            body = "\n".join(body_lines)
            v.speak("Here is your message:")
            v.speak(body[:1000])
            if confirm(v, f"Send to {to_email}?"):
                try:
                    mail.send(to_email, subject, body)
                    v.speak("Sent.")
                except Exception as e:
                    v.speak("Sending failed. Check your SMTP settings.")
                    print(e)
            else:
                v.speak("Cancelled.")
            continue

        # ---- MARK AS READ ----
        if 'mark as read' in cmd:
            if not cache['list']:
                v.speak("No current message to mark. Say read number N first.")
                continue
            uid = cache['list'][0]['uid']
            try:
                mail.mark_seen(uid)
                v.speak("Marked as read.")
            except Exception:
                v.speak("Could not mark as read.")
            continue

        # ---- REPLY ----
        if 'reply' in cmd:
            if not cache['list']:
                v.speak("No message selected. Say read number N first.")
                continue
            uid = cache['list'][0]['uid']
            frm, subj, _ = mail.fetch_message(uid)
            m = re.search(r"<([^>]+)>", frm)
            to_email = m.group(1) if m else frm.split()[-1]
            if '@' not in to_email:
                v.speak("I couldn't detect a reply address. Cancelled.")
                continue
            v.speak(f"Replying to {to_email}. Speak your message; say stop message when done.")
            lines = []
            while True:
                line = v.listen()
                if not line:
                    continue
                if 'stop message' in line.lower():
                    break
                lines.append(line)
            body = "\n".join(lines)
            subject = "Re: " + (subj or "(no subject)")
            if confirm(v, f"Send reply to {to_email}?"):
                try:
                    mail.send(to_email, subject, body)
                    v.speak("Reply sent.")
                except Exception as e:
                    v.speak("Sending failed.")
                    print(e)
            else:
                v.speak("Cancelled.")
            continue

        # ---- UNKNOWN ----
        v.speak("Sorry, I don't know that command yet. Say help to hear options.")

if __name__ == '__main__':
    main()
