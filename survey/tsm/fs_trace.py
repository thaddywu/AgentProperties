#!/usr/bin/env python3
"""
Filesystem actions from agent traces, in three separable layers.

    (A) SOURCE   raw trace -> RawStep(command, returncode, output)
                 The ONLY agent-specific layer. One reader per agent.

    (B) CLEAN    command text -> [Segment]
                 De-wrap the terminal render, strip ANSI, drop heredoc bodies and
                 inline comments, split on ; && || |. Shell-specific, agent-neutral.

    (C) MAP      Segment -> [Action]
                 Data-driven rule table. Neither agent- nor terminal-specific.

Only (C)'s output reaches a checker, so the checker never sees a tmux escape code,
a spinner frame, or a `; tmux wait -S done` suffix.

Run:
    python fs_trace.py --cast <agent.cast>            # all three layers, side by side
    python fs_trace.py --cast <agent.cast> --layer C  # just the actions
    python fs_trace.py --solution <solution.sh>
    python fs_trace.py --stats <dir>                  # yield over a directory of casts
"""

from __future__ import annotations

import argparse
import collections
import json
import posixpath
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ===========================================================================
# (A) SOURCE -- the only agent-specific code
# ===========================================================================


@dataclass
class RawStep:
    index: int
    command: str
    returncode: int | None = None
    output: str = ""
    note: str = ""


_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][B0]|\x1b[=>]")
_SPINNER = re.compile(r"^[⠀-⣿]\s*Waiting for the LM to respond\.\.\.\s*$", re.M)


def _cast_text(path: Path) -> tuple[int, str]:
    """Concatenated output stream of an asciinema v2 recording, ANSI removed.

    Returns the terminal width too: the recording is a fixed-width render, so a line
    of exactly that many characters was hard-wrapped and must be rejoined (layer B).
    """
    width = 160
    chunks: list[str] = []
    with path.open(errors="ignore") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if i == 0 and line.startswith("{"):
                try:
                    width = json.loads(line).get("width", 160)
                except Exception:
                    pass
                continue
            if not line.startswith("["):
                continue
            try:
                _, kind, data = json.loads(line)
            except Exception:
                continue
            if kind == "o":
                chunks.append(data)
    text = _ANSI.sub("", "".join(chunks)).replace("\r\n", "\n").replace("\r", "\n")
    return width, _SPINNER.sub("", text)


def read_mini_cast(path: Path) -> list[RawStep]:
    """mini-swe-agent prints its whole conversation, so every step is recoverable:

        mini-swe-agent (step 1, $0.01):
        THOUGHT: ...
        ```bash
        ls -la
        ```
        User:
        <returncode>0</returncode>
        <output>
        ...
        </output>
    """
    width, text = _cast_text(path)
    # De-wrap per block, never over the whole cast: the ``` fences and the
    # <returncode>/<output> markers sit on their own lines in the WRAPPED text, and
    # gluing a fence onto the command above it makes the block regex run away.
    steps: list[RawStep] = []
    # Blocks before the first step banner belong to the system prompt's format example.
    start = text.find("mini-swe-agent (step ")
    if start < 0:
        return steps
    body = text[start:]
    cmds = [(m.start(), m.group(1)) for m in re.finditer(r"```bash\n(.*?)\n```", body, re.S)]
    for i, (pos, cmd) in enumerate(cmds):
        tail = body[pos : cmds[i + 1][0] if i + 1 < len(cmds) else len(body)]
        rc = re.search(r"<returncode>(-?\d+)</returncode>", tail)
        out = re.search(r"<output>\n(.*?)\n?</output>", tail, re.S)
        steps.append(
            RawStep(
                index=i,
                command=_dewrap(cmd, width),
                returncode=int(rc.group(1)) if rc else None,
                output=_dewrap(out.group(1), width) if out else "",
                note="mini-swe-agent",
            )
        )
    return steps


def read_terminus_cast(path: Path) -> list[RawStep]:
    """terminus types straight into tmux, so the `i` events ARE the commands.

    Output is whatever follows until the shell prompt returns.
    """
    width = 160
    events: list[tuple[str, str]] = []
    with path.open(errors="ignore") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if i == 0 and line.startswith("{"):
                try:
                    width = json.loads(line).get("width", 160)
                except Exception:
                    pass
                continue
            if not line.startswith("["):
                continue
            try:
                _, kind, data = json.loads(line)
            except Exception:
                continue
            if kind in ("i", "o"):
                events.append((kind, data))
    steps: list[RawStep] = []
    cur: str | None = None
    buf: list[str] = []
    for kind, data in events:
        if kind == "i":
            if cur is not None:
                steps.append(_mk_terminus_step(len(steps), cur, buf, width))
            cur, buf = data, []
        elif cur is not None:
            buf.append(data)
    if cur is not None:
        steps.append(_mk_terminus_step(len(steps), cur, buf, width))
    return [s for s in steps if s.command.strip()]


_PROMPT = re.compile(r"^[\w.-]+@[\w.-]+:[^\n#$]*[#$]\s*$", re.M)


def _mk_terminus_step(i: int, cmd: str, buf: list[str], width: int) -> RawStep:
    out = _ANSI.sub("", "".join(buf)).replace("\r\n", "\n").replace("\r", "\n")
    out = _PROMPT.sub("", _dewrap(out, width))
    return RawStep(index=i, command=_ctrl(cmd), output=out.strip(), note="terminus")


def _ctrl(s: str) -> str:
    """Control keystrokes are not commands; a trailing CR is just Enter."""
    if s.strip() in ("\x04", "\x03", "\x1b"):
        return ""
    return s.replace("\r", "").replace("\n", "")


def read_solution_sh(path: Path) -> list[RawStep]:
    """The gold script, replayed offline. No observations: specificity testing only."""
    return [RawStep(index=0, command=path.read_text(errors="ignore"), note="solution.sh")]


SOURCES = {
    "mini": read_mini_cast,
    "terminus": read_terminus_cast,
    "solution": read_solution_sh,
    "empty": lambda _p: [],
}


def sniff(path: Path) -> str:
    """Which reader handles this recording, or "empty" if no agent ever ran.

    162 of the 333 leaderboard trials are agent-INSTALL failures -- the cast holds
    apt-get noise and then `bash: mini: command not found`. Falling back to the
    terminus reader on those picks up the harness's own bookkeeping (`source
    /installed-agent/...`) and reports them as usable, which inflates the trace count
    by almost 2x. They must be counted as empty.
    """
    if path.suffix == ".sh":
        return "solution"
    _, text = _cast_text(path)
    if "mini-swe-agent (step " in text:
        return "mini"
    if "/installed-agent/" in text:
        return "empty"  # an installed agent was launched; it left no recoverable steps
    return "terminus"


# ===========================================================================
# (B) CLEAN -- shell-level, agent-neutral
# ===========================================================================


@dataclass
class Segment:
    text: str
    step: int
    heredoc_target: str | None = None  # `cat > f <<EOF` keeps f after the body is cut
    piped: bool = False                # inside a pipeline: a cd here is not durable
    subshell_open: int = 0             # leading `(` count
    subshell_close: int = 0            # trailing `)` count
    dropped: list[str] = field(default_factory=list)


def _dewrap(text: str, width: int) -> str:
    """Undo the terminal's soft wrapping.

    Matching `len(line) == width` does not work: mini-swe-agent renders through rich,
    which wraps at a WORD boundary, so observed break points scatter (149, 157, 159,
    160 in one file). The reliable test is the wrap rule itself -- a line is a
    continuation when its first word could not have fitted on the previous line.
    Rich keeps the trailing space, so the join needs no separator.
    """
    out: list[str] = []
    for line in text.split("\n"):
        prev = out[-1] if out else ""
        if prev and len(prev) > width * 0.6:
            first = line.split(" ", 1)[0]
            if first and len(prev) + len(first) > width - 1:
                out[-1] = prev + line
                continue
        out.append(line)
    return "\n".join(out)


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _strip_heredocs(cmd: str) -> tuple[str, str | None]:
    """Drop heredoc bodies -- they are arbitrary text that looks like commands.

    161 of 233 terminal-bench gold solutions write scripts this way; leaving the
    bodies in makes `print` and `def` look like shell verbs.

    Only the `<<TERM` token is removed, NOT the rest of its line: agents write
    `cat <<'EOF' > out.py` at least as often as `cat > out.py <<'EOF'`, and cutting
    the line at `<<` threw away the redirection that names the file being created.
    That one slip hid 663 CREATE actions across the 333 leaderboard traces.
    """
    out: list[str] = []
    term: str | None = None
    for line in cmd.split("\n"):
        if term is not None:
            if line.strip() == term:
                term = None
            continue
        m = _HEREDOC.search(line)
        if m:
            term = m.group(2)
            out.append(line[: m.start()] + line[m.end() :])
            continue
        out.append(line)
    return "\n".join(out), None


_QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")


def _mask(s: str) -> str:
    """Blank out quoted spans so separators and `#` inside them are not seen."""
    return _QUOTED.sub(lambda m: "\x00" * len(m.group(0)), s)


def _split_ops(s: str) -> list[tuple[str, bool]]:
    """Split on ; \\n | & && || outside quotes.

    Each part carries `piped`: whether it sits in a pipeline. A `cd` inside a pipeline
    runs in a subshell, so it must not move the parent's cwd -- `cd d | cat x` reads
    x relative to the ORIGINAL directory.

    `||` is treated like `&&`, which is wrong: only one branch of `a || b` actually
    runs. Deciding which needs a per-segment exit code, and traces carry one exit code
    per step, so both branches are walked. Declared approximation.
    """
    masked = _mask(s)
    parts: list[tuple[str, bool]] = []
    start = 0
    i = 0
    prev_pipe = False
    while i < len(masked):
        c = masked[i]
        if c in ";\n|&":
            two = masked[i : i + 2]
            n = 2 if two in ("&&", "||") else 1
            is_pipe = c == "|" and two != "||"
            parts.append((s[start:i], prev_pipe or is_pipe))
            prev_pipe = is_pipe
            i += n
            start = i
            continue
        i += 1
    parts.append((s[start:], prev_pipe))
    return [(t, p) for t, p in ((x.strip(), p) for x, p in parts) if t]


def _strip_comment(s: str) -> str:
    masked = _mask(s)
    i = masked.find("#")
    while i > 0 and masked[i - 1] not in " \t":
        i = masked.find("#", i + 1)
    if i == 0 or (i > 0 and masked[i - 1] in " \t"):
        return s[:i].rstrip()
    return s


# Harness bookkeeping that is not part of what the agent decided to do.
_NOISE = (
    re.compile(r";?\s*tmux wait -S \w+\s*$"),
    re.compile(r"^\s*(clear|exit|true|:)\s*$"),
    re.compile(r"^\s*asciinema rec\b"),
    re.compile(r"^\s*source /installed-agent/"),
    re.compile(r"^\s*echo\s+'?INSTALL_SUCCESS'?\s*$"),
)


def clean(step: RawStep) -> list[Segment]:
    cmd, _ = _strip_heredocs(step.command)
    heredoc_target = None
    m = re.search(r">\s*([^\s<>|&;]+)[^<]*<<-?\s*['\"]?[A-Za-z_]", step.command)
    if m:
        heredoc_target = m.group(1)

    segs: list[Segment] = []
    for raw, piped in _split_ops(cmd):
        text = _strip_comment(raw).strip()
        # `( cd /tmp && touch z )` -- the group runs in a subshell. Count the parens
        # so the walker can restore cwd, and strip them so they do not end up glued
        # to a path (`touch z)` was resolving to a path literally ending in `)`).
        opens = len(text) - len(text.lstrip("( "))
        text = text.lstrip("( ")
        closes = len(text) - len(text.rstrip(") "))
        text = text.rstrip(") ")
        # `2>&1` leaves a bare `1` behind once the redirection is split off, and a
        # line continuation leaves a bare `\`. Neither is a command.
        if text in ("1", "2", "\\", "&", "-"):
            continue
        if not text:
            continue
        text = _NOISE[0].sub("", text).strip()
        if not text or any(p.search(text) for p in _NOISE[1:]):
            continue
        segs.append(Segment(text=text, step=step.index, heredoc_target=heredoc_target,
                            piped=piped, subshell_open=opens, subshell_close=closes))
        heredoc_target = None  # belongs to the first segment only
    return segs


# ===========================================================================
# (C) MAP -- neither agent- nor terminal-specific
# ===========================================================================

CREATE, READ, DELETE, STAT, LIST, EXEC, CHDIR, UNRESOLVED = (
    "CREATE",
    "READ",
    "DELETE",
    "STAT",  # existence probe: legal in EVERY state, including ABSENT
    "LIST",  # directory enumeration: legal anywhere, and yields negative information
    "EXEC",
    "CHDIR",
    "UNRESOLVED",
)

# STAT exists because `ls -la p` does not consume p, it asks whether p is there.
# Probing a path the agent just deleted is correct behaviour -- agents routinely
# verify a deletion with `ls p 2>/dev/null || echo gone`. Folding that into READ
# turns every cleanup task into a false use-after-delete.


@dataclass(frozen=True)
class Action:
    op: str
    path: str | None
    step: int
    raw: str
    rule: str


@dataclass(frozen=True)
class Rule:
    """One row of the mapping table.

    cmds        argv[0] values this rule fires on
    op          abstract action emitted for each selected path
    pick        which arguments name paths: "all" | "first" | "last" | "none"
    takes_value flags whose following token is a VALUE, not a path. Without this,
                `shred -n 3` yields a path `3` and `--cipher-algo AES256` yields
                `AES256`; both were observed in real traces.
    out_flags   flags whose following token is CREATED rather than read
    note        provenance -- why this row says what it says
    """

    cmds: frozenset[str]
    op: str
    pick: str = "all"
    takes_value: frozenset[str] = frozenset()
    out_flags: frozenset[str] = frozenset()
    note: str = ""


# Measured over 233 gold solutions and 333 leaderboard traces; see terminalbench.md.
RULES: tuple[Rule, ...] = (
    Rule(frozenset({"cd", "pushd"}), CHDIR, "first", "cwd move; 51 tasks use it"),
    # `ls` is BOTH a probe (never violates) and an enumeration (grows the ledger).
    # Those are orthogonal; giving it only the first made every path the agent had
    # merely listed look invented.
    Rule(frozenset({"ls", "find", "tree"}), LIST, "all",
         note="enumerates; never violates, and admits the subtree to the ledger"),
    Rule(frozenset({"stat", "file", "du", "test", "realpath", "readlink"}), STAT,
         "all", note="asks whether one path is there; never consumes it"),
    Rule(frozenset({"cat", "less", "more", "md5sum", "sha256sum", "nl", "od", "xxd",
                    "diff", "sort", "uniq", "cut", "jq", "awk"}), READ, "all",
         takes_value=frozenset({"-d", "-f", "-t", "-k", "-w"}),
         note="consume an existing path"),
    Rule(frozenset({"head", "tail"}), READ, "all",
         takes_value=frozenset({"-n", "-c"}), note="line/byte count is not a path"),
    Rule(frozenset({"grep", "rg", "egrep"}), READ, "last",
         takes_value=frozenset({"-e", "-m", "-A", "-B", "-C", "--include", "--exclude"}),
         note="first non-flag argument is the pattern, not a path"),
    Rule(frozenset({"wc"}), READ, "all", takes_value=frozenset(), note=""),
    Rule(frozenset({"mkdir", "touch"}), CREATE, "all", note="create; mkdir in 38 tasks"),
    # cp/mv have no primitive of their own; the block below rewrites them into
    # READ(source) + CREATE(destination) [+ DELETE(source)]. They still need a row
    # here or the rule lookup drops them before that block is reached.
    Rule(frozenset({"cp", "mv", "install"}), READ, "all",
         takes_value=frozenset({"-t", "--target-directory", "-m", "-S"}),
         note="compound; rewritten below"),
    Rule(frozenset({"rm", "rmdir", "unlink"}), DELETE, "all",
         note="delete; rm in 22 tasks"),
    Rule(frozenset({"shred"}), READ, "all", takes_value=frozenset({"-n", "-s"}),
         note="overwrites in place; the removal is a separate rm"),
    Rule(frozenset({"chmod", "chown", "chgrp"}), READ, "all",
         note="requires existence, changes only metadata"),
    Rule(frozenset({"gpg"}), READ, "all",
         takes_value=frozenset({"--cipher-algo", "--compress-algo", "--passphrase-fd",
                                "--passphrase", "--recipient", "-r"}),
         out_flags=frozenset({"--output", "-o"}),
         note="--output names a file it CREATES; the algo flags take bare values"),
    Rule(frozenset({"python", "python3", "bash", "sh", "node", "perl", "ruby"}), EXEC,
         "first", takes_value=frozenset({"-c", "-m"}),
         note="runs a script whose own writes are invisible at this layer"),
    Rule(frozenset({"unzip", "7z", "gunzip"}), READ, "first",
         note="reads the archive; members are only known from the output"),
    Rule(frozenset({"sed"}), READ, "last", takes_value=frozenset({"-e", "-f"}),
         note="in-place edit is read-modify-write"),
)

# tar's direction lives in the mode characters, not in the command name:
#   c = create the archive   x = extract from it   t = list it
# and -f names the archive either way. Handled as a special case rather than a Rule
# because one command name maps to two different ops.
_TAR_VALUE_FLAGS = frozenset({"-f", "--file", "-C", "--directory", "-T"})

_BY_CMD: dict[str, Rule] = {c: r for r in RULES for c in r.cmds}

# Wrappers that run another command; strip and re-dispatch on what follows.
PREFIXES = {"sudo", "timeout", "env", "nohup", "time", "stdbuf", "xargs", "nice"}

# Commands that touch no path, listed explicitly so that anything neither here nor in
# RULES is a genuine gap in the table rather than a silent drop. Mirrors
# `Fsm.stateless_ops` in typestate.py.
STATELESS = frozenset({
    "echo", "printf", "pwd", "which", "whoami", "date", "sleep", "true", "false",
    "export", "set", "unset", "alias", "read", "test", "expr", "seq", "yes",
    "pip", "pip3", "apt", "apt-get", "conda", "npm", "uv", "cargo", "go", "git",
    "curl", "wget", "ps", "kill", "pkill", "top", "df", "free", "uname", "id",
    "mini", "tmux", "man", "help", "history", "clear", "exit",
})

# Paths we never judge: the base image ships tens of thousands of them, and 194 of the
# 207 instruction-named paths live under /app. Judging outside that drowns in noise.
IN_SCOPE = ("/app", "/opt", "/srv", "/data", "/testbed", "/root", "/tmp", "/home")
_SYSTEM = ("/usr", "/etc", "/bin", "/sbin", "/lib", "/var", "/proc", "/sys", "/dev", "/boot")

_UNRESOLVABLE = re.compile(r"[*?\[\]]|\$\(|\$\{|\$[A-Za-z_]|`")


def _argv(text: str) -> list[str]:
    """Split on whitespace outside quotes, then unquote. Redirections are removed
    first because they belong to the segment, not to the command's arguments."""
    text = re.sub(r"\d?>>?\s*[^\s<>|&;]+", " ", text)
    text = re.sub(r"<\s*[^\s<>|&;]+", " ", text)
    masked = _mask(text)
    out, start = [], 0
    for i, c in enumerate(masked):
        if c.isspace():
            if i > start:
                out.append(text[start:i])
            start = i + 1
    if start < len(text):
        out.append(text[start:])
    return [w.strip("'\"") for w in out if w]


def _resolve(p: str, cwd: str) -> str | None:
    if _UNRESOLVABLE.search(p):
        return None
    if not p.startswith("/"):
        p = posixpath.join(cwd, p)
    return posixpath.normpath(p)


def in_scope(path: str | None) -> bool:
    return bool(path) and path.startswith(IN_SCOPE) and not path.startswith(_SYSTEM)


def _operands(rest, takes_value, out_flags, emit):
    """Drop flags and the values they consume; emit CREATE for output flags.

    `--flag=value` needs no lookahead. A bundled short flag (`-vfz`) is treated as
    boolean, which is why value-taking short flags must be written separately in the
    rule table -- the common real-world spellings (`-n 3`, `-o out`) are.
    """
    args: list[str] = []
    skip = False
    for i, tok in enumerate(rest):
        if skip:
            skip = False
            continue
        if tok.startswith("-") and tok != "-":
            head = tok.split("=", 1)[0]
            if head in out_flags:
                if "=" in tok:
                    emit(CREATE, tok.split("=", 1)[1], f"{head} names an output")
                elif i + 1 < len(rest):
                    emit(CREATE, rest[i + 1], f"{head} names an output")
                    skip = True
            elif head in takes_value and "=" not in tok:
                skip = True
            continue
        args.append(tok)
    return args


def _tar(argv: list[str], seg: Segment, emit) -> list[Action]:
    """`tar -czf out.tgz src/` CREATES; `tar -xf a.tgz` and `-tf` READ."""
    rest = argv[1:]
    modes = "".join(a.lstrip("-") for a in rest if a.startswith("-") and not a.startswith("--"))
    creating = "c" in modes
    archive = None
    change_dir = None  # -C DIR: members are relative to DIR, not to the shell's cwd
    operands: list[str] = []
    skip = False
    for i, tok in enumerate(rest):
        if skip:
            skip = False
            continue
        if tok.startswith("-"):
            head = tok.split("=", 1)[0]
            if head in ("-C", "--directory"):
                change_dir = tok.split("=", 1)[1] if "=" in tok else rest[i + 1] if i + 1 < len(rest) else None
                skip = "=" not in tok
            elif head in _TAR_VALUE_FLAGS or ("f" in tok and not tok.startswith("--")):
                if i + 1 < len(rest):
                    archive = rest[i + 1]
                skip = True
            continue
        operands.append(tok)
    if archive is None and operands:
        archive, operands = operands[0], operands[1:]
    if archive:
        emit(CREATE if creating else READ, archive, f"tar {'c' if creating else 'x/t'} -> archive")
    for o in operands:
        emit(READ, posixpath.join(change_dir, o) if change_dir and not o.startswith("/") else o,
             "tar member source" + (" (relative to -C)" if change_dir else ""))
    return []


def to_actions(seg: Segment, cwd: str) -> tuple[list[Action], str]:
    """Returns the actions for one segment and the cwd that follows it."""
    acts: list[Action] = []

    def emit(op: str, raw_path: str, rule: str) -> None:
        p = _resolve(raw_path, cwd)
        acts.append(Action(op if p else UNRESOLVED, p, seg.step, seg.text, rule))

    # A redirection creates its target no matter which command produced the bytes.
    for m in re.finditer(r"(?<![0-9<>])>>?\s*([^\s<>|&;]+)", _mask(seg.text)):
        tgt = seg.text[m.start(1) : m.end(1)]
        emit(CREATE, tgt, "redirection")
    if seg.heredoc_target:
        emit(CREATE, seg.heredoc_target, "heredoc target")

    argv = _argv(seg.text)
    while argv and posixpath.basename(argv[0]) in PREFIXES:
        # `timeout 30 python3 x.py` -- drop the wrapper and any bare numeric argument
        # it consumes, then dispatch on the real command.
        argv = argv[1:]
        while argv and re.fullmatch(r"[\d.]+[smhd]?", argv[0]):
            argv = argv[1:]
    if not argv:
        return acts, cwd
    cmd = posixpath.basename(argv[0])
    if cmd in (".", "source"):
        cmd = "bash"  # sourcing reads the script the same way running it does

    if cmd in STATELESS:
        return acts, cwd

    if cmd == "tar":
        _tar(argv, seg, emit)
        return acts, cwd

    rule = _BY_CMD.get(cmd)
    if rule is None:
        if argv[0].startswith(("./", "/")):
            emit(EXEC, argv[0], "bare executable")
        return acts, cwd

    args = _operands(argv[1:], rule.takes_value, rule.out_flags, emit)
    if rule.op == CHDIR:
        nxt = _resolve(args[0], cwd) if args else cwd
        emit(CHDIR, args[0] if args else cwd, "cd")
        # A cd inside a pipeline happens in a subshell and dies with it.
        return acts, cwd if seg.piped else (nxt or cwd)
    if not args:
        if rule.op in (LIST, STAT):
            emit(rule.op, cwd, "bare -> cwd")
        return acts, cwd

    picked = {"all": args, "first": args[:1], "last": args[-1:], "none": []}[rule.pick]
    for a in picked:
        emit(rule.op, a, f"{cmd} -> {rule.op}")

    # cp/mv are compounds, spelled out rather than given their own primitive.
    if cmd in ("cp", "mv") and len(args) >= 2:
        acts.clear()
        emit(READ, args[0], f"{cmd} source")
        emit(CREATE, args[-1], f"{cmd} destination")
        if cmd == "mv":
            emit(DELETE, args[0], "mv removes its source")
    return acts, cwd


# ===========================================================================
# Pipeline
# ===========================================================================


def pipeline(path: Path, source: str | None = None, cwd: str = "/app"):
    reader = SOURCES[source or sniff(path)]
    for step in reader(path):
        for seg in clean(step):
            acts, cwd = to_actions(seg, cwd)
            yield step, seg, acts


# ===========================================================================
# CLI
# ===========================================================================


def _show(path: Path, layer: str, source: str | None) -> None:
    reader = SOURCES[source or sniff(path)]
    steps = reader(path)
    print(f"# {path}\n# source={source or sniff(path)}  steps={len(steps)}\n")
    cwd = "/app"
    for step in steps:
        if layer in ("A", "all"):
            rc = "" if step.returncode is None else f"  rc={step.returncode}"
            print(f"[A] step {step.index}{rc}\n    {step.command.strip()[:300]!r}")
        for seg in clean(step):
            if layer in ("B", "all"):
                print(f"    [B] {seg.text[:160]}")
            acts, cwd = to_actions(seg, cwd)
            for a in acts:
                if layer in ("C", "all"):
                    scope = "" if in_scope(a.path) else "   (out of scope)"
                    print(f"        [C] {a.op:10s} {a.path}{scope}    <- {a.rule}")
        if layer == "all":
            print()


def _stats(root: Path) -> None:
    casts = sorted(root.rglob("agent.cast"))
    tot = collections.Counter()
    ops = collections.Counter()
    unmatched = collections.Counter()
    for c in casts:
        try:
            src = sniff(c)
            steps = SOURCES[src](c)
        except Exception:
            tot["unreadable"] += 1
            continue
        tot["casts"] += 1
        if not steps:
            tot["casts_with_no_steps"] += 1
            continue
        tot["casts_usable"] += 1
        cwd = "/app"
        for step in steps:
            tot["steps"] += 1
            if step.returncode not in (None, 0):
                tot["failed_steps"] += 1
            for seg in clean(step):
                tot["segments"] += 1
                acts, cwd = to_actions(seg, cwd)
                if not acts:
                    # Three reasons a segment yields nothing, and only the last is a
                    # defect: the command touches no path (STATELESS), it is known
                    # but was given no path operand (`python3 -c ...`), or the
                    # mapping table has no row for it.
                    argv = _argv(seg.text)
                    head = posixpath.basename(argv[0]) if argv else "?"
                    while head in PREFIXES and len(argv) > 1:
                        argv = argv[1:]
                        head = posixpath.basename(argv[0])
                    if head in STATELESS:
                        tot["stateless"] += 1
                    elif head in _BY_CMD or head in ("tar", ".", "source"):
                        tot["no_path_operand"] += 1
                    else:
                        unmatched[head] += 1
                for a in acts:
                    ops[a.op] += 1
                    if in_scope(a.path):
                        ops[a.op + " (in scope)"] += 1
    print(f"casts {tot['casts']}  usable {tot['casts_usable']}  "
          f"empty {tot['casts_with_no_steps']}  unreadable {tot['unreadable']}")
    print(f"steps {tot['steps']}  failed {tot['failed_steps']}  segments {tot['segments']}")
    print("\nactions")
    for k, n in ops.most_common():
        print(f"   {n:6d}  {k}")
    print(f"\nsegments producing no action:"
          f"  stateless {tot['stateless']}  no-path-operand {tot['no_path_operand']}"
          f"  UNMATCHED {sum(unmatched.values())}")
    for k, n in unmatched.most_common(25):
        print(f"   {n:6d}  {k}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cast", type=Path)
    g.add_argument("--solution", type=Path)
    g.add_argument("--stats", type=Path, help="directory to walk for agent.cast")
    ap.add_argument("--layer", default="all", choices=["A", "B", "C", "all"])
    ap.add_argument("--source", choices=sorted(SOURCES))
    a = ap.parse_args(argv)

    if a.stats:
        _stats(a.stats)
    else:
        _show(a.cast or a.solution, a.layer, a.source or (None if a.cast else "solution"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
