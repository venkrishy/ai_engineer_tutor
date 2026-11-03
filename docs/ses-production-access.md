# SES production access

While the account is in sandbox mode, a reply goes only to a verified address, the mailbox simulator, or an address at a domain this account has verified. Production access removes that limit. The request is reviewed by AWS and can take about a day or longer. It can be denied, in which case reply to the case with more detail.

Check the current state:

    aws sesv2 get-account --region us-east-1 --query '{prod:ProductionAccessEnabled,sending:SendingEnabled,quota:SendQuota}'

## Before you ask

- The sending domain `theaiguru.dev` is a verified identity with DKIM enabled.
- Bounces and complaints are published to the SNS topic wired in `infra/tutor_stack.py` through the `tutor` configuration set. SES keeps its own suppression list for bounces and complaints, and that is on.
- The clerk replies only to letters that passed the SES spam and virus checks and whose sender passed DMARC or a matching DKIM signature. It never mails an address that did not write first.
- Registration can be paused from the dashboard, and each student has five graded tries a day with 100 across all students.

## Request it in the console

SES, Account dashboard, Request production access. Use these answers.

- Mail type: Transactional.
- Website URL: the page that describes the course. If there is none yet, use the project repository, https://github.com/venkrishy/ai_engineer_tutor.
- Use case description:

  > AI Engineers Course. A person emails tutor@theaiguru.dev. We reply on the same thread, once per email they send: a welcome and their first coding assignment, and later the result of the code they send back (pass or fail with notes) and the next assignment. We never send unsolicited or bulk mail and we only reply to an address that wrote to us first. Expected volume is under 500 emails a day. Replies are sent only to letters that passed SES spam, virus, SPF/DKIM/DMARC checks. Bounces and complaints are published to an SNS topic and SES account-level suppression is on; an address that bounces or complains is never mailed again.

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
