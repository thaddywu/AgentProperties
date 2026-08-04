# Filesystem Service: Endpoints and Edges

The action layer of [`fs_trace.py`](fs_trace.py) specified as a service, so the
typestate machine is written against endpoints with typed parameters rather than
against shell strings. Same method as [`../mr/typestate.py`](../mr/typestate.py):
the machine comes from the spec, never from traces.

## Principles

1. **No stdout parsing.** The machine sees the endpoint, its arguments, and the exit
   code. Never the output text. Output formats vary per flag, get truncated in traces,
   and reintroduce a dependency on the terminal render that layer C exists to remove.
   Exit code is a structured field, not output, and is allowed.
2. **Minimal flag support, explicitly bounded.** A flag is modeled only if it
   (a) selects a different endpoint, (b) names a path, or (c) consumes a token that
   would otherwise be read as a path. Every other flag is listed as ignored.
3. **Endpoints, not commands.** Several commands map to one endpoint; one command may
   map to several (`tar` -> `archive.pack` or `archive.unpack`).

## Resource and states

One resource: `path`, keyed by its normalized absolute form.

| state | meaning |
|---|---|
| `UNKNOWN` | never observed -- the default; the container ships a whole filesystem |
| `EXISTS` | known to be there |
| `ABSENT` | known not to be there: deleted by this trace, or probed and missing |

Plus a **ledger** of paths the agent had a legitimate source for: named in the
instruction, created by the Dockerfile, created by the trace, or *under a directory the
trace listed*. The last clause is how the ledger grows without reading any output.

Scope: only paths under `/app /opt /srv /data /testbed /root /tmp /home` are judged.
194 of the 207 instruction-named paths in terminal-bench live under `/app`; the base
image ships tens of thousands of system paths that no trace introduces.

## Endpoints

| endpoint | parameters | exit code used for |
|---|---|---|
| `fs.read` | `path` | -- |
| `fs.write` | `path` | -- |
| `fs.delete` | `path`, `recursive: bool` | -- |
| `fs.stat` | `path` | resolving `EXISTS` vs `ABSENT` |
| `fs.list` | `path` | -- |
| `fs.copy` | `src`, `dst` | -- |
| `fs.move` | `src`, `dst` | -- |
| `fs.exec` | `path` | -- |
| `fs.chdir` | `path` | -- |
| `archive.pack` | `archive`, `members[]`, `base_dir` | -- |
| `archive.unpack` | `archive` | -- |

## Edges

One row per resource an endpoint moves. `src` lists the states the call is defined on;
anything else is a violation.

| endpoint | resource role | src | dst | guard |
|---|---|---|---|---|
| `fs.read` | `path` | UNKNOWN, EXISTS | unchanged | `path` in ledger |
| `fs.exec` | `path` | UNKNOWN, EXISTS | unchanged | `path` in ledger; writes it performs are invisible |
| `fs.write` | `path` | UNKNOWN, EXISTS, ABSENT | EXISTS | `parent(path)` not ABSENT |
| `fs.delete` | `path` | UNKNOWN, EXISTS, ABSENT | ABSENT | with `recursive`, all descendants -> ABSENT |
| `fs.stat` | `path` | any | EXISTS if exit 0, ABSENT if nonzero, else unchanged | never violates |
| `fs.list` | `path` | any | EXISTS | admits every path under `path` to the ledger |
| `fs.copy` | `src` | UNKNOWN, EXISTS | unchanged | `src` in ledger |
| `fs.copy` | `dst` | any | EXISTS | `parent(dst)` not ABSENT |
| `fs.move` | `src` | UNKNOWN, EXISTS | ABSENT | `src` in ledger |
| `fs.move` | `dst` | any | EXISTS | `parent(dst)` not ABSENT |
| `fs.chdir` | `path` | UNKNOWN, EXISTS | unchanged | updates cwd only |
| `archive.pack` | `archive` | any | EXISTS | |
| `archive.pack` | each `member` | UNKNOWN, EXISTS | unchanged | resolved against `base_dir` |
| `archive.unpack` | `archive` | UNKNOWN, EXISTS | unchanged | members unknown without output |

`fs.stat` is the reason `ls` is not `fs.read`. Agents verify a deletion with
`ls p 2>/dev/null || echo gone`; folding that into `fs.read` turns every cleanup task
into a false use-after-delete.

**Exit-code attribution caveat.** A step may contain several segments joined by
`&&`/`||`, and the exit code belongs to the step. `fs.stat` therefore updates state only
when its step holds exactly one segment; otherwise the state is left unchanged. Prefer
false negatives.

## Command surface

| command | endpoint | modeled flags | ignored |
|---|---|---|---|
| `cd`, `pushd` | `fs.chdir` | -- | all |
| `ls`, `stat`, `file`, `du`, `test`, `realpath` | `fs.stat` | -- | all |
| `find`, `tree` | `fs.list` | -- | all |
| `cat`, `less`, `nl`, `od`, `diff`, `sort`, `cut`, `jq`, `awk` | `fs.read` | `-d -f -t -k -w` consume a value | all |
| `head`, `tail` | `fs.read` | `-n -c` consume a value | all |
| `grep`, `rg` | `fs.read` (last operand) | `-e -m -A -B -C` consume a value | all |
| `mkdir`, `touch` | `fs.write` | -- | all |
| `rm`, `rmdir`, `unlink` | `fs.delete` | `-r -R --recursive` set `recursive` | all |
| `cp`, `install` | `fs.copy` | `-t -m -S` consume a value | all |
| `mv` | `fs.move` | `-t` consumes a value | all |
| `shred` | `fs.read` | `-n -s` consume a value | all |
| `chmod`, `chown`, `chgrp` | `fs.read` | -- | all |
| `sed` | `fs.read` (last operand) | `-e -f` consume a value | `-i` |
| `gpg` | `fs.read`, plus `fs.write` for `--output` | `--output -o` name an output; `--cipher-algo --compress-algo --passphrase-fd -r` consume a value | all |
| `python`, `bash`, `sh`, `node`, `perl` | `fs.exec` | `-c -m` consume a value | all |
| `tar` | `archive.pack` if mode has `c`, else `archive.unpack` | `-c -x -t` select the endpoint; `-f` names the archive; `-C` sets `base_dir`; `-T` consumes a value | `-z -j -v -p` and all long options |
| `unzip`, `7z`, `gunzip` | `archive.unpack` | -- | all |
| `> f`, `>> f` | `fs.write` | -- | -- |
| heredoc target | `fs.write` | -- | -- |

Two auxiliary tables carry the rest of the surface:

- `PREFIXES` = `sudo timeout env nohup time stdbuf xargs nice` -- stripped, then
  re-dispatched on what follows, along with any bare numeric argument they consume.
- `STATELESS` = `echo printf pwd which pip apt conda npm uv git curl wget ps kill ...` --
  declared to touch no path, so that a command in neither table is a genuine gap rather
  than a silent drop.

## Not modeled

| | why |
|---|---|
| writes performed inside `fs.exec` | invisible at this layer; 486 of 586 `open()` calls in terminal-bench live in scripts the agent writes and then runs |
| archive members after `archive.unpack` | recoverable only from output |
| `$VAR`, globs, backticks, `$(...)` | emitted as `UNRESOLVED`; they also make the affected subtree fall back to `UNKNOWN` |
| symlinks and `realpath` aliasing | 3 tasks use `ln` |
| file vs directory type | type errors are rare here and would double the cost of every edge |
| permission bits | only `fs.exec` would use them |
| background writes (`cmd &`) | no ordering available |

## Coverage

Measured over the 333 mini-swe-agent traces in `datasets/tb-leaderboard/`
(terminal-bench-core 0.1.1):

```
4200 steps  .  5943 segments  .  270 steps with a nonzero exit code

fs.read 1094   fs.write 907   fs.exec 810   fs.stat 462
fs.chdir 176   fs.list 148    fs.delete 66  UNRESOLVED 252

segments with no endpoint:  stateless 1656 . no path operand 425 . UNMATCHED 483 (8.1%)
```

`UNMATCHED` is the maintenance signal. It is currently dominated by task-specific
binaries (`pdp11` 39, `fasttext` 31, `aws` 24, `nginx` 23) and by shell keywords
leaking through the splitter (`do`, `done`, `for`).
