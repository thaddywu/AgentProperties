"""Data-only test files; execution always belongs to the installed application runner."""

from copy import deepcopy


def read_cases(value, application):
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "cases"}
        or type(value["version"]) is not int
        or value["version"] != 1
    ):
        raise ValueError("Expected a version 1 test file with cases.")
    cases = value["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
        raise ValueError("Use 1–20 test cases.")
    result, seen = [], set()
    for case in cases:
        if (
            not isinstance(case, dict)
            or not {"id", "task", "setup", "expected"} <= set(case)
            or set(case) - {"id", "task", "setup", "expected", "split", "seed"}
        ):
            raise ValueError("Each test needs id, task, setup and expected.")
        if (
            not isinstance(case["id"], str)
            or not case["id"].strip()
            or len(case["id"]) > 128
            or case["id"] in seen
        ):
            raise ValueError("Test IDs must be unique, nonempty strings.")
        seen.add(case["id"])
        if any(
            not isinstance(case[k], str) or not case[k].strip() or len(case[k]) > 4000
            for k in ("task", "expected")
        ):
            raise ValueError("Task and expected outcome must be nonempty text.")
        seed, split = case.get("seed", 42), case.get("split", "development")
        if (
            type(seed) is not int
            or not 0 <= seed < 2**31
            or split not in ("development", "heldout")
        ):
            raise ValueError("Invalid seed or test set.")
        application.validate_setup(case["setup"])
        result.append(
            dict(
                task=case["task"],
                setup=deepcopy(case["setup"]),
                expected=case["expected"],
                seed=seed,
                split=split,
                caseId=case["id"],
            )
        )
    return result


def run_cases(study, value):
    # Validate the entire file before saving or running any case. Expected results
    # remain human-written claims; they are never passed to the policy generator.
    cases = read_cases(value, study.application)
    scenarios = [study.add_scenario(case) for case in cases]
    return [pair for scenario in scenarios for pair in study.run_pair(scenario["id"])]
