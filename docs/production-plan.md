# Production plan

Ticket: #6. Status: revised after the owner's answers, waiting for approval to create the tickets. No code changes come with this plan.

Goal: a proof of concept that the owner can demo to executives, who test drive it by emailing `tutor@theaiguru.dev` from their own addresses, and an admin dashboard where the owner sees students, letters, and uploads assignments.

## Words

The glossary now reads (see `GLOSSARY.md`):

- **Assignment**: one course assignment, such as "Triage tickets". It is a ladder of levels. The email that opens it holds the prompt for its first level.
- **Level**: one rung of the ladder. Triage has three: 1 Classify, 2 Route, 3 Reply.
- **Ladder**: the ordered levels of one assignment.

The code still uses the old meaning. `Assignment` in `clerk.py` is really a level, `LADDER` is a tuple of levels, and the card field is `open_assignment`. Ticket 7 renames them so the code matches the glossary. The tracer plan page (`docs/tracer-plan.html`) still says "problem" and is left alone as a historical document.

## Where we are

Built and tested (62 tests), all in memory:

- The clerk (`tutor/clerk.py`): turns a letter into one reply and updates a student card. A first letter gets a welcome, the first level's prompt, step-by-step instructions, and what happens next.
- Batch grading (`tutor/grading.py`): door, room, daily cap, zone retries. The door and the room are stand-ins.
- The mail seam (`tutor/mail.py`): parses a raw letter, checks SES sandbox rules, sends a reply through SES.

Live in AWS (us-east-1):

- The MX record for `theaiguru.dev` points at SES. The domain and two Gmail addresses are verified identities.
- An SES receipt rule (`tutor-inbound`) saves every raw letter to `s3://tutor-mail-theaiguru-908196778839/raw/`.
- SES is in sandbox mode: replies reach only verified addresses.

About the reply the owner already received (the bare "Classify" prompt): it was produced by running the clerk and mail code by hand against a saved letter, which is the ticket 4 flow. It is the text from before the welcome was added. Nothing sends a reply automatically yet, and the student card lived only in that run's memory, so the next letter from the same address would not have been recognised either.

Missing, in order of how soon a student notices:

1. Nothing reads a saved letter or sends a reply on its own.
2. Student cards exist only in a Python dict. They vanish when the process ends.
3. The door and the room are fakes. Nothing real runs a student's code.
4. The assignment is a constant in `clerk.py`. The hidden tickets and the checker do not exist yet.
5. No admin view.
6. SES is in sandbox mode, so an executive's email address cannot receive a reply.

Item 6 gates the demo. See "Executive demo".

## Decision: where letters and cards live

Keep the raw letter in S3, put the student card in DynamoDB, and do not use Aurora.

| Data | Store | Why |
| --- | --- | --- |
| Raw letter (the `.eml`) | S3, already in place | SES writes it there for free. It is the immutable record: replay a letter by re-reading it. Never copy the body into a database. |
| Student card | DynamoDB, one item per email | Every access is "get or update one student by email". Conditional writes give the two guards the clerk needs: set `in_flight` only if it is false, and handle a message id only once. No server to size or patch. Pay per request, which is cents at this volume. |
| Handled message ids | DynamoDB, one small item per message id | Today the card holds a growing set of ids. A DynamoDB item caps at 400 KB, so ids move to their own items (`MSG#<id>`), written with a condition that the id does not exist. That also makes "graded once, replied once" atomic. |
| Letter and result history (for the dashboard) | DynamoDB, one item per event, key `STUDENT#<email>` / `EVENT#<timestamp>` | Cheap, ordered, and read by "show me this student's history". |
| Assignment files (instructions, rubric, checker, hidden tickets) | S3, private prefix | Files, versioned. Hidden tickets must never be readable by a student or by the student's room. |
| Assignment and level catalog | DynamoDB | Small, read on every letter, written by the admin. |
| Invited senders | DynamoDB | See "Executive demo". |

Why not Aurora Serverless:

- Our access pattern is key-value, not relational. Nothing here needs a join today.
- Aurora lives in a VPC. Lambda would need to join that VPC (or use the RDS Data API), which adds a moving part to the one function that must stay simple. The design already says "no NAT gateway".
- Aurora Serverless v2 has a minimum cost when it is awake. Newer versions can pause to zero, but a paused database takes time to resume, which a letter would feel. Verify current numbers before relying on either claim.
- The one thing that favors SQL is dashboard analytics ("pass rate per level by week"). At proof-of-concept scale a scan of a few hundred items is fine. If the dashboard outgrows that, export to S3 and query with Athena before reaching for a database.

Revisit if the admin needs ad-hoc reporting across thousands of students.

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
   -> "grader" (Step Functions): opens the door, runs rooms, deletes the door, writes results, sends replies
   -> SES (sends)

Admin -> CloudFront + S3 (dashboard page) -> API Gateway (Cognito JWT) -> Lambda "admin api" -> DynamoDB / S3
```

Notes:

- "A server with a dashboard" is built serverless: one static page plus one small API function. For a proof of concept it costs almost nothing when idle and has no host to patch. A container or EC2 server would work too but adds cost and upkeep with no benefit here.
- SQS between S3 and the clerk gives retries and a dead-letter queue. A failed send (for example the sandbox refusing an address) must leave the letter unhandled and visible, which is what `SendRefused` already promises.
- The grader is not one long Lambda. A batch holds a door plus several rooms of up to 3 minutes each, and a Lambda stops at 15 minutes. Step Functions fits: open door, map over submissions with a concurrency limit, always delete the door in a final state.
- The door must be deleted on every path, including a crashed grader. Add a scheduled sweeper that deletes any tagged endpoint older than a set age, plus an alarm. A forgotten door costs about $7.30 a month, which is small money but a clear bug.
- Infrastructure as code: AWS CDK in Python.

## Student card changes

The card gains what the dashboard needs:

- `assignment_id` and `level_index`, next to the existing `open_assignment` (renamed `open_level` in ticket 7).
- `registered_at`, `last_letter_at`.
- A `version` number for optimistic concurrency on card writes.

## Assignments move from code to data

Today the ladder is a constant. For the admin to upload an assignment, the clerk reads it from the catalog.

Assignment bundle, uploaded as one zip by the admin:

- `assignment.json`: name, and the ordered list of levels.
- One folder per level, each holding:
  - `instructions.md`: what the student receives (including how the program is run).
  - `rubric.md`: for the note writer.
  - `checker.py`: the checker, trusted code written by the admin.
  - `tickets/`: the five hidden tickets and the answer key.

The upload validates the bundle (all files present, the checker passes a known-good solution and fails a known-bad one, hidden tickets parse) before it goes live. A live assignment is versioned; a student mid-assignment keeps the version they were given.

Which assignment a new student gets: the admin marks one assignment active, and a first letter opens that assignment at level 1. Decision D1.

## Admin dashboard

Pages:

1. Students: email, assignment, level ("Triage tickets, level 2 of 3: Route"), in flight, graded tries today, last result, last letter time, finished.
2. Letters: the raw letters in S3 (sender, subject, time, attachment names, body), linked to the student and the reply sent.
3. Student detail: the event history (letters, results, replies) with a link to the raw letter.
4. Assignments: list assignments and their levels, upload a bundle, mark one active, see the live version.
5. Invited senders: add or remove email addresses and domains allowed to register.

Protection: one admin signs in through Cognito. The API validates the token. The dashboard shows personal data and accepts code that the system runs, so it is a security boundary.

## Executive demo

Executives will test drive by emailing from their own addresses. Three things have to be true.

1. SES production access. In sandbox, a reply goes only to a verified address, the mailbox simulator, or an address at a domain this account has verified. Verifying each executive's address by hand is possible (each person clicks a link) but fragile. Request production access now: it can take days, and AWS wants a description of the use, how bounces and complaints are handled, and how addresses are collected. Ticket 10 holds the work, but the request should start in parallel with ticket 8.
2. An invite list. With production access, anyone who knows the address could register and cost money (graded tries run a model). The invite list in the dashboard decides who gets a reply. A letter from someone not invited gets no grading; whether it gets a polite refusal or silence is decision D7.
3. A safe budget. An AWS Budget alarm and the existing daily cap of ten graded tries per student bound the cost of a demo.

The executives also need to read the welcome email and succeed with Claude Code or Copilot unaided. Plan one dry run with a colleague who has not seen the system before the demo.

## Tickets, in order

Each is a vertical slice that can be shown working. Branch per ticket, stacked, as in `AGENTS.md`. Numbers are assigned when the issues are created.

| # | Title | Done when |
| --- | --- | --- |
| 7 | Rename assignment to level in the clerk | The code, tests, and card field match the glossary. No change in behavior. |
| 8 | Student cards persist in DynamoDB | `receive()` runs against a DynamoDB-backed card store. The same message id twice still gives one reply. Tests use an in-memory fake of the store, plus one run against a real table. |
| 9 | A letter in S3 gets a reply without anyone running a script | S3 event, SQS, clerk Lambda, SES, all in CDK. The owner emails from Gmail and receives the welcome. Dead-letter queue and alarm included. |
| 10 | SES production access, bounces, and the invite list | Access requested and granted. Bounces and complaints go to SNS and mark an address undeliverable. DKIM and DMARC are checked. A letter from an address that is not invited is not graded. |
| 11 | Admin dashboard, read only | Cognito sign-in. The Students and Letters pages read DynamoDB and S3. |
| 12 | The assignment comes from the catalog | The levels are read from DynamoDB and S3. "Triage tickets" is seeded. The first letter's reply holds the active assignment's level 1 prompt. Same replies as today. |
| 13 | Upload an assignment from the dashboard | Validated upload, versioned, mark active, goes live without a deploy. |
| 14 | The checker and the five hidden tickets for Classify | A checker runs a sample solution and a bad solution locally and returns pass and fail with findings. Route and Reply follow in the same shape. |
| 15 | A real room | Code Interpreter on the private network runs a zip against the checker. Three-minute limit, no public internet. Any room failure is not graded. Start as a spike. |
| 16 | A real door and a batch | The interface endpoint opens, is shared, and is deleted on every path. Sweeper and alarm. |
| 17 | A submission is graded end to end | The owner emails a zip and receives pass, fail, or not graded. The model writes the note. The dashboard shows the result. |
| 18 | Demo readiness | Budget alarm, dry run with a colleague, a one-page runbook, and the invite list loaded with the executives. |

Tickets 7 to 11 make the first half of the demo real with no grading: an executive writes in and receives the welcome with the level 1 prompt, and the owner sees them on the dashboard. Tickets 14 to 17 are the largest and riskiest. If they slip, the fallback in D6 keeps a demo possible.

## Decisions

Settled by the owner:

- Assignment, level, and ladder as defined above. Triage tickets is one assignment with three levels. The first email carries the level 1 prompt.
- Infrastructure as code: AWS CDK in Python.
- Admin sign-in: Cognito.
- Batch trigger: a schedule every few minutes.
- Tests: in-memory fakes already used, plus one real-AWS smoke test per ticket, no mocking framework.
- Build the dashboard, with a view of DynamoDB and S3 data and a simple assignment upload.

Open:

- D1. How a new student gets an assignment when there are several. Proposed: the admin marks one assignment active, and a first letter opens it. After a student finishes it, the reply says they are finished, as today. Choosing among assignments can come later.
- D6. Whether grading must be the real private room for the demo. The room and door design in the tracer plan is the strongest isolation, and the heaviest to build. A lighter option is to run each zip in a locked-down container with no network, which is much less work, but the student's code could then not call the model as the tracer plan allows. Decide before ticket 15.
- D7. What a letter from a sender who is not invited receives: a short refusal or silence. Proposed: silence, because it avoids replying to spoofed addresses.
- D8. Region and account: confirm everything stays in us-east-1, account 908196778839.

## Risks

- SES production access can take days and may be denied without a clear use case. Start the request early.
- The room runs untrusted student code. The design is sound on paper, but it is the least-tested part. Treat ticket 15 as a spike first.
- The uploaded checker is code the system runs. Only the admin can upload it, so the admin sign-in is a security boundary.
- The grading batch needs hidden tickets and the answer key. Keep them out of the student-facing S3 prefix and out of the room's reach.
- Student and executive email addresses are personal data. Keep the dashboard private, and keep raw letters in a bucket with public access blocked and a retention rule.
- An executive who cannot get Claude Code or Copilot working in the first ten minutes will stop. The welcome email is the demo, so test it on a newcomer.

## Out of scope for this plan

Other channels besides email, a student-facing website, a second availability zone for the door, a model that picks the next level.
