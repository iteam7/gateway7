# UT-01 surveys

The instruments are the same for every participant, and they contain no name, email, or other identity.
The participant code `P-nn` is the only identifier on a returned form, and its mapping to a person stays in the private usability-data repository.

## Pre-test

The facilitator reads the questions and records the answers verbatim.

1. How would you describe your current role?
2. Have you called an LLM API from application code before? If so, how recently?
3. Which tools do you use to send an API request: a terminal, a code editor, a client application, or something else?
4. Have you used Gateway7 before today?
5. What do you expect this gateway to do for your team?

The participant also confirms the adult declaration before the session starts: "I am 18 years old or older."

## SEQ, after each task

The facilitator asks the standard question immediately after each task ends, before the next scenario is read.

Overall, how difficult or easy was the task to complete?

The scale runs from 1 to 7, where 1 is very difficult and 7 is very easy.
The facilitator records the number and does not comment on it.

## SUS, after all the tasks

The participant answers the ten standard items in their standard order and wording, from strongly disagree (1) to strongly agree (5).

1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

The score is `SUS = 2.5 × (20 + sum(odd) - sum(even))`, computed from the responses as recorded.
The even items are not reverse-coded before the formula.
The analysis reports the mean and the median with the sample size, `n=<count>`.

## Open-ended post-test

The facilitator asks these questions after the SUS and records the answers in the participant's own words.

1. What was the hardest part of the session?
2. What would you change first?
3. Did anything about the gateway's answer surprise you?
4. How would you explain to a teammate what the gateway did to your message?
5. Is there anything else you want the team to know?
