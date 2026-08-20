# A Minimal Filesystem Typestate Machine

For checking terminal-bench traces. Vocabulary follows `mr/typestate.py`
(`Edge`, ledger, `Kind`). Companion to [`terminalbench.md`](terminalbench.md).

## Trace source

Not `commands.txt` (inputs only) but `sessions/agent.cast` — an asciinema stream of
`[t, kind, data]` where `i` = input, `o` = output, `m` = the agent's JSON reasoning.
Pairing is clean: terminus appends `; tmux wait -S done` to every command, and each
output block ends at the shell prompt.

```
i  'netstat -tuln | grep :443; tmux wait -S done\r'
o  'tcp  0  0  0.0.0.0:443  0.0.0.0:*  LISTEN\r\n'
o  '\x1b[?2004hroot@7203dd5163d2:/app# '
```

So every command comes with its output and an implied exit status. Everything below
depends on that.

## 1. States

Three, deliberately **not** distinguishing file from directory:

```
UNKNOWN   never observed (default initial state)
EXISTS    known to exist
ABSENT    known not to exist
```

Type errors (`cd` a file, `cat` a directory) are rare in this corpus and would double
the cost of every edge. Leave them out of v0.

Orthogonal to state, a **ledger**: paths the agent had a legitimate source for.
Both are needed, because they separate two different failures:

| ledger | state | meaning |
|---|---|---|
| ∉ | UNKNOWN | fabricated path → `UNBOUND_IDENTIFIER` |
| ∈ | ABSENT | real path, deleted or already known missing → `UNDEFINED_TRANSITION` |
| ∈ | UNKNOWN | legitimate probe — not reported |

Ledger seed comes from static material: absolute paths named in the instruction
(207 of 241 tasks have some) plus paths the Dockerfile copies or creates. Those are
also seeded to `EXISTS`.

## 2. Actions

Five primitives:

| action | effect |
|---|---|
| `CREATE(p)` | `p → EXISTS`, `ledger += p`; guard: `parent(p) ∉ ABSENT` |
| `READ(p)` | no state change; requires `p ∉ ABSENT` and `p ∈ ledger` |
| `DELETE(p)` | `p → ABSENT` |
| `LIST(d)` | read-only; `ledger +=` listed children, children `→ EXISTS`; **and any known path under `d` that was not listed → `ABSENT`** |
| `EXEC_OPAQUE(p)` | `READ(p)`; subsequent writes are invisible |

Compounds are decomposed rather than added as primitives:

```
cp s d    =  READ(s); CREATE(d)
mv s d    =  READ(s); CREATE(d); DELETE(s)
sed -i f  =  READ(f); CREATE(f)
```

`LIST` is the only read-only action that yields **negative** information, and carries
the most discriminating power: after `ls /app`, guessing `/app/xxx` stops being a probe
and becomes a violation.

## 3. Command → action mapping

Frequencies measured over 233 `solution.sh` files with heredoc bodies stripped
(`occ.` = occurrences, `t` = tasks).

| command form | occ. | action | note |
|---|---|---|---|
| `echo … >> f` | 324 | `CREATE(f)` | |
| `cat > f <<EOF` | 211 | **`CREATE(f)`** | most important rule: `cat` appears in 158 tasks but writes more often than it reads |
| `python3 / bash X` | 92 | `EXEC_OPAQUE(X)` | see below |
| `echo … > f` | 67 | `CREATE(f)` | |
| `cat f` | 63 | `READ(f)` | distinguished from the above by presence of `>` / `<<` |
| `mkdir [-p] d` | 64 / 38t | `CREATE(d)` | `-p` also creates every ancestor |
| `cd d` | 89 / 51t | `READ(d)` + update cwd | relative paths depend entirely on this |
| `sed -i f` | 50 | `READ(f); CREATE(f)` | read-modify-write, so existence is required |
| `ls [d]` | 43 / 25t | `LIST(d)` | requires parsing the output block |
| `chmod / chown p` | 35 / 26t | `READ(p)` | |
| `rm [-r] p` | 34 / 22t | `DELETE(p)` (with `-r`, all descendants) | |
| `cp s d` | 31 / 16t | decomposed | |
| `tar -x f` / `unzip f` | 16 / 11t | `READ(f)`; members enter the ledger | 40 tasks involve archives |
| `grep/head/wc … f` | | `READ(f)` | |

Unresolvable paths — `$VAR`, globs, `$(…)` — produce no findings. Mark them
`UNRESOLVED` and let them make the affected subtree conservative (after `rm /app/*`,
every instance under `/app` falls back to `UNKNOWN`). Same principle as
`truncated → ok=None` in `typestate.py`: prefer false negatives.

**`EXEC_OPAQUE` is the one real compromise.** 161 of 233 solutions write a script via
heredoc and then run it; the `open(p,'w')` inside is invisible at the shell layer.
v0 does *not* reset `ABSENT` after an opaque exec (keeping detection power) but tags
any finding that follows one with `after_opaque_exec=True`, so its false-positive rate
can be measured separately. If that bucket is noisy, the next step is extracting the
script body from the heredoc — it is present verbatim in the trace — and lifting a
second layer of file operations from it.

## 4. Checks on a trace

Reusing the existing `Kind`:

| Kind | trigger |
|---|---|
| `UNBOUND_IDENTIFIER` | `READ(p)` where `p ∉ ledger` — fabricated path |
| `UNDEFINED_TRANSITION` | `READ(p)` where `state(p) = ABSENT` — use after delete, or a repeat of a call already known to fail |
| `GUARD_UNSATISFIED` | `CREATE(p)` where `parent(p) = ABSENT` |

Plus one cost metric, deliberately **outside** `FSM_KINDS`:

- `REDUNDANT_PROBE` — repeated `READ(p)` in the same state with no intervening
  `CREATE`. Not a correctness violation; this is the wasted-turn signal.

### Ground truth is free

Because the cast carries output, every predicted finding can be checked against the
`o` events that follow it (`No such file or directory`, `not found`):

```
predicted + observed error   → true positive
predicted + no error         → false positive (usually EXEC_OPAQUE, or a gap in the s₀ seed)
not predicted + observed error → false negative (a missing row in the mapping table)
```

No manual labelling, and the false-negative column names exactly which command form
the mapping table still needs. This should be the first thing built.

## Blocker

`datasets/terminal-bench/runs/` currently holds 3 traces, all of the same task
(`home-server-https`). The checker can be written now, but producing numbers requires
collecting traces first.
