"""Read-only check that SES is ready to send to real people: python3 scripts/ses_preflight.py

Needs boto3 and AWS credentials that can call ses:GetAccount, ses:GetEmailIdentity and
ses:GetConfigurationSet*. It changes nothing. Exit code 1 means something needs attention."""

from __future__ import annotations

import sys

REGION = "us-east-1"
DOMAIN = "theaiguru.dev"
CONFIGURATION_SET = "tutor"


def _missing(error: Exception) -> bool:
    return getattr(error, "response", {}).get("Error", {}).get("Code") == "NotFoundException"


def check(client, domain: str = DOMAIN, configuration_set: str = CONFIGURATION_SET) -> list[tuple[str, bool, str]]:
    """Each result is (what was checked, passed, what to do or what was found)."""
    results: list[tuple[str, bool, str]] = []

    def add(name: str, ok, detail: str) -> None:
        results.append((name, bool(ok), detail))

    account = client.get_account()
    quota = account.get("SendQuota") or {}
    add(
        "out of the sandbox",
        account.get("ProductionAccessEnabled"),
        f"daily quota {quota.get('Max24HourSend')}, {quota.get('MaxSendRate')}/second"
        if account.get("ProductionAccessEnabled")
        else "still in the sandbox: request it, see docs/ses-production-access.md",
    )
    add("account can send", account.get("SendingEnabled"), "sending is paused for this account")
    health = account.get("EnforcementStatus") or "unknown"
    add("account health", health == "HEALTHY", f"enforcement status is {health}")
    reasons = set((account.get("SuppressionAttributes") or {}).get("SuppressedReasons") or [])
    add(
        "account suppression list",
        {"BOUNCE", "COMPLAINT"} <= reasons,
        f"covers {sorted(reasons) or 'nothing'}, it must cover BOUNCE and COMPLAINT",
    )

    try:
        identity = client.get_email_identity(EmailIdentity=domain)
    except Exception as error:
        if not _missing(error):
            raise
        add("domain identity", False, f"{domain} is not an identity in this account")
    else:
        add("domain identity", identity.get("VerifiedForSendingStatus"), f"{domain} is not verified for sending")
        dkim = identity.get("DkimAttributes") or {}
        add(
            "DKIM signing",
            dkim.get("Status") == "SUCCESS" and dkim.get("SigningEnabled"),
            f"DKIM status is {dkim.get('Status')}, signing enabled is {dkim.get('SigningEnabled')}",
        )
        mail_from = identity.get("MailFromAttributes") or {}
        add(
            "custom MAIL FROM",
            bool(mail_from.get("MailFromDomain")) and mail_from.get("MailFromDomainStatus") == "SUCCESS",
            "set a MAIL FROM domain and publish its MX and SPF records so SPF aligns with DMARC"
            if not mail_from.get("MailFromDomain")
            else f"{mail_from.get('MailFromDomain')} is {mail_from.get('MailFromDomainStatus')}",
        )

    try:
        settings = client.get_configuration_set(ConfigurationSetName=configuration_set)
    except Exception as error:
        if not _missing(error):
            raise
        add("configuration set", False, f"{configuration_set} does not exist: deploy infra/")
    else:
        add("configuration set sends", (settings.get("SendingOptions") or {}).get("SendingEnabled"), "sending is off")
        add(
            "reputation metrics",
            (settings.get("ReputationOptions") or {}).get("ReputationMetricsEnabled"),
            "turn on reputation metrics: deploy infra/",
        )
        suppressed = set((settings.get("SuppressionOptions") or {}).get("SuppressedReasons") or [])
        add(
            "configuration set suppression",
            {"BOUNCE", "COMPLAINT"} <= suppressed,
            f"covers {sorted(suppressed) or 'nothing'}: deploy infra/",
        )
        destinations = client.get_configuration_set_event_destinations(ConfigurationSetName=configuration_set)
        feeds = [
            item
            for item in destinations.get("EventDestinations") or []
            if item.get("Enabled")
            and "SnsDestination" in item
            and {"BOUNCE", "COMPLAINT"} <= set(item.get("MatchingEventTypes") or [])
        ]
        add("bounces and complaints reach SNS", feeds, "no enabled SNS destination for BOUNCE and COMPLAINT")

    return results


def main(argv: list[str]) -> int:
    import boto3

    results = check(boto3.client("sesv2", region_name=REGION))
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok and name != "out of the sandbox" else f": {detail}"))
    return 0 if all(ok for _name, ok, _detail in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
