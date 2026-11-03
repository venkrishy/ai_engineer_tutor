Read one ticket as JSON and print one JSON object with the ticket id, a label (bug, billing, access, or other), a priority (P1, P2, P3), a queue, and a short customer reply.

Your program is main.py. The grader runs it once per ticket with `python3 main.py`, sends the ticket as JSON on standard input, and reads standard output. Print exactly one JSON object and nothing else.

Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.

Bugs go to engineering, billing goes to billing, and the rest go to support. P1 means work is blocked or money is wrong. P3 is a how-to. P2 is the rest.

The customer reply must contain the ticket id, stay under 80 words, and say "refund" only when the ticket does.

Sample ticket:
{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}
