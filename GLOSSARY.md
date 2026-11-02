# Mail tutor

A tutor that reaches a student only by email. The student receives an assignment, sends code back, and gets a result on that same thread.

## People

**Student**:
A person identified by the email address they write from. A student has at most one open assignment.
_Avoid_: user, account

**Student card**:
The stored facts for one student: email, open assignment, whether a grade is in flight, graded tries for the UTC day, last result, and letters already handled.
_Avoid_: profile, account

**In flight**:
A student whose submission is being graded in a room.
_Avoid_: locked, busy

**Finished**:
A student who has passed the last assignment on the ladder.
_Avoid_: complete, graduated

## Mail

**Letter**:
One inbound email from a student, identified by its message id.
_Avoid_: attempt

**Zip**:
The code archive attached to a letter.
_Avoid_: attempt

**Submission**:
A letter whose zip has been accepted for grading. A student has at most one in a batch.
_Avoid_: attempt

**Reply**:
The email the tutor sends on the same thread as a letter.
_Avoid_: response, notification

## The work

**Assignment**:
One exercise the tutor asks a student to complete, such as triaging tickets.
_Avoid_: problem

**Ladder**:
The ordered assignments a student walks, one open at a time.
_Avoid_: sequence, course, track

**Checker**:
The tutor's judge of a submission.
_Avoid_: model

**Model**:
The language model that writes the note. The student's code may call it.
_Avoid_: checker

## Grading

**Batch**:
The submissions graded together.

**Door**:
The private opening that exists only while a batch is grading.
_Avoid_: endpoint

**Room**:
The private place where one submission is graded.
_Avoid_: sandbox

**Graded try**:
One pass or one fail for a student on a UTC day.
_Avoid_: attempt

**Daily cap**:
Ten graded tries for one student on one UTC day.
_Avoid_: quota

**Pass**:
The checker's acceptance of a submission.
_Avoid_: success

**Fail**:
The checker's rejection of a submission.
_Avoid_: error

**Not graded**:
A submission the tutor did not finish grading.
_Avoid_: fail, cap hit

**Cap hit**:
The result on a letter that was not accepted because the student has reached the daily cap.
_Avoid_: not graded

**Note**:
The explanation the model writes on a pass or a fail.
_Avoid_: feedback, comment, findings

**Findings**:
What the checker returns when it rejects a submission.
_Avoid_: note, explanation
