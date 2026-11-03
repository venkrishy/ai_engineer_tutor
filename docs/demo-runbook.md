# Demo runbook

## Before the day

1. Deploy: `cd infra && bunx aws-cdk@latest deploy`. Review the diff it prints first.
2. Load the assignment: `python3 scripts/upload_assignment.py assignments/triage`. The hidden
   tickets (`levels/*/tickets.json`) are not in git. Keep them on this machine.
3. Open the dashboard. Its URL is the `AdminUrl` output of the stack. The password is in Secrets
   Manager under the name in the `AdminPasswordSecret` output:
   `aws secretsmanager get-secret-value --secret-id <name> --query SecretString --output text`
4. While SES is in sandbox, verify each executive's address. They get an email from AWS and must
   click the link before any reply can reach them:
   `aws sesv2 create-email-identity --region us-east-1 --email-identity name@company.com`
   Production access removes this step: see `docs/ses-production-access.md`.
5. Dry run with someone who has not seen the system. They email `tutor@theaiguru.dev`, follow the
   welcome, and send back a zip. Then press "Reset this student" on the dashboard.
6. Confirm the budget alert reaches your inbox (the stack subscribes your address; accept the
   AWS confirmation email once).

## Limits that protect the demo

- Five graded tries per student per UTC day, 100 across everyone. At the cap the reply is "Cap hit".
- Settings, "Pause registration": new addresses get no reply while it is on.
- A $50 monthly budget alert at 80 percent.

## During

- Students: who registered, which assignment and level, last result.
- Letters: the raw mail with the SES spam, virus checks.
- A student who is stuck: open them for the history of every letter and reply.

## If something is wrong

- No reply at all: the Lambda log group for the clerk, and the dead-letter queue alarm email.
  A send to an unverified address is refused and the letter can be tried again after you verify it.
- "Not graded": the room failed. Nothing was spent. Ask the student to send the zip again.
- Redo a student's first experience: Students, open them, Reset this student.
