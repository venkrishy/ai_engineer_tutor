import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ses_preflight.py"
spec = importlib.util.spec_from_file_location("ses_preflight", SCRIPT)
ses_preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ses_preflight)


class NotFound(Exception):
    response = {"Error": {"Code": "NotFoundException"}}


class AccessDenied(Exception):
    response = {"Error": {"Code": "AccessDeniedException"}}


def healthy():
    return {
        "account": {
            "ProductionAccessEnabled": True,
            "SendingEnabled": True,
            "EnforcementStatus": "HEALTHY",
            "SendQuota": {"Max24HourSend": 50000.0, "MaxSendRate": 14.0},
            "SuppressionAttributes": {"SuppressedReasons": ["BOUNCE", "COMPLAINT"]},
        },
        "identity": {
            "VerifiedForSendingStatus": True,
            "DkimAttributes": {"Status": "SUCCESS", "SigningEnabled": True},
            "MailFromAttributes": {"MailFromDomain": "bounce.theaiguru.dev", "MailFromDomainStatus": "SUCCESS"},
        },
        "configuration_set": {
            "SendingOptions": {"SendingEnabled": True},
            "ReputationOptions": {"ReputationMetricsEnabled": True},
            "SuppressionOptions": {"SuppressedReasons": ["BOUNCE", "COMPLAINT"]},
        },
        "destinations": {
            "EventDestinations": [
                {
                    "Enabled": True,
                    "MatchingEventTypes": ["BOUNCE", "COMPLAINT", "REJECT"],
                    "SnsDestination": {"TopicArn": "arn:aws:sns:us-east-1:1:alerts"},
                }
            ]
        },
    }


class FakeSesV2:
    """Answers like SESv2 from a plain dict. A value that is an exception is raised."""

    def __init__(self, state):
        self.state = state

    def _answer(self, key):
        value = self.state[key]
        if isinstance(value, Exception):
            raise value
        return value

    def get_account(self):
        return self._answer("account")

    def get_email_identity(self, EmailIdentity):
        return self._answer("identity")

    def get_configuration_set(self, ConfigurationSetName):
        return self._answer("configuration_set")

    def get_configuration_set_event_destinations(self, ConfigurationSetName):
        return self._answer("destinations")


def outcome(state):
    return {name: ok for name, ok, _detail in ses_preflight.check(FakeSesV2(state))}


class SesPreflightTest(unittest.TestCase):
    def test_a_production_account_with_everything_in_place_passes(self):
        results = outcome(healthy())
        self.assertTrue(results)
        self.assertTrue(all(results.values()), results)

    def test_the_sandbox_is_reported(self):
        state = healthy()
        state["account"]["ProductionAccessEnabled"] = False
        results = outcome(state)
        self.assertFalse(results["out of the sandbox"])
        self.assertTrue(results["domain identity"])

    def test_an_account_under_review_or_paused_is_reported(self):
        for status in ("PROBATION", "SHUTDOWN"):
            state = healthy()
            state["account"]["EnforcementStatus"] = status
            self.assertFalse(outcome(state)["account health"], status)
        state = healthy()
        state["account"]["SendingEnabled"] = False
        self.assertFalse(outcome(state)["account can send"])

    def test_account_suppression_must_cover_bounces_and_complaints(self):
        state = healthy()
        state["account"]["SuppressionAttributes"] = {"SuppressedReasons": ["BOUNCE"]}
        self.assertFalse(outcome(state)["account suppression list"])
        state["account"].pop("SuppressionAttributes")
        self.assertFalse(outcome(state)["account suppression list"])

    def test_a_missing_domain_identity_is_reported_not_raised(self):
        state = healthy()
        state["identity"] = NotFound()
        results = outcome(state)
        self.assertFalse(results["domain identity"])
        self.assertNotIn("DKIM signing", results)

    def test_dkim_must_be_verified_and_signing(self):
        state = healthy()
        state["identity"]["DkimAttributes"] = {"Status": "PENDING", "SigningEnabled": True}
        self.assertFalse(outcome(state)["DKIM signing"])
        state["identity"]["DkimAttributes"] = {"Status": "SUCCESS", "SigningEnabled": False}
        self.assertFalse(outcome(state)["DKIM signing"])

    def test_a_mail_from_domain_must_be_set_and_verified(self):
        state = healthy()
        state["identity"]["MailFromAttributes"] = {}
        self.assertFalse(outcome(state)["custom MAIL FROM"])
        state["identity"]["MailFromAttributes"] = {"MailFromDomain": "bounce.theaiguru.dev", "MailFromDomainStatus": "PENDING"}
        self.assertFalse(outcome(state)["custom MAIL FROM"])

    def test_a_missing_configuration_set_is_reported_not_raised(self):
        state = healthy()
        state["configuration_set"] = NotFound()
        results = outcome(state)
        self.assertFalse(results["configuration set"])
        self.assertNotIn("bounces and complaints reach SNS", results)

    def test_the_configuration_set_needs_metrics_and_suppression(self):
        state = healthy()
        state["configuration_set"]["ReputationOptions"] = {"ReputationMetricsEnabled": False}
        state["configuration_set"]["SuppressionOptions"] = {}
        results = outcome(state)
        self.assertFalse(results["reputation metrics"])
        self.assertFalse(results["configuration set suppression"])

    def test_bounces_and_complaints_need_an_enabled_sns_destination(self):
        state = healthy()
        state["destinations"]["EventDestinations"][0]["Enabled"] = False
        self.assertFalse(outcome(state)["bounces and complaints reach SNS"])
        state = healthy()
        state["destinations"]["EventDestinations"][0]["MatchingEventTypes"] = ["BOUNCE"]
        self.assertFalse(outcome(state)["bounces and complaints reach SNS"])
        state = healthy()
        state["destinations"] = {"EventDestinations": []}
        self.assertFalse(outcome(state)["bounces and complaints reach SNS"])

    def test_other_errors_are_not_swallowed(self):
        state = healthy()
        state["identity"] = AccessDenied()
        with self.assertRaises(AccessDenied):
            ses_preflight.check(FakeSesV2(state))


if __name__ == "__main__":
    unittest.main()
