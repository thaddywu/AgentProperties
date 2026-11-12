"""Portable execution-reading bundles and directly editable student judgments."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading

from policy_runtime.policy import fingerprint
from .porting.codex import artifact_text, save
from .review import review_units
from .study import Study


class BundleApplication:
    setup_fields = []
    documents = []
    runner_info = {'available': False}
    policy_origin = 'model-candidate'
    policy_hash = 'review-only'
    name = 'Policy review'

    def __init__(self, directory, policy=None, *, policy_text=None):
        self.directory = Path(directory).resolve()
        manifest = json.loads(artifact_text(self.directory, 'manifest.json'))
        identity = manifest.pop('id')
        if manifest.get('version') != 1 or fingerprint(manifest) != identity:
            raise ValueError('Execution-reading manifest changed.')
        manifest['id'] = identity
        origin = manifest.get('origin', 'model')
        if origin not in {'model', 'manual'}:
            raise ValueError('Unknown execution-reading origin.')
        self.policy_origin = 'manual-candidate' if origin == 'manual' else 'model-candidate'
        for relative, digest in manifest['assets'].items():
            content = artifact_text(self.directory, relative)
            if hashlib.sha256(content.encode()).hexdigest() != digest:
                raise ValueError('Execution-reading asset changed: ' + relative)
        app = self.directory.parent
        for relative, digest in manifest['applicationFiles'].items():
            path = app / relative
            if path.is_symlink() or not path.resolve().is_relative_to(app) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Translated implementation changed: ' + relative)
        text = Path(policy).read_text() if policy is not None else policy_text
        if not isinstance(text, str) or fingerprint(text) != manifest['policyHash']:
            raise ValueError('Selected policy differs from the policy used for translation.')
        self.binding = dict(version=1, id='student-review', predicates={})
        self.revision = fingerprint(dict(bundle=identity, policy=manifest['policyHash']))
        self.evidence = dict(sourceRevision=manifest['sourceCommit'], bundleId=identity)
        execution = json.loads(artifact_text(self.directory, 'execution.json'))
        execution['links'] = json.loads(artifact_text(self.directory, 'alignment.json'))['links']
        value = dict(version=2, origin=origin,
                     source=dict(name=Path(policy).name if policy else 'policy.md', text=text,
                                 hash=fingerprint(text), offsetUnit='unicode-code-point'),
                     contractHash=fingerprint(self.binding), requirements=[], rules=[], coverage=[], behaviors=[],
                     omittedRequirementIds=[], attempts=[], runtimeInstalled=False,
                     validation='execution-reading; human judgment required', execution=execution,
                     bundleId=identity)
        self._reference = dict(value, id=fingerprint(value))
        review_units(self._reference)  # Check every frozen sentence correspondence.

    def reference(self):
        return deepcopy(self._reference)

    def validate_setup(self, setup):
        raise ValueError('Run test scenarios using the original application and submit its trajectories.')


def blank_review(reference):
    return dict(version=1, policy_hash=reference['source']['hash'], translation_id=reference['bundleId'],
                sentences=[dict(sentence_id=u['id'], policy_text=u['quote'], rating='', categories=[],
                                note='', other_category='') for u in review_units(reference)['units']])


class StudentStudy(Study):
    """review.json is authoritative on resume; normal Save writes it atomically."""
    def __init__(self, directory, application, review_file):
        self.review_file = Path(review_file).absolute()
        if self.review_file.is_symlink():
            raise ValueError('Choose a regular review file.')
        self._submission_ready = False
        super().__init__(directory, application)
        reference = application.reference()
        self.add_review(reference)
        if self.review_file.exists():
            if self.review_file.stat().st_size > 4_000_000:
                raise ValueError('Review file exceeds the size limit.')
            self.load_submission(json.loads(self.review_file.read_text()), reference)
        self.review_file.parent.mkdir(parents=True, exist_ok=True)
        self._submission_ready = True
        self.save()

    def load_submission(self, value, reference):
        expected = blank_review(reference)
        if (not isinstance(value, dict) or set(value) != set(expected)
                or value['version'] != 1 or value['policy_hash'] != expected['policy_hash']
                or value['translation_id'] != expected['translation_id'] or not isinstance(value['sentences'], list)):
            raise ValueError('Review file belongs to another source/version or has an invalid format.')
        units = {r['sentence_id']: r for r in expected['sentences']}
        seen = set()
        # Validate all judgments using the ordinary backend rules before changing
        # state or touching the submission file. Handwritten files use that schema.
        probe = object.__new__(Study)
        probe.lock, probe.data = threading.RLock(), deepcopy(self.data)
        probe.save = lambda: None
        probe.data['judgments'][reference['id']] = {}
        for row in value['sentences']:
            if not isinstance(row, dict) or set(row) != {'sentence_id', 'policy_text', 'rating', 'categories', 'note', 'other_category'}:
                raise ValueError('Invalid sentence judgment fields.')
            identifier = row['sentence_id']
            if identifier not in units or identifier in seen or row['policy_text'] != units[identifier]['policy_text']:
                raise ValueError('Sentence judgment must match a unique original sentence.')
            seen.add(identifier)
            judgment = dict(rating=row['rating'], categories=row['categories'], note=row['note'], otherCategory=row['other_category'])
            probe.judge(reference['id'], identifier, judgment)
        self.data['judgments'][reference['id']] = probe.data['judgments'][reference['id']]

    def judge(self, review_id, requirement_id, judgment):
        with self.lock:
            before = deepcopy(self.data)
            try:
                return super().judge(review_id, requirement_id, judgment)
            except Exception:
                self.data = before
                raise

    def submission(self):
        reference = self.application.reference()
        value = blank_review(reference)
        judgments = self.data['judgments'].get(reference['id'], {})
        for row in value['sentences']:
            history = judgments.get(row['sentence_id'], [])
            if history:
                current = history[-1]
                row.update(rating=current.get('rating', ''), categories=current.get('categories', []),
                           note=current.get('note', ''), other_category=current.get('otherCategory', ''))
        return value

    def save(self):
        # Write the submission first: a failed submission save must never report
        # success merely because an internal study file was updated.
        if self._submission_ready:
            save(self.review_file, self.submission())
        super().save()
