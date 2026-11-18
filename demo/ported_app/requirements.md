# LabCluster

## Overview

LabCluster is a multi-agent framework for coordinating a simulated laboratory server cluster. Professor, PhD and Master each make decisions using a separate role prompt and model context, exchange messages, and use local tools to manage resource requests and jobs.

| Agent | Resource capability | Permissions and information access |
|---|---|---|
| Professor | Manages CPU and GPU nodes within configured resource limits | Reviews and dispatches requests, may stop either student's job, and can inspect both students' complete task inputs and results. |
| PhD | CPU or GPU; up to 8 cores, 32 GB and 60 requested minutes | Manages only its own jobs and normally has priority over Master for a free compatible node. Cannot inspect or stop Master's work. |
| Master | CPU only; up to 4 cores, 8 GB and 20 requested minutes | Manages only its own jobs. Waits behind eligible PhD jobs, with protection after three skipped eligible dispatch opportunities. Cannot inspect or stop PhD's work. |

The cluster contains one CPU node and one GPU node, each with 8 CPU cores and 32 GB of memory. A job exclusively occupies its assigned node. Requested runtime is an admission limit in this finite simulator, not a real workload timer. PhD priority applies only while waiting for a free compatible node and does not preempt a running Master job.

## Required workflow

A new job is QUEUED. Professor reviews its exact task version and resource request; approval leaves it QUEUED until a compatible node is free. Successful allocation changes it to RUNNING. A matching runner completion receipt produces COMPLETED and releases its allocation. A rejected request, owner cancellation or Professor stop produces TERMINATED; a running job requires stop confirmation before releasing its node. These are the only four job states. Terminal jobs cannot restart.

Revising queued work invalidates its approval. Students send their own requests and reports to Professor; Professor may send task details back to the owner. Private data must not cross from one student to the other. Public node availability and quota rules may be shared.

## What the application must never do

- Give a student authority to approve, dispatch or stop another student's work, or run a request outside its resource capability.
- Deliver one student's private tasks, inputs, results, approvals or execution receipts to the other student; Professor remains authorized to inspect both.
- Start a task from an unrecorded approval claim or reuse approval after the task changes.
- Mark work completed without matching execution evidence, double-allocate a node, lose a running job's node, or revive a terminal job.
- Use queue priority to interrupt running work or let an old notification release a newer run's allocation.
- Expose API keys or real student records in prompts, logs or the submission.

The detailed, checkable conditions and exceptions are P1–P6 in [the original policies](../orig_app/policies.md).

## Course demo

This snapshot runs the deterministic `T1_priority_queue` scenario in
[the test cases](../test_cases.json) with synthetic fixtures. See
[the walkthrough](../README.md) for the original and ported commands.
