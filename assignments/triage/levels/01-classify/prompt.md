Build a small Python program for me. Do the whole job yourself and do not ask me any questions: every detail you need is below. If something is unclear, make a sensible choice and tell me what you chose at the end.

What to build:
- One file named main.py in the current folder. Python 3, standard library only, no network calls.
- It reads ONE support ticket as JSON from standard input. A ticket looks like this:
  {"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}
- It prints exactly ONE JSON object to standard output and nothing else (no extra text, no debug lines), like this:
  {"id": "T-100", "label": "billing"}
- "id" is copied from the ticket. "label" must be exactly one of: bug, billing, access, other.
- Do not hard-code the example. Other tickets with the same three fields (id, subject, body) will be used to check your work.

How to choose the label (use simple keyword rules, not an AI model):
- Join the subject and the body, lowercase the result, and look for keywords.
- billing: charge, charged, invoice, refund, payment, billed, billing, receipt
- access: login, log in, sign in, password, permission, locked out, access
- bug: broken, crash, error, not working, fails, wrong, bug
- If more than one group matches, prefer billing first, then access, then bug.
- If no group matches, the label is "other".

After writing main.py:
1. Test it. Save the example ticket to a file and run it with `python3 main.py < ticket.json`. Show me the output. Then invent two more tickets (a login problem and a crash) and run those too.
2. When it works, create the zip: run `zip classify.zip main.py`, or use Python's zipfile module if `zip` is not installed. main.py must be at the top of the zip, not inside a folder.
3. Tell me the full path of classify.zip.
