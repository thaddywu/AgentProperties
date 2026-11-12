"""Review a copied repository without importing or executing its implementation."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import uuid

from policy_runtime.policy import fingerprint
from .codex import files, save


class RepositoryApplication:
    setup_fields = []
    documents = []
    policy_origin = 'model-candidate'
    policy_hash = 'not-installed-in-a-study-runner'
    runner_info = {'available': False}

    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.manifest = json.loads((self.directory / 'source.json').read_text())
        if files(self.directory / 'original') != self.manifest['files']:
            raise ValueError('Original source snapshot changed.')
        self.name = 'Repository review'
        self.revision = fingerprint(self.manifest)
        # Review identity stays fixed while immutable translation readings vary.
        self.binding = dict(version=1, id='repository-review', predicates={})
        self.documents = [dict(path=str(p.relative_to(self.directory / 'original')), content=p.read_text())
                          for p in (self.directory / 'original').rglob('app.md')]
        translation = self.directory / 'translation.json'
        self.evidence = dict(sourceRevision=self.manifest['revision'])
        if translation.exists():
            self.evidence['developmentChecks'] = json.loads(translation.read_text()).get('validation', {})

    def initial_review(self):
        policy = self.manifest['policy']
        text = (self.directory / 'original' / policy).read_text()
        value = dict(version=2, origin='source',
                     source=dict(name=Path(policy).name, text=text, hash=fingerprint(text), offsetUnit='unicode-code-point'),
                     contractHash=fingerprint(self.binding), requirements=[], rules=[], coverage=[],
                     behaviors=[], omittedRequirementIds=[], attempts=[], runtimeInstalled=False, validation='source-only')
        return dict(value, id=fingerprint(value))

    def reference(self):
        path = self.directory / 'review.json'
        if not path.exists():
            return self.initial_review()
        value = json.loads(path.read_text())
        if value['contractHash'] != fingerprint(self.binding):
            raise ValueError('Review binding changed.')
        pointer = json.loads((self.directory / 'backtranslation.json').read_text())
        if files(self.directory / 'candidate') != pointer['candidateFiles']:
            raise ValueError('Review is stale; candidate changed.')
        if value.get('execution', {}).get('candidateHash') != fingerprint(pointer['candidateFiles']):
            raise ValueError('Review and back-translation refer to different candidates.')
        return deepcopy(value)

    def validate_setup(self, setup):
        raise ValueError('This repository has no installed paired-study runner. Use saved development tests/trajectories.')


class PortJobs:
    """One operator-selected repo/connection; HTTP cannot choose executable paths."""
    def __init__(self, port, study):
        self.port, self.study = port, study
        self.lock = threading.Lock()
        self.path = port.output / 'job.json'
        self.state = dict(status='idle')
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state.get('status') == 'running':
                self.state['status'] = 'interrupted'
                save(self.path, self.state)

    def status(self):
        translation = self.port.output / 'translation.json'
        failed = translation.exists() and json.loads(translation.read_text()).get('status') == 'failed'
        return dict(self.state,
                    canTranslate=not translation.exists() or failed,
                    canBacktranslate=(self.port.output / 'candidate/policy_port/rules.dl').exists())

    def start(self, stage):
        if stage not in ('translate', 'backtranslate'):
            raise ValueError('Unknown translation stage.')
        if not self.lock.acquire(blocking=False):
            raise ValueError('A repository job is already running.')
        self.state = dict(id=uuid.uuid4().hex, stage=stage, status='running')
        save(self.path, self.state)

        def run():
            try:
                if stage == 'translate':
                    previous = self.port.output / 'translation.json'
                    if previous.exists() and json.loads(previous.read_text()).get('status') == 'failed':
                        result = self.port.translate(feedback=json.loads(previous.read_text())['validation'])
                    else:
                        result = self.port.translate()
                    if not result.get('passed'):
                        raise ValueError('Translation did not pass development checks.')
                    with self.study.lock:
                        self.study.data['applicationEvidence']['developmentChecks'] = result
                        self.study.save()
                else:
                    result = self.port.backtranslate()
                    if not result.get('passed'):
                        raise ValueError('Back-translation failed validation.')
                    review = self.port.review()
                    self.study.add_review(review)
                self.state = dict(self.state, status='completed')
            except Exception as error:
                save(self.port.output / ('job-failure-' + self.state['id'] + '.json'),
                     dict(type=type(error).__name__, error=str(error)))
                self.state = dict(self.state, status='failed')
            finally:
                save(self.path, self.state)
                self.lock.release()

        threading.Thread(target=run, daemon=True).start()
        return self.status()
