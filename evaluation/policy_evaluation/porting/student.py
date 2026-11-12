"""Two-directory student workflow; Git branches remain entirely user-owned."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from policy_runtime.policy import fingerprint
from .codex import CodexPort, artifact_text, files, save

DEFAULTS = dict(baseUrl='https://api.openai.com/v1', modelId='gpt-6.1-sol', reasoningEffort='medium')
POLICY_NAMES = {'policy.md', 'policies.md'}


def student_text(value):
    """Use business-facing terminology without changing execution conditions."""
    return re.sub(r'\bdatalog\b', 'policy rules', value, flags=re.IGNORECASE)


def load_connection(path=None):
    if path is not None:
        # Explicit debugging connections take precedence over the environment.
        settings = dict(DEFAULTS, **json.loads(Path(path).read_text()))
    else:
        fields = dict(baseUrl='POLICY_BASE_URL', apiKey='POLICY_API_KEY',
                      modelId='POLICY_MODEL_ID', reasoningEffort='POLICY_REASONING_EFFORT')
        settings = dict(DEFAULTS, **{key: os.environ[name] for key, name in fields.items() if name in os.environ})
        if not settings.get('apiKey') and not os.environ.get('POLICY_BASE_URL'):
            raise ValueError('Set POLICY_API_KEY before translation. Model and reasoning effort can be set with POLICY_MODEL_ID and POLICY_REASONING_EFFORT.')
    if not all(isinstance(settings.get(k), str) and settings[k].strip() for k in ('baseUrl', 'modelId', 'reasoningEffort')):
        raise ValueError('Connection requires nonblank baseUrl, modelId and reasoningEffort.')
    if 'apiKey' in settings and not isinstance(settings['apiKey'], str):
        raise ValueError('API key must be a string.')
    if 'apiKey' in settings:
        settings['apiKey'] = settings['apiKey'].strip()
        if '\n' in settings['apiKey'] or '\r' in settings['apiKey']:
            raise ValueError('API key must not contain line breaks.')
    return settings


def check_base(base, target, policy='policy.md', *, strict=True, app_doc='app.md'):
    base, target = Path(base).resolve(), Path(target).absolute()
    if base == target.resolve() or base.is_relative_to(target.resolve()) or target.resolve().is_relative_to(base):
        raise ValueError('Use separate base and enforced application directories.')
    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir()))):
        raise ValueError('Enforced application directory must be absent or empty.')
    git_root = Path(subprocess.check_output(['git', '-C', str(base), 'rev-parse', '--show-toplevel'], text=True).strip()).resolve()
    if git_root != base:
        raise ValueError('Base application must be the root of its own Git checkout.')
    if subprocess.check_output(['git', '-C', str(base), 'status', '--porcelain', '--untracked-files=normal'], text=True).strip():
        raise ValueError('Commit or remove local changes before translating the base application.')
    required = (app_doc, policy) if strict else (policy,)
    for name in required:
        path = base / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(base):
            raise ValueError('Base application requires ' + name + '.')
        subprocess.run(['git', '-C', str(base), 'ls-files', '--error-unmatch', name], check=True, capture_output=True)
    return base, target


def clean_candidate(candidate, destination, policy=None):
    if candidate.is_symlink() or any(p.is_symlink() for p in candidate.rglob('*')):
        raise ValueError('Generated application must not contain symbolic links.')
    shutil.copytree(candidate, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))
    for path in destination.rglob('*'):
        if path.is_file() and path.name.lower() in POLICY_NAMES:
            path.unlink()
    if policy:
        path = destination / policy
        if path.is_file():
            path.unlink()
    if (destination / 'back-translation').exists():
        raise ValueError('Application already uses the reserved back-translation directory.')


def publish(port, target, clean, policy_text):
    """Export implementation and independently generated readings, no source policy."""
    reference = json.loads(artifact_text(port.output, 'review.json'))
    if reference['source']['text'] != policy_text:
        raise ValueError('Source policy differs from the one used for translation.')
    pointer = json.loads(artifact_text(port.output, 'backtranslation.json'))
    if files(port.output / 'candidate') != pointer['candidateFiles']:
        raise ValueError('Candidate changed after back-translation.')
    reverse = port.output / pointer['directory']
    source_files = json.loads(artifact_text(reverse, 'source-manifest.json'))
    published_files = files(clean)
    if any(published_files.get(name) != digest for name, digest in source_files.items()):
        raise ValueError('Published implementation differs from the independently read implementation.')
    back = clean / 'back-translation'
    back.mkdir()
    execution = deepcopy(reference['execution'])
    links = execution.pop('links')
    for procedure in execution['procedures']:
        procedure['title'] = student_text(procedure['title'])
        for field in ('reads', 'steps'):
            for row in procedure[field]:
                row['text'] = student_text(row['text'])
    limits = []
    for item in execution.get('limitations', []):
        if isinstance(item, str):
            limits.append(student_text(item))
        elif isinstance(item, dict) and isinstance(item.get('text'), str):
            limits.append(dict(item, text=student_text(item['text'])))
        else:
            raise ValueError('Execution limitations need text descriptions.')
    execution['limitations'] = limits
    # The UI reads source text separately. It does not need executable internals.
    save(back / 'execution.json', execution)
    save(back / 'alignment.json', dict(links=links))
    description = reverse / 'backtranslation.md'
    if description.is_file():
        (back / 'description.md').write_text(student_text(artifact_text(reverse, 'backtranslation.md')))
    source = json.loads(artifact_text(port.output, 'source.json'))
    assets = files(back)
    metadata = dict(version=1, sourceCommit=source['revision'], policyHash=fingerprint(policy_text),
                    applicationFiles=source_files, assets=assets,
                    validation='Source correspondence and development checks; not a semantic proof.',
                    presentation='Business descriptions; implementation-language naming omitted. Original model output retained privately.',
                    model=getattr(port, 'settings', {}).get('modelId', DEFAULTS['modelId']))
    metadata['id'] = fingerprint(metadata)
    save(back / 'manifest.json', metadata)
    # Create the same blank submission file the review UI can later resume.
    from ..student_review import BundleApplication, blank_review
    application = BundleApplication(back, policy_text=policy_text)
    save(clean / 'review.json', blank_review(application.reference()))
    if target.exists() and any(target.iterdir()):
        raise ValueError('Output directory became nonempty; results remain in the private work directory.')
    os.rename(clean, target)


def run(base, target, settings, *, work=None, reuse=None, policy='policy.md', app_doc='app.md', image='policy-portin:batch-v1', codex='codex', repairs=2):
    base, target = check_base(base, target, policy, strict=reuse is None, app_doc=app_doc)
    if reuse:
        work = Path(reuse).resolve()
    else:
        work = Path(work).resolve() if work else target.parent / ('.' + target.name + '.translation')
    if work == target.resolve() or work.is_relative_to(target.resolve()) or target.resolve().is_relative_to(work):
        raise ValueError('Keep private work outside the published application.')
    port = CodexPort(work, settings, image=image, codex=codex)
    if reuse:
        source = json.loads(artifact_text(work, 'source.json'))
        revision = subprocess.check_output(['git', '-C', str(base), 'rev-parse', 'HEAD'], text=True).strip()
        if source['revision'] != revision or source['policy'] != policy:
            raise ValueError('Reused port does not match the selected original commit/policy.')
    else:
        port.prepare(base, policy)
        with (work / 'prompt.txt').open('a') as prompt:
            prompt.write('\nThe published application omits policy.md/policies.md. Preserve actual runtime behavior without depending on these authoring documents. Existing operational prompts may be retained separately. Do not name the underlying enforcement language in student-facing execution descriptions.\n')
        result = port.translate(repairs)
        if not result.get('passed'):
            raise ValueError('Translation failed development checks. Private attempts were retained.')
    clean = work / ('publish-' + uuid.uuid4().hex[:12])
    policy_relative = json.loads(artifact_text(work, 'source.json'))['policy']
    for attempt in range(repairs + 1):
        clean_candidate(work / 'candidate', clean, policy_relative)
        validation = port.check('publication-check-' + str(attempt) + '.json', source=clean)
        if validation.get('passed'):
            break
        if reuse or attempt == repairs:
            raise ValueError('Application failed checks without its source policy document; private results retained.')
        result = port.translate(repairs, feedback=dict(publicationCheck=validation,
            requirement='The published app omits policy.md/policies.md. Preserve existing behavior without those authoring files. Repair actual dependencies; never replace the native engine.'))
        if not result.get('passed'):
            raise ValueError('Publication repair failed; private results retained.')
        clean = work / ('publish-' + uuid.uuid4().hex[:12])
    if not reuse:
        result = port.backtranslate()
        if not result.get('passed'):
            raise ValueError('Independent execution reading failed checks; private attempts retained.')
        port.review()
    publish(port, target, clean, (base / policy).read_text())
    return target


def main():
    parser = argparse.ArgumentParser(description='Translate a clean original app into a separate enforced app.')
    parser.add_argument('base_app_dir', type=Path)
    parser.add_argument('enforced_app_dir', type=Path)
    parser.add_argument('--connection', type=Path)
    parser.add_argument('--work-dir', type=Path, help='Private debugging output; outside both application directories')
    parser.add_argument('--reuse-port', type=Path, help='Debug: publish an already completed, matching port without model calls')
    parser.add_argument('--policy', default='policy.md', help='Debug: original policy path relative to base')
    parser.add_argument('--app-doc', default='app.md', help='Debug: original application description path relative to base')
    parser.add_argument('--image', default='policy-portin:batch-v1')
    parser.add_argument('--codex', default='codex')
    parser.add_argument('--repairs', type=int, default=2)
    args = parser.parse_args()
    try:
        settings = dict(DEFAULTS) if args.reuse_port and not args.connection else load_connection(args.connection)
        target = run(args.base_app_dir, args.enforced_app_dir, settings, work=args.work_dir,
                     reuse=args.reuse_port, policy=args.policy, app_doc=args.app_doc, image=args.image, codex=args.codex, repairs=args.repairs)
        print('Enforced application: ' + str(target))
        print('Execution reading: ' + str(target / 'back-translation'))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
