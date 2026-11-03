Read one ticket as JSON and print one JSON object with the ticket id and a label: bug, billing, access, or other.

Your program is main.py. The grader runs it once per ticket with `python3 main.py`, sends the ticket as JSON on standard input, and reads standard output. Print exactly one JSON object and nothing else.

Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.

Sample ticket:
{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}
