# UT-01 consent

This is the public, unfilled consent template.
The team prints one copy per session, and the participant signs it before the session starts.
The signed copies are kept in the private usability-data repository and are never committed to the product repository.

## Study

Gateway7 usability test `UT-01`, run by Team 7 of the IT Product Development course.
The test studies how a developer sends a first request through the gateway, recovers from a denied model, and checks a middleware change offline.

## What the session involves

- One session of about 45 minutes, in person, on the university network.
- Three tasks in a fixed order, a short questionnaire before the session, a rating after each task, a ten-item questionnaire after all tasks, and a short interview.
- The session is recorded: screen and audio.
- The team observes and takes notes.

## Recording

The recording is mandatory for a counted session.
A participant who does not want to be recorded can stop before the session starts and is not counted.
The recording is stored in the team's cloud folder, and only the team and the instructors can open it.

## What is published

The team publishes a sanitized record of the session: the task outcomes, the timings, the ratings, the questionnaire scores, and the anonymized observations.
No name, email, face, voice, or other identity is published.
The team may quote an anonymized statement from the interview, and the participant can refuse the quotes without refusing the session.
The recordings are never published.

## Private data and access

The consent record, the identity mapping, the raw notes, the working analysis, and the test's filtered telemetry export are kept in the private `iteam7/gateway7-usability-data` repository.
Only the team and the instructors can read it.
The session's telemetry uses a participant code, and its mapping to a person stays in that private repository.

## Tools

The team uses the staging deployment of Gateway7, its analytics and observability backends, and the team's cloud storage for the recording.
No real payment is made, and the session does not touch production data.

## Withdrawal

The participant can stop at any time and can withdraw after the session by contacting the team through the course.
On withdrawal, the team removes the raw text and the recording, retires the participant code, and does not use the session's data in the results.
The sanitized record already published is not rewritten, and the withdrawn session is reported as not counted.

## Deletion after grading

The private repository, its history, and the recordings are deleted after the course has been graded.
The sanitized public record, which contains no identity, stays in the product repository.

## Declaration

- [ ] I am 18 years old or older.
- [ ] I have read this form and I agree to the recording.
- [ ] I agree to the sanitized public results.
- [ ] I agree to the optional anonymized quotes (optional; the session is counted without them).

Participant code: `P-__`

Signature: ______________________________

Date: ______________________________

Team member present: ______________________________
