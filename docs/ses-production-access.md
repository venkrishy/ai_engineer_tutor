# SES production access

While the account is in sandbox mode, a reply goes only to a verified address, the mailbox simulator, or an address at a domain this account has verified. Production access removes that limit. The request is reviewed by AWS and can take about a day or longer. It can be denied, in which case reply to the case with more detail.

Check the current state, and everything AWS reviewers care about, in one go:

    python3 scripts/ses_preflight.py

It is read-only. It needs `boto3` and credentials for the account. Every line should say `PASS` except the first one, which stays `FAIL` until the sandbox is lifted. A `FAIL` line says what to fix.

## Before you ask

1. Deploy the stack so the configuration set, the IAM scope and the alarms match this repo:

       cd infra && bunx aws-cdk@latest deploy

   The `tutor` configuration set has reputation metrics and bounce and complaint suppression on, and publishes bounces, complaints and rejects to the alerts topic. The clerk may send only as `theaiguru.dev` or `tutor@theaiguru.dev` and only through that configuration set. Two alarms email you when the account bounce rate reaches 3% or the complaint rate reaches 0.05%. AWS puts an account under review at 5% and 0.1%, and pauses it at 10% and 0.5%.

2. Run the preflight. The sending domain `theaiguru.dev` must be a verified identity with DKIM signing and a verified MAIL FROM domain (`bounce.theaiguru.dev`). The account-level suppression list must cover bounces and complaints. These are not in CDK because the identity already exists and its DNS lives at Cloudflare.

3. Check the DNS that SES cannot see. The DKIM CNAME records at Cloudflare must be DNS only (grey cloud), not proxied.

       dig +short TXT _dmarc.theaiguru.dev
       dig +short MX bounce.theaiguru.dev
       dig +short TXT bounce.theaiguru.dev

   Publish a DMARC record if the first command prints nothing. Start with `v=DMARC1; p=none; rua=mailto:you@example.com` and move to `p=quarantine` after a few weeks of clean reports. The MAIL FROM host should answer with an MX at `feedback-smtp.us-east-1.amazonses.com` and an SPF TXT of `v=spf1 include:amazonses.com ~all`.

4. Know what the app already does, because the request describes it:
   - The clerk replies only to letters that passed the SES spam and virus checks and whose sender passed DMARC or a matching DKIM signature. It never mails an address that did not write first.
   - Registration can be paused from the dashboard, and each student has five graded tries a day with 100 across all students.

## Request it in the console

SES, Account dashboard, Request production access. Use these answers.

- Mail type: Transactional.
- Website URL: the page that describes the course. If there is none yet, use the project repository, https://github.com/venkrishy/ai_engineer_tutor.
- Use case description:

  > AI Engineers Course. A person emails tutor@theaiguru.dev, so every conversation starts with the recipient writing to us. We reply on the same thread to each email they send: a welcome and their first coding assignment, and later the result of the code they send back (pass or fail with notes) and the next assignment. We never send unsolicited, marketing or bulk mail, we never use purchased or third-party lists, and we never mail an address that did not write to us first. A person who wants no more mail stops writing. Expected volume is under 500 emails a day. Replies are sent only to letters that passed SES spam, virus, SPF/DKIM/DMARC checks, and registration can be paused at any time. Mail is signed with DKIM from a verified domain with a custom MAIL FROM domain. Bounces and complaints are published to an SNS topic that alerts the owner, account-level suppression is on for both, and CloudWatch alarms on the account bounce and complaint rates fire at 3% and 0.05%. An address that bounces or complains is never mailed again.

- Additional contact addresses: your own address.
- Acknowledge that you will send only to recipients who requested it.

## Or from the command line

    aws sesv2 put-account-details --region us-east-1 \
      --production-access-enabled \
      --mail-type TRANSACTIONAL \
      --website-url https://github.com/venkrishy/ai_engineer_tutor \
      --use-case-description "<the description above>" \
      --additional-contact-email-addresses you@example.com

## Until it is granted

Verify each demo recipient as an identity. SES emails them a link, and they must click it before any reply can reach them:

    aws sesv2 create-email-identity --region us-east-1 --email-identity someone@example.com

## When it is granted

1. Run `python3 scripts/ses_preflight.py`. Every line should say `PASS`. The first line shows the daily quota AWS set. If it is below your expected volume, ask for more under Service Quotas.
2. Email `tutor@theaiguru.dev` from an address that is not an SES identity, and confirm the reply arrives. That is the one thing the sandbox used to block.
3. Remove the sandbox wording: the note at the bottom of `README.md`, the first slide in `docs/deck.html`, step 4 of `docs/demo-runbook.md`, and the sandbox lines in `docs/production-plan.md` and `docs/tracer-plan.html`.
4. Watch the two SES alarms for the first week. If one fires, check the bounce and complaint events in the alerts email before sending more.
