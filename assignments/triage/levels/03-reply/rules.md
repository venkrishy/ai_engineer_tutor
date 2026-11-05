**The label.** Join the subject and the body, make it lowercase, and look for these words:

- billing: charge, charged, invoice, refund, payment, billed, billing, receipt
- access: login, log in, sign in, password, permission, locked out, access
- bug: broken, crash, error, not working, fails, wrong, bug

If more than one group matches, billing wins over access, and access wins over bug. If no group matches, the label is `other`.

**The queue.** A `bug` goes to `engineering`, `billing` goes to `billing`, and everything else (`access` and `other`) goes to `support`.

**The priority.** Look at the lowercased subject and body and check in this order:

- P1 (work is blocked or money is wrong): cannot, can't, unable, locked out, down, outage, twice, duplicate, overcharged, wrong amount
- P3 (a how-to question): how do i, how can i, how to, where is, where can i, where do i
- P2 is everything else

**The reply.** Build a short, friendly message for the customer from a template:

- It must contain the ticket id, for example `S-1`.
- It must be under 80 words. Aim for 25 to 45.
- It says which team (engineering, billing, or support) is looking at it.
- Use the word "refund" only when the customer's own subject or body contains it.
- Plain text, polite, no emojis.
