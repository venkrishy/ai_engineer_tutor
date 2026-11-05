# Production plan

Ticket: #6. Status: approved, tickets #7 to #17 created. No code changes come with this plan.

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

Branch per ticket, stacked, as in `AGENTS.md`.

| Issue | Title |
| --- | --- |
| #7 | Rename assignment to level in the clerk |
| #8 | Student cards persist in DynamoDB |
| #9 | A letter in S3 gets a reply without anyone running a script |
| #10 | Anyone who writes in is registered and welcomed, safely |
| #11 | Admin dashboard, read only |
| #12 | The assignment comes from the catalog |
| #13 | Upload an assignment from the dashboard |
| #14 | The checker and hidden tickets for Triage tickets |
| #15 | A room runs a student's zip in AgentCore Code Interpreter |
| #16 | A submission is graded end to end with a Bedrock note |
| #17 | Demo readiness |

## Decisions

Settled by the owner:

- Everything stays on AWS (Cloudflare holds only DNS). The owner wants practice with AgentCore and has AWS credits to spend on Bedrock.
- Assignment, level, and ladder as defined above. Assignments follow a fixed, predefined order, each with a fixed ladder of levels. The assignment id travels in the subject, like `[triage] Classify`, and the student card stays the source of truth.
- AWS CDK in Python, Cognito for admin sign-in, tests with in-memory fakes plus one real-AWS check per ticket, no mocking framework.
- Isolation: the lightest that works. A room is an AgentCore Code Interpreter session. A spike showed it runs `python3 main.py` with the ticket on stdin and has no internet (DNS fails). The private door and the VPC are dropped. The student program does not call the model. The checker runs outside the session, so the answer key never enters it.
- The model writes the note through Bedrock with a cross-region inference profile (`us.anthropic.claude-sonnet-4-6`).
- Anyone who writes in is registered and gets the welcome. The invite list is dropped. Safeguards instead: reply only when the letter passed SES spam, virus, SPF and DKIM checks; a global daily cap on graded tries; a pause-registration switch.
- Sandbox for now: the demo recipients are verified SES identities. Production access is requested later, see `docs/ses-production-access.md` (ticket #10).
- Batch trigger: with no door to open, a letter is graded as it arrives. The batch logic stays and runs with a no-op door.

## Risks

- SES production access can take days and may be denied without a clear use case. Start the request early.
- The room runs untrusted student code. The design is sound on paper, but it is the least-tested part. Treat ticket 15 as a spike first.
- The uploaded checker is code the system runs. Only the admin can upload it, so the admin sign-in is a security boundary.
- The grading batch needs hidden tickets and the answer key. Keep them out of the student-facing S3 prefix and out of the room's reach.
- Student and executive email addresses are personal data. Keep the dashboard private, and keep raw letters in a bucket with public access blocked and a retention rule.
- An executive who cannot get Claude Code or Copilot working in the first ten minutes will stop. The welcome email is the demo, so test it on a newcomer.

## Out of scope for this plan

Other channels besides email, a student-facing website, a second availability zone for the door, a model that picks the next level.
