"""Read human-oriented rule annotations for documentation and reference artifacts."""

import re


def entries(source):
    result = []
    pattern = r'^// (Rule|Fact): ([A-Za-z0-9_-]+) \| (P[1-9][0-9]*\.[1-9][0-9]*)\s*$'
    matches = list(re.finditer(pattern, source, re.M))
    for index, match in enumerate(matches):
        block = source[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(source)]
        code = '\n'.join(line for line in block.splitlines() if line.strip() and not line.lstrip().startswith('//'))
        # Policy headings and comments may follow the terminating period.
        if not code.endswith('.'):
            raise ValueError('Every annotated entry must end in a period.')
        comments = [line[3:].strip() for line in block.splitlines() if line.startswith('// ')]
        result.append({'kind': match[1].lower(), 'id': match[2], 'policy': match[3],
                       'explanation': comments[0] if comments else '', 'datalog': code})
    if len({entry['id'] for entry in result}) != len(result):
        raise ValueError('Rule and fact annotation IDs must be unique.')
    return result
