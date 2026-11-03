import unittest

from tutor.notes import PROFILE_ID, BedrockModel


class FakeBedrock:
    def __init__(self, text="Nice work.", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"output": {"message": {"content": [{"text": self.text}]}}}


class NotesTest(unittest.TestCase):
    def test_the_note_is_the_models_text(self):
        self.assertEqual(BedrockModel(FakeBedrock("  Well done.  ")).note("Classify", "pass"), "Well done.")

    def test_the_call_uses_the_cross_region_profile_and_no_randomness(self):
        client = FakeBedrock()

        BedrockModel(client).note("Route", "fail", "2 of 5 tickets passed")

        call = client.calls[0]
        self.assertEqual(call["modelId"], PROFILE_ID)
        self.assertTrue(PROFILE_ID.startswith("us."))
        self.assertEqual(call["inferenceConfig"]["temperature"], 0)
        self.assertIn("2 of 5 tickets passed", call["messages"][0]["content"][0]["text"])

    def test_a_model_error_gives_no_note_instead_of_breaking_the_reply(self):
        self.assertEqual(BedrockModel(FakeBedrock(error=RuntimeError("throttled"))).note("Classify", "pass"), "")


if __name__ == "__main__":
    unittest.main()
