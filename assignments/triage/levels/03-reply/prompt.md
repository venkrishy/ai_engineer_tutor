Build a small Python program for me. Do the whole job yourself and do not ask me any questions: every detail you need is below. If something is unclear, make a sensible choice and tell me what you chose at the end.

What to build:
- One file named main.py in the current folder. Python 3, standard library only, no network calls.
- It reads ONE support ticket as JSON from standard input. A ticket looks like this:
  {"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}
- It prints exactly ONE JSON object to standard output and nothing else (no extra text, no debug lines), like this:
  {"id": "T-100", "label": "billing", "priority": "P1", "queue": "billing", "reply": "Hi, thanks for contacting us about T-100. Our billing team is looking into the duplicate payment and will follow up soon."}
- "id" is copied from the ticket. "label" is one of: bug, billing, access, other. "priority" is one of: P1, P2, P3. "queue" is one of: engineering, billing, support. "reply" is a short, friendly message to the customer.
- Do not hard-code the example. Other tickets with the same three fields (id, subject, body) will be used to check your work.

How to choose the label (use simple keyword rules, not an AI model):
- Join the subject and the body, lowercase the result, and look for keywords.
- billing: charge, charged, invoice, refund, payment, billed, billing, receipt
- access: login, log in, sign in, password, permission, locked out, access
- bug: broken, crash, error, not working, fails, wrong, bug
- If more than one group matches, prefer billing first, then access, then bug.
- If no group matches, the label is "other".

How to choose the queue: bug goes to engineering, billing goes to billing, everything else (access and other) goes to support.

How to choose the priority (use simple keyword rules on the lowercased subject and body, checked in this order):
- P1 means work is blocked or money is wrong: cannot, can't, unable, locked out, down, outage, twice, duplicate, overcharged, wrong amount.
- P3 means a how-to question: how do i, how can i, how to, where is, where can i, where do i.
- P2 is everything else.

How to write the reply (build it from a template, no AI model):
- It must contain the ticket id (for example T-100).
- It must be under 80 words. Aim for 25 to 45.
- Say which team (engineering, billing, or support) is looking at it.
- Use the word "refund" only when the customer's own subject or body contains the word "refund". Otherwise never write that word.
- Plain text, polite, no emojis.

After writing main.py:
1. Test it. Save the example ticket to a file and run it with `python3 main.py < ticket.json`. Show me the output. Then invent two more tickets (a login problem and a crash) and run those too.
2. When it works, create the zip: run `zip reply.zip main.py`, or use Python's zipfile module if `zip` is not installed. main.py must be at the top of the zip, not inside a folder.
3. Tell me the full path of reply.zip.
