"""Build the single English PolicyScope guide from reviewed policy and code sources."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'translation/tools'), str(ROOT / 'runtime/python')]
from annotated_policy import entries
from policy_runtime import Policy
from policy_runtime.policy import CORE, CATALOG
from policy_runtime.datalog import parse, decode, variable
from policy_runtime.source import read_policy_document


def tex(value):
    escapes = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
               '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(escapes.get(c, c) for c in str(value))


def mono(value):
    text = tex(value).replace('(', r'(\allowbreak{}').replace(',', r',\allowbreak{}')
    return r'\texttt{' + text + '}'


def styled(name):
    if name in CORE:
        return r'\textbf{' + mono(name) + '}'
    if any(name in module['predicates'] for module in CATALOG.values()):
        return r'\textit{' + mono(name) + '}'
    return mono(name)


def code(source, *, background='gray!5', tight=False):
    # Compact clause whitespace, preserving each executable clause and its comment.
    if ':-' in source and not source.lstrip().startswith('#'):
        lines, pending = [], ''
        for line in source.strip().splitlines():
            if not line.strip() or line.startswith('//') or not line.startswith(' '):
                if pending:
                    lines.append(pending); pending = ''
                if line.startswith('//') or not line.strip():
                    lines.append(line)
                else:
                    pending = line
            elif len(pending + ' ' + line.strip()) <= 96:
                pending += ' ' + line.strip()
            else:
                lines.append(pending); pending = '    ' + line.strip()
        if pending: lines.append(pending)
        source = '\n'.join(lines)
    options = 'backgroundcolor=\\color{' + background + '}'
    if tight: options += ',aboveskip=0pt,belowskip=0pt'
    return '\n\\begin{lstlisting}[' + options + ']\n' + source.strip('\n') + '\n\\end{lstlisting}\n'


def quote_box(identity, original, url):
    needed = 4 + (len(original) // 105)
    return (r'\needspace{' + str(needed) + r'\baselineskip}' + '\n'
            + r'\noindent\colorbox{gray!11}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{\small '
            + r'\textbf{Original policy ' + tex(identity) + r'.} ' + tex(original.replace('**', ''))
            + r' \href{' + url + r'}{[source]}}}\par')


def preamble():
    return r'''\documentclass[a4paper,10pt]{article}
\usepackage[margin=19mm]{geometry}
\usepackage{fontspec,xcolor,listings,hyperref,fancyhdr,needspace,longtable,array,titlesec}
\setmainfont{DejaVu Serif}[AutoFakeSlant=0.18]
\setmonofont{DejaVu Sans Mono}[Scale=0.90]
\hypersetup{colorlinks=true,urlcolor=blue,linkcolor=blue,pdfauthor={PolicyScope project},pdftitle={PolicyScope: policies, adapters and system boundaries}}
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{PolicyScope}\fancyhead[R]{Policies and adapters}
\fancyfoot[C]{\thepage}\setlength{\headheight}{14pt}
\setlength{\parindent}{0pt}\setlength{\parskip}{4pt}\raggedright
\titleformat{\section}{\large\bfseries}{\thesection}{0.6em}{}
\titleformat{\subsection}{\normalsize\bfseries}{\thesubsection}{0.6em}{}
\titleformat{\subsubsection}{\normalsize\bfseries}{}{0pt}{}
\titlespacing*{\section}{0pt}{1.5ex}{0.8ex}
\titlespacing*{\subsection}{0pt}{1.4ex}{0.6ex}
\titlespacing*{\subsubsection}{0pt}{1.3ex}{0.5ex}
\lstset{basicstyle=\ttfamily\footnotesize,breaklines=true,columns=fullflexible,
keepspaces=true,showstringspaces=false,sensitive=true,
morecomment=[l]{//},morecomment=[l]{\#},commentstyle=\color{black!65},
morekeywords=[1]{Request,Parameter,Allow,Deny},keywordstyle=[1]\bfseries,
morekeywords=[2]{Capability,PrincipalGroup,ResourceGroup,Can,Source,DependsOn,Provenance,ResourceType,ResourceState,InitialState,AllowedTransition,ReachableState,CanTransition},keywordstyle=[2]\itshape,
aboveskip=4pt,belowskip=5pt}
\begin{document}
\begin{center}{\Large\bfseries PolicyScope}\\[3pt]
Policies, adapters, enforcement and analysis\end{center}
'''


def load_app(name, prefix):
    path = ROOT / 'apps' / name
    manifest = json.loads((path / 'walkthrough.json').read_text())
    source = (path / 'rules.dl').read_text()
    annotated = entries(source)
    rules = {r['id']: r for r in annotated if r['kind'] == 'rule'}
    _, actual, configuration = read_policy_document(source)
    assert parse(actual)[0] == parse('\n'.join(r['datalog'] for r in rules.values()))[0]
    policies = {}
    for paragraph in (path / 'policy.md').read_text().strip().split('\n\n'):
        identity, text = paragraph.split('. ', 1)
        policies[identity] = text.strip()
    for row in manifest['requirements']:
        original = policies[row['policyId']]
        start = row.get('start', original.index(row['source']))
        end = row.get('end', start + len(row['source']))
        assert original[start:end] == row['source'], row['id']
    policy = Policy(path / 'rules.dl', target=manifest.get('target', 'resource'),
                    invariants=tuple(manifest.get('invariants', [])))
    binding = policy.runtime.binding
    policy.runtime.close()
    return dict(path=path, manifest=manifest, source=source, annotated=annotated,
                rules=rules, policies=policies, configuration=configuration,
                binding=binding, prefix=prefix)


def rule_listing(entry):
    return code('// ' + entry['explanation'] + '\n' + entry['datalog'])


def atom_text(atom):
    return atom['predicate'] + '(' + ', '.join(atom['args']) + ')'


def builtins():
    lines = [r'\subsection{Builtins and their semantics}\label{sec:builtins}',
             r'\textbf{Runtime predicates are bold}; \textit{shared predicates are italic}; '
             'app predicates use plain monospace. SDK signatures below are not fact assertions.',
             r'\textbf{Runtime gate.}']
    meanings = {
        'Request': 'Runtime input: call ID, application-supplied caller name and event kind.',
        'Parameter': 'Runtime input: actual call arguments bound to Q.',
        'Allow': 'Derived permission; requires no Deny and valid runtime checks.',
        'Deny': 'Derived refusal; overrides Allow for the same Q.',
    }
    lines.append(code('\n\n'.join('// ' + meanings[n] + '\n' + n + '(' + ', '.join(s['args']) + ')' for n, s in CORE.items())))
    lines += [r'\begin{center}\small\begin{tabular}{lll}\hline '
              + styled('Allow') + '(Q) & Any ' + styled('Deny') + r'(Q, Reason) & Business callback\\\hline '
              r'Absent & Absent & Refused\\Present & Absent & May execute after runtime checks\\'
              r'Absent & Present & Refused\\Present & Present & Refused\\\hline\end{tabular}\end{center}',
              'Each call derives fresh answers from current facts. Evaluation failure, an invalid transition or a violated invariant refuses execution.']
    titles = {'capability': 'Optional capability and membership', 'provenance': 'Optional provenance', 'fsm': 'Optional resource lifecycle'}
    for name, module in CATALOG.items():
        lines += [r'\needspace{7\baselineskip}', r'\textbf{' + titles[name] + '.}']
        signatures = []
        for predicate, schema in module['predicates'].items():
            kind = 'Input' if schema['kind'] == 'input' else 'Derived'
            signatures += ['// ' + kind + ': ' + schema['meaning'], predicate + '(' + ', '.join(schema['args']) + ')', '']
        lines.append(code('\n'.join(signatures)))
        for rule in module['rules']:
            text = '// ' + rule['explanation'] + '\n' + atom_text(rule['head']) + ' :-\n    ' + ',\n    '.join(atom_text(a) for a in rule['body']) + '.'
            lines.append(code(text))
        if name == 'capability':
            lines.append('Can constrains execution only when used by an Allow/Deny rule.')
        elif name == 'provenance':
            lines.append('Provenance alone does not authorize disclosure.')
        else:
            lines.append('Configured lifecycle calls must match CanTransition. On confirmed success, the SDK replaces ResourceState. ReachableState ignores permissions and execution history.')
    return lines


def adapter_table():
    rows = [
        ('Policy(path, **options)', 'Load .dl schemas, initial EDB facts and rules once at startup.'),
        ('@policy', 'Create Request/Parameter, check Allow/Deny and skip denied tool bodies.'),
        ('policy.put / policy.delete', 'Manual adapters update EDB. Keyed put replaces the old tuple; delete removes a fact.'),
    ]
    lines = [r'\small\begin{longtable}{@{}>{\raggedright\arraybackslash}p{0.43\linewidth}>{\raggedright\arraybackslash}p{0.53\linewidth}@{}}',
             r'\textbf{Schema / call form} & \textbf{Semantics}\\\hline\endfirsthead',
             r'\textbf{Schema / call form} & \textbf{Semantics (continued)}\\\hline\endhead']
    for signature, meaning in rows:
        lines.append(mono(signature) + ' & ' + tex(meaning) + r'\\[4pt]')
    lines += [r'\hline\end{longtable}\normalsize']
    return lines


def adapters(app):
    lines = [r'\subsection{Loading rules and adding a tool adapter}\label{sec:adapter}',
             'The .dl file describes schemas, initial facts and rules. @policy adds enforcement to a tool call. '
             'Developers must add the adapter statements that update EDB from actual business results.']
    lines += adapter_table()
    lines += [r'\textbf{Import and load once at startup.} Selected settings from adapter.py and run.py:',
              code('''# SDK import and initial policy loading; no business operation runs here.
from policy_runtime import Policy

policy = Policy(
    "rules.dl",
    target="job_id",  # Tool argument identifying the FSM resource.
    # Map the existing approve=False argument to a job-rejection event.
    event=lambda name, args: "reject_job"
        if name == "approve_job" and args.get("approve") is False else name,
    completed=lambda result: result.get("ok") is not False,
)
store.policy = policy  # Reuse the same instance across tool calls.'''),
              r'\textbf{Existing application logic.} '
              'In the tool below, s is the original Store instance. s.submit calls this unchanged Store.submit method:',
              code(app['manifest']['originalSubmit']['code'], background='white'),
              'The existing method validates the specification, creates the job and commits it through the application\'s own transaction.',
              r'\needspace{25\baselineskip}', r'\textbf{Manual adapter after the original operation.} '
              'Grey blocks are added code; white blocks retain the business call.',
              r'\begin{minipage}{\linewidth}']
    lines.append(code("policy = s.policy  # Reuse the policy loaded at startup.", background='gray!18', tight=True))
    lines.append(code("elif name=='submit_job':", background='white', tight=True))
    annotation = '    @policy(name=name, arguments=a)  # Adaptation code: read caller at invocation.'
    lines.append(code(annotation, background='gray!18', tight=True))
    lines.append(code("""    def fn(e):
        result=s.submit(r,a['spec'],e)""", background='white', tight=True))
    submit = """        # Adaptation code: stage only the confirmed job fields.
        if result.get('ok') is not False:
            job=result['job']
            policy.put('ResourceType', job['id'], 'job')
            policy.put('ResourceState', job['id'], job['state'])
            # Current job metadata: ID, owner, version, task hash and run ID.
            # Job is keyed by ID; put replaces that job's old tuple.
            policy.put('Job', job['id'], job['owner'], job['version'],
                       job['task_hash'], job['run_id'])
            spec=job['spec']
            policy.put('JobSpec', job['id'], spec['node_type'], spec['cpu_cores'],
                       spec['memory_gb'], spec['runtime_minutes'])
            policy.put('CurrentApproval', job['id'], job['approval_id'])
            policy.put('Waiting', job['id'], job['waiting_dispatches'], job['submission_seq'])
            policy.put('JobOutcome', job['id'], job['outcome'])
            # Adaptation code: identify this task version and record its owner as origin.
            job_data = policy.data.reference('job', job['id'], job['task_hash'])
            policy.put('RecordData', 'job', job['id'], job_data)
            policy.put('Source', job['owner'], job_data)"""
    patch = (app['path'] / 'upstream.patch').read_text()
    assert '+' + '        ' + annotation in patch
    assert all('+' + '        ' + line in patch for line in submit.splitlines())
    lines.append(code(submit, background='gray!18', tight=True))
    lines.append(code('        return result', background='white', tight=True))
    lines += [r'\end{minipage}',
              'The local callback receives only a trace event ID, so name and a supply the actual tool name and parameters. Ordinary named functions use @policy directly. '
              'The original call path is retained. Caller-name adaptation reads Tools.role here, or MCP request metadata in the second app.',
              tex('Nested dictionaries such as spec are flattened into Parameter names. Lists, floats and custom objects require an explicit adapter mapping.'),
              tex('New resource type/state facts are checked against InitialState("job", "QUEUED") before policy commit. ')
              + styled('RecordData') + ' maps a business record to its data ID; ' + styled('Source') + ' records its origin.',
              'The annotation supplies the request and gate; it does not infer these business facts. A refusal skips the body. An explicit ok=False publishes no EDB edits. '
              'A synchronization failure after a business commit stops the scope without undoing the business effect.',
              r'\textbf{Allowing Professor to reject a queued job.} This is a permitted business operation, not a policy refusal:']
    lines.append(code('''// Reviewed membership and the job-rejection state edge.
PrincipalGroup("Professor", "Professor").
AllowedTransition("job", "reject_job", "QUEUED", "TERMINATED").'''))
    lines.append(rule_listing(app['rules']['r9']))
    lines += [code('''# Assume JOB-001 is currently QUEUED at version 1.
prof_tools = Tools("Professor", store, trace)
prof_tools.call("approve_job", {
    "job_id": "JOB-001", "expected_version": 1, "approve": False})
# Policy allows the mapped reject_job event.
# The original application rejects the job; policy state becomes TERMINATED.''')]
    return lines

def literal_fact(row, schema):
    types = schema.get('types', ['symbol'] * len(schema['args']))
    values = [value if kind == 'number' else json.dumps(value) for value, kind in zip(row['args'], types)]
    return row['predicate'] + '(' + ', '.join(values) + ').'


def app_walkthrough(app):
    manifest, rules, binding = app['manifest'], app['rules'], app['binding']
    prefix = app['prefix']
    lines = [r'\section{' + tex(manifest['application']) + '}',
             r'\subsection{Policy walkthrough}\label{' + prefix + '-walkthrough}',
             'Grey boxes quote original P1--P6. Pn.m are our decomposition; rules follow in source order.']
    seen, shown, operations, configured = set(CORE), set(), set(), set()
    for module in CATALOG.values(): seen.update(module['predicates'])
    upstream = manifest['upstream']
    url = upstream['url'] + '/blob/' + upstream['revision'] + '/' + upstream['policyFile']
    for policy_id, original in app['policies'].items():
        lines += [r'\subsubsection*{' + policy_id + r'}\phantomsection\label{' + prefix + '-' + policy_id + '}',
                  r'\addcontentsline{toc}{subsubsection}{' + policy_id + '}',
                  quote_box(policy_id, original, url)]
        for row in (r for r in manifest['requirements'] if r['policyId'] == policy_id):
            identity = row['id']
            lines += [r'\needspace{5\baselineskip}\phantomsection\label{' + prefix + '-' + identity + '}',
                      r'\textbf{' + tex(identity + '  ' + row['title']) + '}']
            selected = row['ruleIds']
            names = list(dict.fromkeys(re.findall(r'\b([A-Z][A-Za-z0-9_]*)\(', '\n'.join(rules[r]['datalog'] for r in selected))))
            heads = {parse(rules[r]['datalog'])[0][0]['head']['predicate'] for r in selected}
            for name in names:
                schema = binding['predicates'].get(name)
                if not schema: continue
                if name not in seen:
                    seen.add(name)
                    if name not in heads:
                        description = manifest.get('vocabulary', {}).get(name, {})
                        meaning = description.get('brief', description.get('text', schema['meaning']))
                        lines.append(mono(name + '(' + ', '.join(schema['args']) + ')') + ': ' + tex(meaning))
                        if 'key' in schema:
                            lines.append(mono('.key ' + name + '(' + ', '.join(schema['key']) + ')'))
                if schema['kind'] == 'input' and name not in configured and name not in ('AllowedTransition', 'InitialState'):
                    facts = [f for f in app['configuration'] if f['predicate'] == name]
                    if facts:
                        lines.append(code('// Reviewed configuration.\n' + '\n'.join(literal_fact(f, schema) for f in facts)))
                    configured.add(name)
            for rule_id in selected:
                assert rule_id not in shown, 'Reference an earlier rule instead of repeating it: ' + rule_id
                entry = rules[rule_id]
                for clause in parse(entry['datalog'])[0]:
                    for atom in clause['body']:
                        if atom['predicate'] != 'Request' or variable(atom['args'][2]): continue
                        event = decode(atom['args'][2])
                        if event in operations: continue
                        note = manifest['operations'][event]; operations.add(event)
                        lines.append(r'\textbf{' + tex(note['kind']) + '.} ' + mono(note['call']) + ': ' + tex(note['text']))
                lines.append(rule_listing(entry)); shown.add(rule_id)
            facts = [f for f in app['annotated'] if f['kind'] == 'fact' and f['policy'] == identity]
            if facts:
                lines.append(code('\n\n'.join('// ' + f['explanation'] + '\n' + f['datalog'] for f in facts)))
            related = row['relatedRuleIds']
            if related:
                refs = list(dict.fromkeys(rules[r]['policy'] for r in related))
                lines.append(r'\textbf{Reuses} ' + ', '.join(r'\hyperref[' + prefix + '-' + p + ']{' + p + '}' for p in refs) + '.')
            if row.get('guideNote'):
                lines.append(r'\textbf{Adapter.} ' + tex(row['guideNote']))
            if row['relation'] != 'equivalent':
                status = 'Partial' if row['relation'] == 'partial' else 'Context only'
                lines.append(r'\textbf{' + status + r';} see Section~\ref{' + prefix + '-scope}.')
            if identity == 'P1.3' and prefix == 'lab':
                lines.append(r'\textbf{Adapter.} Bus.send checks COMPLETION\_REPORT ownership before delivery; other message kinds are unchanged.')
            if identity == 'P2.4' and prefix == 'lab':
                lines.append(mono('refused("read_job")') + ' returns ' + mono('{"status": "UNAVAILABLE"}') + ' for both forbidden and missing jobs.')
    assert shown == set(rules), 'Show every executable application clause exactly once.'
    return lines


SCOPES = {
    'lab': [
        ('P2.1--P2.3', 'Output and IFC', 'Original view/read_private filter outputs; QueueViewer/PrivateReadable do not. General message/context IFC is missing: T2 UNSAFE_PEER_NOTE still leaks. Only structured completion reports are guarded.'),
        ('P2.6--P2.7', 'Trace and secrets', 'Evaluator-only trace access relies on deployment. Credential and secret-flow checks are not implemented.'),
        ('P3.4, P4.7', 'Observation and commits', 'Store and EDB commit separately; synchronization failures stop the scope. Restart reconciliation and external drift detection are not implemented.'),
        ('P5.1, P5.4', 'Scheduling scope', 'Aging constrains dispatch choices, not future progress. Waiting updates assume the pinned one-node-per-type backend; other schedulers need explicit change records.'),
        ('P6.2', 'Reason semantics', 'Reasons are checked for nonblank text and length, not justification.'),
        ('All', 'Trusted application boundary', 'Host role strings are not authentication. No real runner is integrated; the T4 direct Store bypass remains unguarded.'),
    ],
    'scam': [
        ('P1.2--P1.4, P2.2', 'Missing trusted producers', 'Authenticated confirmation, identity-review and cooling producers are absent. Tests ingest synthetic host facts.'),
        ('P4.2--P4.3', 'Missing lineage instrumentation', 'Tests supply Source/DependsOn; original message rewrites do not record data-version lineage.'),
        ('P1.3, P3.2', 'Bank state and day boundary', 'Bank JSON and EDB commit separately. No restart reconciliation, drift detection or daily rollover. Policy uses integer cents; original bank arithmetic remains floating point.'),
        ('P5.1--P5.4', 'Identity and separation', 'Principal checks require endpoint authentication. Free-text A2A verification is not bound to a transfer-safe scope. The original prompt rejects unregistered recipients outright.'),
        ('P6.2--P6.4', 'Output and A2A scope', 'list_payees masks accounts; other outputs and raw request_payment_verification text lack a scoped structured bridge.'),
        ('P1.1, P2.1, P3.1, P4.1, P6.1', 'Motivating statements', 'These sentences motivate policies; they do not define executable detectors.'),
    ],
}


def scope_section(app):
    prefix = app['prefix']
    lines = [r'\subsection{Unsupported and conditional scope}\label{' + prefix + '-scope}']
    for ids, title, detail in SCOPES[prefix]:
        lines.append(r'\textbf{' + tex(title) + '} (' + tex(ids) + '). ' + tex(detail))
    # Every declared gap must appear in this section's references (range-aware).
    covered = set()
    for refs, _, _ in SCOPES[prefix]:
        for token in refs.split(', '):
            match = re.fullmatch(r'(P\d+)\.(\d+)--(?:P\d+\.)?(\d+)', token)
            if match:
                covered.update(match[1] + '.' + str(i) for i in range(int(match[2]), int(match[3]) + 1))
            elif token != 'All': covered.add(token)
    gaps = {r['id'] for r in app['manifest']['requirements'] if r['relation'] != 'equivalent'}
    assert gaps <= covered, 'Keep every partial/unresolved requirement in scope: ' + str(gaps - covered)
    upstream = app['manifest']['upstream']
    lines.append(r'{\small Source: \href{' + upstream['url'] + '/tree/' + upstream['revision'] + r'}{pinned student repository}.}')
    return lines


def render():
    lab = load_app('labcluster-port', 'lab')
    scam = load_app('scam-port', 'scam')
    lines = [preamble(), r'\section{Builtins and a concrete adapter example}\label{sec:example}']
    lines += builtins()
    lines += adapters(lab)
    for app in (lab, scam):
        lines += [r'\clearpage'] + app_walkthrough(app) + scope_section(app)
    lines.append(r'\end{document}')
    return '\n\n'.join(lines)


def build(source, output):
    output = output.resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='policy-walkthrough-') as temporary:
        folder = Path(temporary); (folder / 'guide.tex').write_text(source)
        for _ in range(2):
            result = subprocess.run(['xelatex', '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode', 'guide.tex'], cwd=folder,
                                    env={**os.environ, 'SOURCE_DATE_EPOCH': '1794268800'}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
            if result.returncode: raise RuntimeError(result.stdout[-5000:])
        log = (folder / 'guide.log').read_text()
        if 'Missing character' in log or 'Overfull' in log:
            raise RuntimeError('\n'.join(line for line in log.splitlines() if 'Missing character' in line or 'Overfull' in line))
        shutil.copy(folder / 'guide.pdf', output)
    print('Built', output.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/policyscope-guide.pdf')
    args = parser.parse_args()
    build(render(), args.output)


if __name__ == '__main__': main()
