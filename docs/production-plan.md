# Production plan

Ticket: #6. Status: draft for the owner's approval. No code changes come with this plan.

## Where we are

Built and tested (62 tests), all in memory:

- The clerk (`tutor/clerk.py`): turns a letter into one reply and updates a student card.
- Batch grading (`tutor/grading.py`): door, room, daily cap, zone retries. The door and the room are stand-ins (protocols with scripted test doubles).
- The mail seam (`tutor/mail.py`): parses a raw letter, checks SES sandbox rules, sends a reply through SES.

Live in AWS (us-east-1):

- The MX record for `theaiguru.dev` points at SES. The domain and two Gmail addresses are verified identities.
- An SES receipt rule (`tutor-inbound`) saves every raw letter to `s3://tutor-mail-theaiguru-908196778839/raw/`.
- SES is in sandbox mode: replies reach only verified addresses.

Missing, in order of how soon a student notices:

1. Nothing reads a saved letter or sends a reply.
2. Student cards exist only in a Python dict. They vanish when the process ends.
3. The door and the room are fakes. Nothing real runs a student's code.
4. The ladder (Classify, Route, Reply) is a constant in `clerk.py`. The hidden tickets and the checker do not exist yet.
5. No admin view.

## Decision: where letters and cards live

Short answer: keep the raw letter in S3, put the student card in DynamoDB, and do not use Aurora.

| Data | Store | Why |
| --- | --- | --- |
| Raw letter (the `.eml`) | S3, already in place | SES writes it there for free. It is the immutable record: replay a letter by re-reading it. Never copy the body into a database. |
| Student card | DynamoDB, one item per email | Every access is "get or update one student by email". Conditional writes give us the two guards the clerk needs: set `in_flight` only if it is false, and handle a message id only once. No server to size or patch. Pay per request, which is cents at this volume. |
| Handled message ids | DynamoDB, one small item per message id | Today the card holds a growing set of ids. A DynamoDB item caps at 400 KB, so move ids to their own items (`MSG#<id>`), written with a condition that the id does not exist. That also makes "graded once, replied once" atomic. |
| Letter and result history (for the dashboard) | DynamoDB, one item per event, key `STUDENT#<email>` / `EVENT#<timestamp>` | Cheap, ordered, and read by "show me this student's history". |
| Assignment files (instructions, rubric, checker, hidden tickets) | S3, private prefix | Files, versioned. Hidden tickets must never be readable by a student or by the student's room. |
| Ladder and assignment catalog | DynamoDB | Small, read on every letter, written by the admin. |

Why not Aurora Serverless:

- Our access pattern is key-value, not relational. Nothing here needs a join today.
- Aurora lives in a VPC. Lambda would need to join that VPC (or use the RDS Data API), which adds a moving part to the one function that must stay simple. Our design already says "no NAT gateway".
- Aurora Serverless v2 has a minimum cost when it is awake. Newer versions can pause to zero, but a paused database takes time to resume, which a letter would feel. Verify the current numbers before relying on either claim.
- The one thing that favors SQL is dashboard analytics ("pass rate per assignment by week"). At proof-of-concept scale a scan of a few hundred items is fine. If the dashboard outgrows that, export to S3 and query with Athena before reaching for a database.

Revisit this decision if the admin needs ad-hoc reporting across thousands of students.

## Target architecture

```
Student's mailbox
   -> SES (receives)
   -> S3 raw/<id>            (record of the letter)
   -> SQS "letters" (+ DLQ)  (S3 event notification)
   -> Lambda "clerk"         (loads card, runs receive(), writes card, sends reply through SES)
        non-submission letter: replies now
        accepted zip: marks the letter waiting
   -> EventBridge schedule   (every few minutes)
   -> "grader" (Step Functions or Lambda): opens the door, runs rooms, deletes the door, writes results, triggers replies
   -> SES (sends)

Admin -> CloudFront + S3 (static page) -> API Gateway -> Lambda "admin api" -> DynamoDB / S3
```

Notes:

- SQS between S3 and the clerk gives retries and a dead-letter queue. A failed send (for example the sandbox refusing an address) must leave the letter unhandled and visible, which is what `SendRefused` already promises.
- The grader should not be one long Lambda. A batch holds a door plus up to N rooms of up to 3 minutes each, and a Lambda stops at 15 minutes. Step Functions fits: open door, map over submissions with a concurrency limit, always delete the door in a final state. Decide at ticket 9.
- The door must be deleted on every path, including a crashed grader. Add a scheduled sweeper that deletes any tagged endpoint older than a set age, plus an alarm. A forgotten door costs about $7.30 a month, which is small money but a clear bug.

## Student card changes

The card gains what the dashboard needs:

- `ladder_id` and `assignment_index` (the level within the ladder), next to the existing `open_assignment`.
- `registered_at`, `last_letter_at`.
- A `version` number for optimistic concurrency on card writes.

## Assignments move from code to data

Today `LADDER` is a constant. For the admin to upload an assignment, the clerk reads the ladder from the catalog.

Assignment bundle, uploaded as one zip by the admin:

- `assignment.json`: name, ladder, position, pass bar.
- `instructions.md`: what the student receives (including the how-it-runs paragraph).
- `rubric.md`: for the note writer.
- `checker.py`: the checker, trusted code written by the admin.
- `tickets/`: the five hidden tickets and answer key.

The upload validates the bundle (all files present, checker runs against a known-good solution, hidden tickets parse) before it becomes live. A live assignment is versioned; a student mid-assignment keeps the version they were given.

## Admin dashboard

Pages:

1. Students: email, ladder, current assignment and level ("Triage, level 2 of 3: Route"), in flight, graded tries today, last result, last letter time, finished.
2. Student detail: the event history (letters, results, replies) with a link to the raw letter.
3. Assignments: list ladders and their assignments, upload a bundle, see the live version.

Protection: one admin. Options are Cognito with a single user, or Cloudflare Access in front of the page (the DNS is already at Cloudflare). Recommended: Cognito, because the API then validates a token instead of trusting the network. Decision D3.

## Words

The glossary says a student walks one **ladder** of **assignments** and avoids the word "problem". The owner's examples ("the triage problem", "level 2 or 3") map to this:

- Triage = a ladder.
- Level 1, 2, 3 = Classify, Route, Reply, the assignments on that ladder.

Several ladders is new. `GLOSSARY.md` says a student has at most one open assignment and does not define more than one ladder. Decision D1 below. If it is accepted, update the glossary in the first ticket that needs it.

## Tickets, in order

Each is a vertical slice that can be shown working. Branch per ticket, stacked, as in `AGENTS.md`.

| # | Title | Done when |
| --- | --- | --- |
| 7 | Student cards persist in DynamoDB | `receive()` runs against a DynamoDB-backed card store. Same message id twice still gives one reply. Tests use a local fake of the store, plus one run against a real table. |
| 8 | A letter in S3 gets a reply without anyone running a script | S3 event -> SQS -> clerk Lambda -> SES. The owner emails from Gmail and receives the welcome. Infrastructure as code. DLQ and alarm included. |
| 9 | SES production access and bounces | Production access requested early (it takes days). Bounces and complaints go to an SNS topic and mark an address undeliverable. DKIM and DMARC are checked. |
| 10 | The ladder comes from the catalog | `LADDER` is read from DynamoDB and S3. Seed it with Classify, Route, Reply. Same replies as today. |
| 11 | The checker and the five hidden tickets for Classify | A checker runs a sample solution and a bad solution locally, giving pass and fail with findings. |
| 12 | A real room | Code Interpreter on the private network runs a zip against the checker. Three-minute limit. No public internet. Not graded on any room failure. |
| 13 | A real door and a batch | The interface endpoint opens, is shared, and is deleted on every path. Sweeper and alarm. |
| 14 | A submission is graded end to end | The owner emails a zip, receives pass, fail, or not graded. The note is written by the model. |
| 15 | Admin API and students page | Read-only students list with ladder and level. Protected. |
| 16 | Student detail and history | Event history per student. |
| 17 | Upload an assignment bundle | Validated upload, versioned, goes live. |

Tickets 7 to 9 come first because they make the welcome flow real with no grading. Tickets 11 to 14 are the largest and riskiest, and nothing in 15 to 17 depends on them except showing real data.

## Decisions the owner needs to make

- D1. Several ladders. Is "triage" one ladder among several, with the student choosing or being assigned one, or is there one ladder for now and "problems" is a future word for ladders? Affects the card, the glossary, and ticket 10.
- D2. Infrastructure as code tool. Recommended: AWS CDK in Python, since the existing `ai-stories-*` stacks look like CDK and the code here is Python. Alternatives: Terraform, SAM. Pick one before ticket 8.
- D3. Admin sign-in: Cognito (recommended) or Cloudflare Access.
- D4. Batch trigger: a schedule every few minutes (simple, recommended) or a letter-count threshold.
- D5. Tests. The project convention is to ask how tests should be written. Proposed: keep the in-memory fakes already used, add one real-AWS smoke test per ticket, no mocking framework.
- D6. Region and account: confirm everything stays in us-east-1 in account 908196778839.

## Risks

- SES production access can take days and may be denied without a clear sending use case. Request it in ticket 9, or earlier in parallel with ticket 7.
- The room runs untrusted student code. The design (private network, no internet, three-minute limit, model key placed by us) is sound on paper, but it is the least-tested part. Treat ticket 12 as a spike first.
- The uploaded checker is code the system runs. Only the admin can upload it, so the admin sign-in is a security boundary, not a convenience.
- The grading batch needs hidden tickets and the answer key. Keep them out of the student-facing S3 prefix and out of the room's reach.
- Student email addresses are personal data. Keep the dashboard private, and keep raw letters in a bucket with public access blocked and a retention rule.

## Out of scope for this plan

Other channels besides email, a student-facing website, a second availability zone for the door, a model that picks the next assignment. These match the tracer plan.
