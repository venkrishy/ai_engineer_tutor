import aws_cdk as cdk

from tutor_stack import TutorStack

app = cdk.App()
TutorStack(
    app,
    "TutorStack",
    synthesizer=cdk.DefaultStackSynthesizer(generate_bootstrap_version_rule=False),
    env=cdk.Environment(account="908196778839", region="us-east-1"),
)
app.synth()
