"""Independent implementation-only reverse session for an injected agent port."""

import json
import shutil
import uuid
from policyscope.core.artifacts import artifact_text, files, save
from policyscope.core.compilation import validate_rules
from .execution import READING_STYLE, validate_execution

EXCLUDED = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "archive",
    "submission",
    ".codex",
    ".claude",
    ".aws",
    ".ssh",
}


def backtranslate(port):
    candidate = port.output / "candidate"
    artifact_text(candidate, "policy_port/rules.dl")
    # A new directory/session receives implementation only, no forward artifacts.
    versions = port.output / "reverse"
    versions.mkdir(exist_ok=True)
    reverse = versions / uuid.uuid4().hex[:12]
    reverse.mkdir()
    source = reverse / "source"
    source.mkdir()
    shutil.copytree(
        port.runtime,
        reverse / "framework/policyscope",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    original_policy = json.loads((port.output / "source.json").read_text())["policy"]
    # Generated tests/debug fixtures are forward history, not implementation.
    # Keep adapter imports and its referenced configuration, not every helper
    # that happened to be written beside adapter.py during development.
    package = candidate / "policy_port"
    active = {
        p for p in (package / "adapter.py", package / "__init__.py") if p.is_file()
    }
    while True:
        code = "\n".join(p.read_text() for p in active)
        additional = {
            p
            for p in package.glob("*.py")
            if not p.name.startswith("test_") and p.stem in code
        }
        if additional <= active:
            break
        active.update(additional)
    for path in candidate.rglob("*"):
        relative = path.relative_to(candidate)
        if (
            path.is_symlink()
            or not path.is_file()
            or set(relative.parts) & (EXCLUDED | {"tests", "traces", "episodes"})
        ):
            continue
        if str(relative) == original_policy:
            continue
        if path.name.lower() in {"policy.md", "policies.md"}:
            continue
        if relative.parts[0] == "policy_port":
            if path.suffix == ".py" and path not in active:
                continue
            if path.suffix == ".json" and path.name not in code:
                continue
        system_card = path.suffix == ".md" and bool(
            set(relative.parts) & {"agents", "prompts", "system_cards"}
        )
        if (
            path.suffix
            not in {
                ".py",
                ".dl",
                ".json",
                ".toml",
                ".yaml",
                ".yml",
                ".js",
                ".ts",
                ".html",
                ".jsx",
                ".tsx",
                ".vue",
                ".svelte",
            }
            and not system_card
        ) or path.name.startswith("test_"):
            continue
        if (
            path.name
            in {
                "port.json",
                "trajectories.json",
                "report.json",
                "results.json",
                "policy-plan.json",
                "backtranslation.json",
            }
            or (
                relative.parts[0] == "policy_port"
                and path.name in {"plan.json", "translation.json"}
            )
            or path.stat().st_size > 256000
        ):
            continue
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    save(reverse / "source-manifest.json", files(source))
    (reverse / "AGENTS.md").write_text(
        "Read source/ implementation only. Do not execute application code. No subagents or network. Write only backtranslation.json and backtranslation.md. No original policy, forward plan or tests are provided.\n"
    )
    prompt = (
        READING_STYLE
        + """
Independently explain the added executable policy layer from source/policy_port and its installed hooks, using framework/policyscope for runtime semantics. Inspect application code only to establish actual input producers, bindings, explicit dependencies and unmediated paths. Do not summarize the app's existing enforcement as generated policy. Trace A input production/update, B derivation and C actual invocation permission/refusal, including every fallback allow branch. No original policy is provided. Do not name the underlying enforcement language or expose raw clauses in student-facing descriptions. Do not infer guarantees from names, prompts or comments. Expose missing producers and bypasses through their consequences for the affected action. Explain who supplies approval evidence and which gate actually requires it. Missing approval/confirmation is not a fabricated fact.
Write backtranslation.json with procedures [{id,title,ruleIds,reads:[{text,sources}],steps:[{kind,indent,text}],evidence:[{file,quote}]}], limitations and unresolvedInputs. Each step has kind A for recorded information and its sources, B for decision rules, or C for the execution boundary and permission/refusal. The UI groups these stages; omit a stage when it has no relevant content. rule1..ruleN are clause order after declarations/static facts. Cover every rule; sharing ruleIds between requirements is allowed. Sources must be from: runtime identity, tool call, application state, tool result, agent statement, static configuration, rule constant, unknown. Prefer 2–4 short steps per requirement, indent 0; avoid nested walkthroughs. Keep source and recording timing visible in steps, even though reads also summarizes inputs. Evidence file is source/relative/path or framework/policyscope/relative/path, without path traversal. Quote one exact contiguous substring, citing both input producers and conditions/effects. Also write concise backtranslation.md organized by the same requirements. Report what the code does, not what it ought to do."""
    )
    clauses = validate_rules(candidate / "policy_port/rules.dl")
    rules = [dict(r, id="rule" + str(i + 1)) for i, r in enumerate(clauses)]
    evidence = {"source/" + n: (source / n).read_text() for n in files(source)}
    evidence.update(
        {
            "framework/policyscope/" + n: (
                reverse / "framework/policyscope" / n
            ).read_text()
            for n in files(reverse / "framework/policyscope")
        }
    )
    validation = {}
    for attempt in range(3):
        code = port.session(
            reverse, prompt, f"backtranslate-{attempt}", ("source", "framework")
        )
        try:
            reading = json.loads(artifact_text(reverse, "backtranslation.json"))
            reading["procedures"] = validate_execution(reading, rules, evidence)
            if code:
                raise ValueError("Codex did not finish successfully.")
            save(reverse / "backtranslation.json", reading)
            validation = dict(
                passed=True,
                procedures=len(reading["procedures"]),
                rules=len(rules),
                originalPolicyProvided=False,
                checks="Structure/rule coverage/exact citations, not semantic equivalence.",
            )
            break
        except (ValueError, KeyError, TypeError, FileNotFoundError) as error:
            validation = dict(passed=False, error=str(error)[:1800], codexExitCode=code)
            save(reverse / f"validation-{attempt}.json", validation)
            prompt = (
                "Repair backtranslation.json only using source/ and runtime. Keep independent implementation reading. Validation error: "
                + json.dumps(validation)
            )
    save(reverse / "validation.json", validation)
    if validation["passed"]:
        save(
            port.output / "backtranslation.json",
            dict(
                directory=str(reverse.relative_to(port.output)),
                candidateFiles=files(candidate),
                validation=validation,
            ),
        )
    return validation
