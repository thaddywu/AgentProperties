# Checking Agent Traces for Resource-Lifecycle Violations

## 1. The problem

Agents use resources with a lifecycle: a certificate is issued, valid, then expired.
A file lock is taken and must be released. A file is created before it is read.

When an agent violates one of these, the environment usually just errors and the agent
recovers — so the run still passes, and the benchmark records nothing. The cost is a
wasted turn. The goal is to detect these statically from the trace, and eventually to
prevent them at runtime: refuse the call that uses an expired certificate before it is
made.

**Today we have done one resource, filesystem paths, offline.** No certificates, no
locks, no interception yet. Filesystem first because it is the densest: 207 of the 241
terminal-bench tasks name an absolute path directly in the instruction.

## 2. A minimal filesystem service

`tsm/openapi.yaml` — OpenAPI 3.1, 13 operations.

```
fs.read   fs.write   fs.delete   fs.stat   fs.list   fs.copy   fs.move
fs.exec   fs.chdir   archive.pack   archive.unpack   sys.opaque   sys.noop
```

Modelling a filesystem completely, or every binary, is impossible. So the spec states
what it does NOT model. `tar` declares four flags (`-c -f -C -T`) and lists `-z -j -v -p`
as ignored. Every operation carries `x-commands`, `x-modeled-flags`, `x-ignored-flags`
and `x-provenance`.

The payoff comes in two places. **Later:** an agent calling these endpoints gives us the
tool name and arguments for free. **Now:** a schema forces the boundary of the model to
be written down and reviewed.

Paths are always absolute. Resolving relative paths is the adapter's job; when it cannot,
the call is marked unresolved and skipped rather than guessed.

## 3. A minimal state machine

`tsm/fsm.yaml` — 3 states, 16 edges over the 13 operations.

```
UNKNOWN  ──fs.write──▶  EXISTS  ──fs.delete──▶  ABSENT
   │                       ▲                       │
   └───── fs.read OK ──────┘                fs.read = VIOLATION
```

`UNKNOWN` is why there are three states rather than two: a container ships an entire
filesystem, so a path the agent has not touched is not absent, it is unobserved.
Reading it is legitimate probing.

One operation may carry several edges — `fs.move` has two, because one call moves two
resources: the source to ABSENT and the destination to EXISTS.

Alongside the state, a **ledger** of paths the agent had a legitimate source for. The
two separate an invented filename (`UNBOUND_IDENTIFIER`) from a real path that was
removed (`UNDEFINED_TRANSITION`).

## 4. The traces

terminal-bench-core 0.1.1, from the official leaderboard repository
(`github.com/laude-institute/terminal-bench-leaderboard`), the
`swe-agent-mini + claude-4-sonnet` submission.

**333 trials, 171 usable** — the other 162 are agent-install failures whose recording
holds apt-get noise and `bash: mini: command not found`. 171 traces convert to **6216
endpoint calls**.

```
recorded (.cast)                    converted (calls.jsonl)
```bash                             {"op": "archive.pack",
tar -czf sensitive_files.tar.gz \    "args": {"archive": "/app/sensitive_files.tar.gz",
    -C /opt sensitive_service_data/           "members": ["/opt/sensitive_service_data"]},
```                                  "raw": "tar -czf sensitive_files.tar.gz -C /opt ...",
<returncode>0</returncode>           "cwd": "/app", "rule": "tar c -> archive",
                                     "exit_code": 0}
```

Conversion is automatic, but every call carries its own evidence: `raw` (the segment
verbatim), `cwd` (the directory the path was resolved against), `rule` (which mapping
row fired). Any line can be checked back against the recording.

## 5. Replay — see `walkthrough.md`

`decommissioning-service-with-sensitive-data`: archive a sensitive directory, encrypt
it, shred the originals, leave nothing behind. 11 steps.

| step | | |
|---|---|---|
| 2, 4 | `archive.pack`, `fs.write` | `UNKNOWN → EXISTS` — created, not seeded: naming a path in the instruction proves the agent knows the name, not that the file is there |
| 6-8 | `fs.delete` ×4 | files, then the directory, then the intermediate archive |
| 9 | `fs.list` on ABSENT | **raises nothing** — the agent is verifying its own cleanup with `ls p 2>/dev/null`. Had `ls` been a read, every cleanup task would report a false use-after-delete |
| 10 | blind | a `tar` reading from a pipe has no path argument; recorded as blind, not guessed |

**Zero violations — this trial passed. The machine earning its keep by not firing.**

## 6. Where this stands

Across all 171 traces: 3467 checked transitions, **9 findings, 0 of them high
confidence.** Every one follows an opaque call, and our confidence tag says so.

Three measurable reasons, not excuses:

- `fs.delete` occurs **56 times in the entire corpus** — use-after-delete has almost no
  opportunity to fire
- **1905 of 5372 calls are blind**: opaque 418, exec 810, unresolved 251, no path
  operand 426
- the largest hole is `fs.exec` (810). terminal-bench is solved by writing a script and
  running it, and 486 of 586 `open()` calls live inside those scripts

**Next:** open up `fs.exec`. The script body is in the recording — the agent typed it
into the terminal as a heredoc — so its `open(p, 'w')` calls can be lifted statically.
That converts the largest blind bucket into visible writes.
