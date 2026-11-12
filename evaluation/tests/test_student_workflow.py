"""Offline integration of publication, external policy reading and real Save."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from policy_evaluation.porting.codex import CodexPort, files, save
from policy_evaluation.porting.repository import RepositoryApplication
from policy_evaluation.porting.student import check_base, clean_candidate, load_connection, publish, run
from policy_evaluation.review import review_units
from policy_evaluation.student_review import BundleApplication, StudentStudy


class StudentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / 'base'
        self.base.mkdir()
        (self.base / 'policy.md').write_text('Only the reviewer may approve an operation.\nThe application helps a user organize work.\n')
        (self.base / 'app.md').write_text('A synthetic review app.')
        (self.base / 'app.py').write_text('def run(): return True\n')
        subprocess.run(['git', 'init', '-q', str(self.base)], check=True)
        subprocess.run(['git', '-C', str(self.base), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.base), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '-qm', 'fixture'], check=True)
        self.target = self.root / 'enforced'
        self.port = CodexPort(self.root / 'audit', dict(baseUrl='http://127.0.0.1/v1', modelId='fixture'), codex='true')
        self.port.prepare(self.base)
        package = self.port.output / 'candidate/policy_port'
        package.mkdir()
        (package / 'adapter.py').write_text('def observe(): return []\n')
        (package / 'rules.dl').write_text('Allow(Q) :- Request(Q,"reviewer","approve").\n')
        reverse = self.port.output / 'reverse/fixture'
        reverse.mkdir(parents=True)
        manifest = {n: h for n, h in files(self.port.output / 'candidate').items() if n.endswith(('.py', '.dl'))}
        save(reverse / 'source-manifest.json', manifest)
        (reverse / 'backtranslation.md').write_text('The reviewer may approve an operation.\n')
        reference = RepositoryApplication(self.port.output).initial_review()
        units = review_units(reference)['units']
        reference['execution'] = dict(version=1, procedures=[dict(id='approve', title='Approve an operation', ruleIds=['rule1'],
            reads=[dict(text='The actor bound to the current request.', sources=['runtime identity'])],
            steps=[dict(indent=0, text='Allow approval when the actor is the reviewer.')], evidence=[])],
            links=[dict(sentenceId=u['id'], procedureIds=['approve'] if i == 0 else []) for i, u in enumerate(units)])
        save(self.port.output / 'review.json', reference)
        save(self.port.output / 'backtranslation.json', dict(directory='reverse/fixture', candidateFiles=files(self.port.output / 'candidate'),
             validation=dict(passed=True)))

    def tearDown(self):
        self.temp.cleanup()

    def export(self):
        clean = self.port.output / 'publish'
        clean_candidate(self.port.output / 'candidate', clean)
        publish(self.port, self.target, clean, (self.base / 'policy.md').read_text())
        return BundleApplication(self.target / 'back-translation', self.base / 'policy.md')

    def test_two_directories_keep_original_branch_and_source_untouched(self):
        before = files(self.base)
        branch = subprocess.check_output(['git', '-C', str(self.base), 'branch', '--show-current'])
        check_base(self.base, self.target)
        app = self.export()
        self.assertEqual(files(self.base), before)
        self.assertEqual(subprocess.check_output(['git', '-C', str(self.base), 'branch', '--show-current']), branch)
        self.assertFalse((self.target / 'policy.md').exists())
        self.assertFalse((self.target / '.git').exists())
        self.assertTrue((self.target / 'app.py').exists())
        self.assertTrue((self.target / 'review.json').exists())
        self.assertEqual(len(review_units(app.reference())['units']), 2)
        for path in (self.target / 'back-translation').glob('*.json'):
            self.assertNotIn((self.base / 'policy.md').read_text(), path.read_text())

    def test_export_preserves_structured_limitations_with_source_evidence(self):
        path = self.port.output / 'review.json'
        reference = json.loads(path.read_text())
        evidence = [dict(file='source/app.py', quote='def run(): return True')]
        reference['execution']['limitations'] = [dict(text='No external identity check is installed.', evidence=evidence)]
        save(path, reference)
        app = self.export()
        limitation = app.reference()['execution']['limitations'][0]
        self.assertEqual(limitation['text'], 'No external identity check is installed.')
        self.assertEqual(limitation['evidence'], evidence)

    def test_manual_reading_is_not_reported_as_model_output(self):
        self.export()
        manifest_path = self.target / 'back-translation/manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest.pop('id')
        manifest['origin'] = 'manual'
        manifest.pop('model', None)
        from policy_runtime.policy import fingerprint
        manifest['id'] = fingerprint(manifest)
        save(manifest_path, manifest)
        app = BundleApplication(self.target / 'back-translation', self.base / 'policy.md')
        self.assertEqual(app.reference()['origin'], 'manual')
        self.assertEqual(app.policy_origin, 'manual-candidate')

    def test_source_must_be_clean_and_target_must_not_be_overwritten(self):
        (self.base / 'app.py').write_text('local changes')
        with self.assertRaises(ValueError):
            check_base(self.base, self.target)
        self.target.mkdir()
        (self.target / 'existing.txt').write_text('keep')
        with self.assertRaises(ValueError):
            check_base(self.base, self.target)
        self.assertEqual((self.target / 'existing.txt').read_text(), 'keep')

    def test_existing_document_names_can_be_selected_without_rewriting_them(self):
        subprocess.run(['git', '-C', str(self.base), 'mv', 'app.md', 'requirements.md'], check=True)
        subprocess.run(['git', '-C', str(self.base), 'mv', 'policy.md', 'policies.md'], check=True)
        subprocess.run(['git', '-C', str(self.base), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '-qm', 'original document names'], check=True)
        before = files(self.base)
        with self.assertRaises(ValueError):
            check_base(self.base, self.target)
        self.assertEqual(check_base(self.base, self.target, policy='policies.md', app_doc='requirements.md'),
                         (self.base, self.target))
        self.assertEqual(files(self.base), before)

    def test_save_resume_and_manual_file_edits_use_same_submission(self):
        app = self.export()
        path = self.target / 'review.json'
        study = StudentStudy(self.root / 'study', app, path)
        reference = app.reference()
        units = review_units(reference)['units']
        study.judge(reference['id'], units[0]['id'], dict(rating='partially_correct', categories=['permission'], note='Missing a scope restriction.'))
        disk = json.loads(path.read_text())
        self.assertEqual(disk['sentences'][0]['rating'], 'partially_correct')
        disk['sentences'][1]['rating'] = 'not_policy'
        save(path, disk)
        resumed = StudentStudy(self.root / 'study', app, path)
        self.assertEqual(resumed.submission()['sentences'][1]['rating'], 'not_policy')
        self.assertEqual(resumed.submission()['sentences'][0]['note'], 'Missing a scope restriction.')

    def test_wrong_policy_or_modified_reading_cannot_reuse_judgments(self):
        app = self.export()
        path = self.target / 'review.json'
        saved = path.read_text()
        (self.base / 'policy.md').write_text('Different intent.')
        with self.assertRaises(ValueError):
            BundleApplication(self.target / 'back-translation', self.base / 'policy.md')
        self.assertEqual(path.read_text(), saved)
        manifest = self.target / 'back-translation/execution.json'
        manifest.write_text('{}')
        with self.assertRaises(ValueError):
            BundleApplication(self.target / 'back-translation', policy_text=app.reference()['source']['text'])

    def test_invalid_manual_judgment_and_failed_save_preserve_previous_file(self):
        app = self.export()
        path = self.target / 'review.json'
        study = StudentStudy(self.root / 'study', app, path)
        saved = path.read_text()
        units = review_units(app.reference())['units']
        before = deepcopy(study.data)
        with patch('policy_evaluation.student_review.save', side_effect=PermissionError('read only')):
            with self.assertRaises(PermissionError):
                study.judge(app.reference()['id'], units[0]['id'], dict(rating='fully_correct', categories=['permission']))
        self.assertEqual(study.data, before)
        self.assertEqual(path.read_text(), saved)
        value = json.loads(saved)
        value['sentences'][0]['rating'] = 'partially_correct'
        save(path, value)
        with self.assertRaises(ValueError):
            StudentStudy(self.root / 'study', app, path)
        self.assertEqual(json.loads(path.read_text())['sentences'][0]['rating'], 'partially_correct')

    def test_connection_defaults_and_explicit_model_override(self):
        path = self.root / 'connection.json'
        save(path, dict(apiKey='synthetic-key'))
        settings = load_connection(path)
        self.assertEqual(settings['modelId'], 'gpt-6.1-sol')
        self.assertEqual(settings['reasoningEffort'], 'medium')
        save(path, dict(modelId='local-model', baseUrl='http://127.0.0.1/v1'))
        self.assertEqual(load_connection(path)['modelId'], 'local-model')

    def test_environment_connection_and_explicit_file_precedence(self):
        with patch.dict(os.environ, {'POLICY_API_KEY': 'synthetic-environment-key'}, clear=True):
            settings = load_connection()
            self.assertEqual(settings['apiKey'], 'synthetic-environment-key')
            self.assertEqual(settings['modelId'], 'gpt-6.1-sol')
            self.assertEqual(settings['reasoningEffort'], 'medium')
        with patch.dict(os.environ, {'POLICY_API_KEY': 'synthetic-environment-key',
                                    'POLICY_MODEL_ID': 'local-model', 'POLICY_REASONING_EFFORT': 'high',
                                    'POLICY_BASE_URL': 'http://127.0.0.1/v1'}, clear=True):
            self.assertEqual(load_connection()['modelId'], 'local-model')
            self.assertEqual(load_connection()['reasoningEffort'], 'high')
            self.assertEqual(load_connection()['baseUrl'], 'http://127.0.0.1/v1')
            path = self.root / 'explicit.json'
            save(path, dict(apiKey='synthetic-file-key', modelId='file-model'))
            self.assertEqual(load_connection(path)['apiKey'], 'synthetic-file-key')
            self.assertEqual(load_connection(path)['modelId'], 'file-model')
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                load_connection()
        with patch.dict(os.environ, {'POLICY_API_KEY': 'synthetic-key', 'POLICY_MODEL_ID': ''}, clear=True):
            with self.assertRaises(ValueError):
                load_connection()
        with patch.dict(os.environ, {'POLICY_API_KEY': 'synthetic\ninvalid-key'}, clear=True):
            with self.assertRaises(ValueError) as error:
                load_connection()
            self.assertNotIn('synthetic', str(error.exception))

    def test_entry_orchestrates_forward_publication_check_reverse_and_alignment(self):
        stages = []

        def check(name, *, source):
            stages.append('check')
            self.assertFalse((source / 'policy.md').exists())
            return dict(passed=True)

        with patch('policy_evaluation.porting.student.CodexPort', return_value=self.port), \
             patch.object(self.port, 'prepare'), \
             patch.object(self.port, 'translate', side_effect=lambda *a, **k: stages.append('translate') or dict(passed=True)), \
             patch.object(self.port, 'check', side_effect=check), \
             patch.object(self.port, 'backtranslate', side_effect=lambda: stages.append('reverse') or dict(passed=True)), \
             patch.object(self.port, 'review', side_effect=lambda: stages.append('align')):
            target = run(self.base, self.target, self.port.settings, work=self.port.output)
        self.assertEqual(target, self.target)
        self.assertEqual(stages, ['translate', 'check', 'reverse', 'align'])
        self.assertTrue((target / 'back-translation/manifest.json').exists())

    def test_failed_publication_check_never_publishes_a_successful_app(self):
        with patch('policy_evaluation.porting.student.CodexPort', return_value=self.port), \
             patch.object(self.port, 'prepare'), \
             patch.object(self.port, 'translate', return_value=dict(passed=True)), \
             patch.object(self.port, 'check', return_value=dict(passed=False)), \
             patch.object(self.port, 'backtranslate') as reverse:
            with self.assertRaises(ValueError):
                run(self.base, self.target, self.port.settings, work=self.port.output, repairs=0)
        self.assertFalse(self.target.exists())
        reverse.assert_not_called()


if __name__ == '__main__':
    unittest.main()
