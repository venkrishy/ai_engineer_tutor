"""The note: a short explanation the model writes on a pass or a fail."""

from __future__ import annotations

PROFILE_ID = "us.anthropic.claude-sonnet-4-6"

SYSTEM = (
    "You write the short note in an email from an automated coding tutor to a student. "
    "The student built a small program with an AI coding tool and the tutor graded it against hidden tickets. "
    "Write plain text only, at most 90 words, in a warm and direct voice. No emojis, no markdown, no greeting, no sign-off. "
    "Never reveal or guess the hidden tickets or their answers. "
    "On a pass, say briefly what the level asked for and congratulate the student on moving up. "
    "On a fail, say in plain words what to look at next, using only the findings you are given, and encourage another try."
)


class BedrockModel:
    def __init__(self, client, model_id: str = PROFILE_ID) -> None:
        self._client = client
        self._model_id = model_id

    def note(self, level: str, result: str, findings: str = "") -> str:
        prompt = f"Level: {level}\nResult: {result}\nFindings:\n{findings or 'none'}"
        try:
            response = self._client.converse(
                modelId=self._model_id,
                system=[{"text": SYSTEM}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 300, "temperature": 0},
            )
            parts = response["output"]["message"]["content"]
            return "".join(part.get("text", "") for part in parts).strip()
        except Exception:
            return ""
