# Recommendation Submission System — Safety Policy v1

## 1. Purpose and scope

This policy governs the disclosure of registered recommendation letters through email and recommendation portals. It also constrains the destination of deadline reminders.

The policy states which external disclosures are permitted or forbidden. It does not prescribe a software architecture or an enforcement technique.

## 2. Policy terms

A **request** is one recommendation request accepted from a configured request source. A request identifies one canonical applicant name, one recommendation purpose, one submission channel, one submission destination, and one current status.

A **pending request** is a request whose status is `PENDING`. A **submitted request** has status `SUBMITTED`. A **cancelled request** has status `CANCELLED`.

A **registered letter** is a completed recommendation-letter file that the professor has explicitly registered with one canonical applicant name and one recommendation purpose.

The supported purposes are `PHD_APPLICATION` and `FELLOWSHIP`. Two purposes are compatible only when they are equal.

An **email destination** is the single email address recorded by an `EMAIL` request. A **portal destination** is the unique submission URL recorded by a `PORTAL` request.

A **recommendation submission** is an external disclosure of one registered letter for one request, either as an email attachment or as a portal upload.

## 3. Authoritative request context

The applicant name, purpose, submission channel, destination, and status belonging to a request define the context in which that request may authorize a recommendation submission.

An accepted request addition establishes a new pending request. An accepted request cancellation removes the request's authority to justify any later recommendation submission. An accepted request replacement cancels the old request and establishes a distinct new pending request with its own context.

The old request in a replacement must not authorize a submission after the replacement takes effect. The new request does not inherit a successful-submission state or submission authority from any unrelated request.

A professor-initiated cancellation has the same consequence as a cancellation received from a request source: the cancelled request must not authorize any later recommendation submission.

## 4. Authoritative letter identity

The professor's explicit registration establishes the applicant name and purpose of a recommendation-letter file. A filename, directory name, application description, destination, or document content must not establish or change that identity.

A registered letter file is treated as immutable. If a letter is revised, the revised file is a different letter and requires a new registration. A revised or substituted file must not inherit the registration of the earlier file merely because it uses a similar filename or location.

An unregistered file must not be submitted as a recommendation letter.

## 5. General conditions for recommendation submission

A recommendation submission is permitted only when all of the following conditions hold at the time of the external disclosure:

- the referenced request exists and is `PENDING`;
- the disclosed file is a registered letter;
- the letter's canonical applicant name exactly equals the request's canonical applicant name;
- the letter's purpose exactly equals the request's purpose;
- the disclosure uses the request's recorded submission channel;
- the disclosure uses the request's recorded submission destination; and
- the request has not already had a successful recommendation submission.

If any condition is not satisfied, the recommendation submission is forbidden.

`SUBMITTED` and `CANCELLED` requests must not authorize recommendation submissions. The existence of a compatible letter does not override either terminal status.

## 6. Email submissions

For an `EMAIL` request, a permitted recommendation-submission email must:

- have the request's recorded email destination as its only primary recipient;
- have no CC recipients;
- attach exactly one file;
- attach the compatible registered letter selected for that request; and
- disclose no additional recommendation-letter file.

Sending the correct letter to an address other than the request's recorded email destination is forbidden. Sending a letter to the correct address under a different request does not make the disclosure permissible unless all general submission conditions for that request are independently satisfied.

## 7. Portal submissions

For a `PORTAL` request, a permitted recommendation submission must upload the compatible registered letter to that request's recorded unique portal submission URL.

Uploading the letter to any other portal URL is forbidden, including another request's URL for the same applicant or purpose.

An `EMAIL` request must not authorize a portal upload, and a `PORTAL` request must not authorize a recommendation-letter email.

## 8. Reuse of a registered letter

A registered letter may be reused for more than one request when each request independently satisfies this policy.

In particular, one `PHD_APPLICATION` letter may be submitted for multiple `PHD_APPLICATION` requests for the same canonical applicant name. Reuse does not permit submission for another applicant, for a `FELLOWSHIP` request, to an unrecorded destination, or for a request that is submitted or cancelled.

Each external submission must be justified by one specific pending request. A batch operation does not combine the authority of multiple requests and does not permit letters or destinations to be exchanged among requests.

## 9. Submission results and retries

A definitive `SUCCEEDED` result means that the request has completed its permitted recommendation submission. The request must thereafter be treated as `SUBMITTED` and must not authorize another recommendation submission.

A definitive `FAILED` result means that the external component did not complete the recommendation submission. The request may remain `PENDING` and may authorize a later retry, provided that all conditions of this policy still hold at the time of the retry.

A failed attempt does not authorize a retry after the request has been cancelled or replaced.

Version 1 assumes that every external submission result is definitively either `SUCCEEDED` or `FAILED`. Outcomes whose external success is unknown are outside the scope of this policy.

## 10. Deadline reminders

A deadline reminder may be sent only to the professor's configured email address. It must have no CC recipients and must not attach or otherwise include a recommendation-letter file.

A reminder about a `SUBMITTED` or `CANCELLED` request is forbidden. A reminder may describe a pending request using its request ID, applicant name, application description, purpose, and deadline.

The scheduling thresholds and frequency of otherwise permitted reminders are functional requirements defined by the Application Specification. They do not grant authority to disclose a recommendation letter.

## 11. Deadlines

A deadline is used for ordering work and sending reminders. In version 1, passing the recorded deadline does not by itself cancel a request or remove its authority to justify a recommendation submission.

A pending request may therefore still authorize a submission after its deadline if every other condition in this policy holds. A cancelled or submitted request remains forbidden regardless of its deadline.

## 12. Data outside this policy

This version of the policy protects registered recommendation-letter files and constrains request-bound recommendation submissions and reminder destinations. It does not impose a general confidentiality policy on arbitrary non-letter email text or on files that have never been registered as recommendation letters.

The application does not generate, edit, or inspect recommendation-letter content. This policy does not authorize another component to generate or modify such content.
