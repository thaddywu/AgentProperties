"""Pinned study records. Unreviewed/unknown judgments never count as successful cases."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from time import perf_counter_ns
import uuid

from policyscope.core.policy import fingerprint
from policyscope.core.validation import CATEGORIES
from .contracts import ApplicationAdapter
from policyscope.policy_viewer.review import review_units


def now():
    return datetime.now(timezone.utc).isoformat()


class Study:
    def __init__(self, directory, application: ApplicationAdapter):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.application = application
        self.lock = threading.RLock()
        self.path = self.directory / "study.json"
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if (
                self.data["applicationRevision"] != application.revision
                or self.data["contractHash"] != fingerprint(application.binding)
                or self.data.get("installedPolicyHash") != application.policy_hash
            ):
                raise ValueError("Application changed. Use a new study directory.")
        else:
            reference = application.reference()
            self.data = dict(
                version=1,
                id=uuid.uuid4().hex,
                application=application.name,
                applicationRevision=application.revision,
                contractHash=fingerprint(application.binding),
                installedPolicyHash=application.policy_hash,
                applicationEvidence=deepcopy(getattr(application, "evidence", {})),
                createdAt=now(),
                reviews=[reference],
                judgments={},
                scenarios=[],
                pairs=[],
                failures=[],
                generations=[],
            )
            self.save()
        # Derived navigation is pinned separately, preserving signed review content
        # and existing requirement-level judgments during the UI migration.
        units = self.data.setdefault("reviewUnits", {})
        for review in self.data["reviews"]:
            units.setdefault(review["id"], review_units(review))
        self.save()

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(self.data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporary, self.path)

    def export(self):
        with self.lock:
            return deepcopy(self.data)

    def add_review(self, review, usage=()):
        with self.lock:
            if review["contractHash"] != self.data["contractHash"]:
                raise ValueError("Review contract does not match this study.")
            if not any(r["id"] == review["id"] for r in self.data["reviews"]):
                self.data["reviews"].append(deepcopy(review))
                self.data["reviewUnits"][review["id"]] = review_units(review)
                self.data.setdefault("generations", []).append(
                    dict(
                        reviewId=review["id"],
                        model=deepcopy(review.get("model", {})),
                        usage=deepcopy(list(usage)),
                    )
                )
                self.save()

    def judge(self, review_id, requirement_id, judgment):
        with self.lock:
            review = next(
                (r for r in self.data["reviews"] if r["id"] == review_id), None
            )
            if not review or requirement_id not in {
                r["id"]
                for r in review["requirements"]
                + self.data["reviewUnits"][review_id]["units"]
            }:
                raise ValueError(
                    "Judgment must reference an existing review requirement."
                )
            if set(judgment) - {
                "categories",
                "support",
                "rating",
                "difference",
                "note",
                "otherCategory",
            }:
                raise ValueError("Unknown judgment field.")
            categories = judgment.get("categories", [])
            if (
                not isinstance(categories, list)
                or len(set(categories)) != len(categories)
                or any(c not in CATEGORIES for c in categories)
            ):
                raise ValueError("Invalid categories.")
            if len(categories) > 1 and "uncertain" in categories:
                raise ValueError("Uncertain is exclusive.")
            other = judgment.get("otherCategory", "")
            if not isinstance(other, str) or len(other) > 200:
                raise ValueError("Invalid custom category.")
            if "other" in categories and not other.strip():
                raise ValueError("Name the other category.")
            if (
                judgment.get("support", "")
                not in ("", "full", "partial", "unsupported", "unsure")
                or judgment.get("rating", "")
                not in (
                    "",
                    "fully_correct",
                    "partially_correct",
                    "needs_improvement",
                    "not_covered",
                    "not_policy",
                    "unsure",
                )
                or judgment.get("difference", "")
                not in ("", "missing", "stricter", "weaker", "meaning", "integration")
            ):
                raise ValueError("Invalid support or translation judgment.")
            if judgment.get("rating") == "not_policy" and categories:
                raise ValueError("Non-policy text does not need a policy category.")
            note = judgment.get("note", "")
            if not isinstance(note, str) or len(note) > 4000:
                raise ValueError("Invalid judgment note.")
            if (
                judgment.get("rating")
                in ("partially_correct", "needs_improvement", "not_covered")
                and not note.strip()
            ):
                raise ValueError("Explain what differs before saving this rating.")
            entry = dict(deepcopy(judgment), createdAt=now())
            history = (
                self.data["judgments"]
                .setdefault(review_id, {})
                .setdefault(requirement_id, [])
            )
            if (
                history
                and {k: v for k, v in history[-1].items() if k != "createdAt"}
                == judgment
            ):
                return
            history.append(entry)
            self.save()

    def add_scenario(self, scenario):
        with self.lock:
            required = {"task", "setup", "expected", "split", "seed"}
            if (
                not required <= set(scenario)
                or set(scenario) - required - {"caseId"}
                or any(
                    not isinstance(scenario[k], str)
                    or not scenario[k].strip()
                    or len(scenario[k]) > 4000
                    for k in ("task", "expected")
                )
            ):
                raise ValueError(
                    "A scenario needs task, setup, expected outcome, split and seed."
                )
            if "caseId" in scenario and (
                not isinstance(scenario["caseId"], str)
                or not scenario["caseId"].strip()
                or len(scenario["caseId"]) > 128
            ):
                raise ValueError("Invalid case ID.")
            if (
                scenario["split"] not in ("development", "heldout")
                or type(scenario["seed"]) is not int
                or not 0 <= scenario["seed"] < 2**31
            ):
                raise ValueError("Invalid scenario split or seed.")
            self.application.validate_setup(scenario["setup"])
            entry = dict(deepcopy(scenario), id=uuid.uuid4().hex, createdAt=now())
            self.data["scenarios"].append(entry)
            self.save()
            return deepcopy(entry)

    def run_pair(self, scenario_id, repetitions=1):
        if type(repetitions) is not int or not 1 <= repetitions <= 10:
            raise ValueError("Use 1–10 repetitions.")
        # Trusted runner code is selected at startup, never by documents or HTTP requests.
        with self.lock:
            scenario = next(
                (s for s in self.data["scenarios"] if s["id"] == scenario_id), None
            )
            if not scenario:
                raise ValueError("Unknown scenario.")
            scenario = deepcopy(scenario)
            pairs = []
            for trial in range(repetitions):
                pair = dict(
                    id=uuid.uuid4().hex,
                    scenarioId=scenario_id,
                    scenarioHash=fingerprint(scenario),
                    split=scenario["split"],
                    seed=scenario["seed"] + trial,
                    applicationRevision=self.application.revision,
                    policyHash=self.application.policy_hash,
                    policyOrigin=self.application.policy_origin,
                    createdAt=now(),
                    runs={},
                )
                modes = (
                    ("baseline", "protected")
                    if trial % 2 == 0
                    else ("protected", "baseline")
                )
                pair["order"] = list(modes)
                for mode in modes:
                    events = []

                    def emit(event):
                        if len(events) >= 1000:
                            raise ValueError("Trajectory exceeds the event limit.")
                        if (
                            not isinstance(event, dict)
                            or event.get("outcome")
                            not in ("executed", "blocked", "failed", "unknown")
                            or not isinstance(event.get("action"), str)
                        ):
                            raise ValueError("Invalid connector event.")
                        json.dumps(event, allow_nan=False)
                        events.append(
                            dict(
                                deepcopy(event),
                                id=uuid.uuid4().hex,
                                sequence=len(events),
                            )
                        )

                    started = perf_counter_ns()
                    try:
                        result = self.application.run(
                            deepcopy(scenario), mode, pair["seed"], emit
                        )
                        if (
                            not isinstance(result, dict)
                            or (
                                result.get("completed") is not None
                                and type(result["completed"]) is not bool
                            )
                            or any(
                                not isinstance(result.get(k), str) or not result[k]
                                for k in ("initialStateHash", "configurationHash")
                            )
                        ):
                            raise ValueError("Invalid application result.")
                        run = dict(status="completed", result=deepcopy(result))
                    except Exception:
                        run = dict(
                            status="failed",
                            error="Application runner failed; this run is not a safe outcome.",
                        )
                    pair["runs"][mode] = dict(
                        run, events=events, durationNs=perf_counter_ns() - started
                    )
                original, protected = (
                    pair["runs"][mode] for mode in ("baseline", "protected")
                )
                pair["comparable"] = all(
                    run["status"] == "completed" for run in (original, protected)
                ) and all(
                    original["result"][key] == protected["result"][key]
                    for key in ("initialStateHash", "configurationHash")
                )
                self.data["pairs"].append(pair)
                self.save()
                pairs.append(deepcopy(pair))
            return pairs

    def judge_event(self, pair_id, mode, event_id, judgment):
        with self.lock:
            pair = next((p for p in self.data["pairs"] if p["id"] == pair_id), None)
            if not pair or mode not in pair["runs"]:
                raise ValueError("Unknown run.")
            event = next(
                (e for e in pair["runs"][mode]["events"] if e["id"] == event_id), None
            )
            if (
                not event
                or set(judgment) != {"violation", "shouldAllow", "note"}
                or any(
                    judgment[k] not in ("yes", "no", "unsure")
                    for k in ("violation", "shouldAllow")
                )
                or not isinstance(judgment["note"], str)
                or len(judgment["note"]) > 4000
            ):
                raise ValueError("Invalid trajectory judgment.")
            if event["outcome"] == "blocked" and judgment["violation"] == "yes":
                raise ValueError(
                    "A blocked operation is not an executed violation; judge the attempt separately."
                )
            event.setdefault("judgments", []).append(
                dict(deepcopy(judgment), createdAt=now())
            )
            self.save()

    def judge_run(self, pair_id, mode, judgment):
        with self.lock:
            pair = next((p for p in self.data["pairs"] if p["id"] == pair_id), None)
            if (
                not pair
                or mode not in pair["runs"]
                or set(judgment) != {"completed", "note"}
                or judgment["completed"] not in ("yes", "no", "unsure")
                or not isinstance(judgment["note"], str)
                or len(judgment["note"]) > 4000
            ):
                raise ValueError("Invalid task completion judgment.")
            pair["runs"][mode].setdefault("judgments", []).append(
                dict(deepcopy(judgment), createdAt=now())
            )
            self.save()

    def summary(self):
        with self.lock:
            summaries = []
            for review in self.data["reviews"]:
                latest = {
                    k: v[-1]
                    for k, v in self.data["judgments"].get(review["id"], {}).items()
                    if v and k in {r["id"] for r in review["requirements"]}
                }
                units = self.data["reviewUnits"][review["id"]]["units"]
                sentence_latest = [
                    history[-1]
                    for unit in units
                    if (
                        history := self.data["judgments"]
                        .get(review["id"], {})
                        .get(unit["id"])
                    )
                ]
                count = len(review["requirements"])
                categories = {
                    c: sum(c in j.get("categories", []) for j in latest.values())
                    for c in CATEGORIES
                }
                ratings = {
                    r: sum(j.get("rating") == r for j in latest.values())
                    for r in (
                        "fully_correct",
                        "partially_correct",
                        "needs_improvement",
                        "unsure",
                    )
                }
                summaries.append(
                    dict(
                        reviewId=review["id"],
                        origin=review["origin"],
                        requirements=count,
                        classified=sum(
                            bool(j.get("categories")) for j in latest.values()
                        ),
                        categories=categories,
                        ratings=ratings,
                        unrated=count - sum(ratings.values()),
                        support={
                            s: sum(j.get("support") == s for j in latest.values())
                            for s in ("full", "partial", "unsupported", "unsure")
                        },
                        sentenceReview=dict(
                            method="source-sentences-v1",
                            count=len(units),
                            rated=sum(bool(j.get("rating")) for j in sentence_latest),
                            classified=sum(
                                bool(j.get("categories")) for j in sentence_latest
                            ),
                            ratings={
                                r: sum(j.get("rating") == r for j in sentence_latest)
                                for r in (
                                    "fully_correct",
                                    "partially_correct",
                                    "not_covered",
                                    "not_policy",
                                    "needs_improvement",
                                    "unsure",
                                )
                            },
                            categories={
                                c: sum(
                                    c in j.get("categories", [])
                                    for j in sentence_latest
                                )
                                for c in CATEGORIES
                            },
                        ),
                    )
                )
            runs = []
            for pair in self.data["pairs"]:
                for mode, run in pair["runs"].items():
                    rated = [
                        (e, e["judgments"][-1])
                        for e in run["events"]
                        if e.get("judgments")
                    ]
                    runs.append(
                        dict(
                            pairId=pair["id"],
                            split=pair["split"],
                            mode=mode,
                            status=run["status"],
                            comparable=pair["comparable"],
                            durationNs=run["durationNs"],
                            events=len(run["events"]),
                            humanCompletion=(run.get("judgments") or [{}])[-1].get(
                                "completed"
                            ),
                            reviewed=len(rated),
                            actualViolations=sum(
                                e["outcome"] == "executed" and j["violation"] == "yes"
                                for e, j in rated
                            ),
                            preventedAttempts=sum(
                                e["outcome"] == "blocked" and j["shouldAllow"] == "no"
                                for e, j in rated
                            ),
                            falseBlocks=sum(
                                e["outcome"] == "blocked" and j["shouldAllow"] == "yes"
                                for e, j in rated
                            ),
                            unknownOutcomes=sum(
                                e["outcome"] in ("unknown", "failed")
                                for e in run["events"]
                            ),
                            unknownJudgments=sum(
                                j["violation"] == "unsure"
                                or j["shouldAllow"] == "unsure"
                                for _, j in rated
                            ),
                        )
                    )
            return dict(
                reviews=summaries,
                runs=runs,
                translationFailures=len(self.data["failures"]),
                note="Counts retain unknown and unreviewed cases. Category counts overlap. Reference reviews and development scenarios are not model accuracy or held-out results.",
            )
