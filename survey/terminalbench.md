## Resources by mining yield

### 1. Filesystem paths — 207 tasks

The dominant resource. Identifiers appear as literals in the instruction
(`/app/report.txt`, `/app/access_log`, `/app/answer.txt`, `/opt/sensitive_service_data/`).

Occurrences in code: `with open` 486, `open(` 100, `.close()` 35, `tempfile.*` 24,
`shutil.copy` 12, `shutil.rmtree` 9, `flush()` 6, `os.unlink` 4, `os.remove` 3.
Shell verbs by task: `mkdir` 39, `rm` 25, `cp` 12, `chmod` 8, `mv` 4, `ln` 3.

Actions: create (`touch`, `mkdir`, `>`, `cp`, `mv`, extract, `git clone`),
use (`cat`/`head`/`grep`/`python p`/`./p`/`cd`/`ls`), delete (`rm`, `rm -r`, `rmdir`),
discover (`ls`, `find`, `tree`, `stat`).

Properties:
- use-before-create — read/exec a path that is absent
- fabricated path — path never named by the task, never listed by a `ls`/`find` the
  agent saw, never created by it
- parent-not-a-directory before write
- type mismatch (`cd` a file, `cat` a directory)
- destructive overwrite of a declared input (unrecoverable)
- declared output never written
- redundant probe — repeated read, same state, no intervening write (cost, not correctness)

`ls` is unusual: it is read-only yet yields **negative** information — anything not
listed under a listed directory is known absent.

### 2. Packages / environments — ~100 tasks

Occurrences: `apt-get install` 475, `uv run` 284, `uv pip` 273, `uv venv` 222,
`pip install` 171, `venv` 129, `requirements.txt` 15, `conda env` 10, `npm install` 4.
(A share of the `uv` counts is `run-tests.sh` boilerplate present in every task;
`apt-get install` appears in the gold solutions of 41 tasks.)

Actions: `apt-get update`, `apt-get install`, `venv create`, `activate`, `pip install`,
`conda create/activate`, import/use.

Properties:
- `apt-get update` must precede `apt-get install`
- install must precede first use of the package
- venv must be activated before install, or the install lands in system python

### 3. Processes / ports / services — 94 tasks with a start verb, 23 naming a port

Ports named: 8080 (8), 8088 (7), 5000 (5), 8000/8008/8443 (4 each), 80, 443, 9000,
5901, 8888, 3000, 8333.

Actions: `nohup` (3 tasks), `service X start` (5), `nginx` (4), `tmux send-keys` (8),
`pkill` (2), `subprocess.Popen` (13 occ.), `.kill()` (9), `.terminate()` (6), `.wait()` (6).

Properties:
- bind a port already bound (repeated start / start-after-restart)
- reload or stop a service that was never started
- `Popen` without a matching `wait`/`terminate` — dangling child
- service must be running before the client request that probes it

Caveat: only 6 gold solutions contain both a start and a stop
(`blind-maze-explorer-5x5`, `blind-maze-explorer-algorithm`, `install-windows-xp`,
`play-lord`, `slurm-simple-node-monitoring`, `solana-data`). Treat leaks as warnings,
not hard violations.

### 4. Archives — 40 tasks

Actions: `7z` (5 tasks), `unzip`, `tar -xzf` / `-xf` / `xf` / `-tf`, `tarfile.open`,
`zipfile.ZipFile`, `.extractall`, `gzip.open`.

Properties: extract before reading a member path; `tar -t` (list) does not change state
while `-x` does.

### 5. Git object graph — 38 tasks

By task: `git clone` 38, `git reset` 17, `git remote` 14, `git reflog` 14, `git gc` 14,
`git checkout` 13, `git tag` 13, `git add`/`commit` 5, `git init` 4.

The only resource here with a non-trivial state machine: ref → commit → object
reachability, where **`git gc` destroys unreachable objects**. So
`gc` before `reflog`-based recovery is an irrecoverable violation — the agent cannot
repair it afterwards. Highest severity, narrowest coverage (the `reflog`/`gc` counts
concentrate in `git-leak-recovery`).

### 6. C-level memory and file handles — 12 tasks

Occurrences: `malloc` 48, `free(` 34, `fopen` 21, `fread` 17, `fclose` 17, `fwrite` 10,
`realloc` 9, `calloc` 3.

Tasks: `custom-memory-heap-crash`, `make-mips-interpreter`, `make-doom-for-mips`,
`path-tracing`, `path-tracing-reverse`, `port-compressor`, `circuit-fibsqrt`,
`gpt2-codegolf`, `build-pov-ray`, `3d-model-format-legacy`, `pytorch-model-cli`,
`modernize-fortran-build`.

Properties: alloc/free pairing, use-after-free, double free, fopen/fclose pairing.

### 7. Databases — 11 tasks

Occurrences: `.execute(` 28, `BEGIN` 13, `.fetchall(` 11, `.fetchone(` 11,
`conn.close` 9, `psycopg2.connect` 9, `conn.cursor` 9, `sqlite3.connect` 5, `PRAGMA` 5,
`CREATE TABLE` / `DROP TABLE` / `VACUUM` 1 each.

Chain: `connect → cursor → execute → commit/rollback → close`.
Tasks include `postgres-csv-clean`, `query-optimize`, `sqlite-with-gcov`,
`db-wal-recovery`, `sqlite-db-truncate`.

Despite being the obvious candidate, the smallest usable pool here. Low priority.

### 8. Locks / concurrency — 7 tasks

`flock` 23 occ. but concentrated in one task; `threading.Thread` 4,
`multiprocessing` 2, `asyncio.gather` 1. Negligible.

## Priority

paths (207) > packages (~100) > processes & ports (94) > archives (40) > git (38) >
C memory/handles (12) > DB (11) > locks (7).

Cheapest first detector, fully static, largest coverage:

1. **use-before-exist on paths** — derive s₀ path set from instruction + Dockerfile,
   scan the trace for reads whose target is in neither s₀ nor the written set.
2. **install-before-use / update-before-install** — extract package names from the
   trace, check `apt-get update` precedes `install` and `pip install X` precedes
   `import X`.

Both target the failure mode that costs turns without costing correctness: the agent
errors, sees the error, and repairs — pure overhead.

## Known blind spot

Most terminal-bench solutions are "write a script, then run it". The shell trace shows
`python solve.py`, not the `open(p, 'w')` inside it — and 486 of the 586 `open` calls
live in such scripts. The script body *is* recoverable, because the agent types it into
the terminal via `cat > solve.py <<EOF … EOF`, so it appears verbatim in `commands.txt`.
Lifting shell → embedded-source → file operations is the single highest-value extension,
and the most work.
