"""Read declarations next to rules; native directives never pass through to Souffle."""

import re
import json


QUOTED = re.compile(r'"(?:\\.|[^"\\])*"')


def policy_line(line):
    masked = QUOTED.sub(lambda m: ' ' * len(m[0]), line)
    positions = [i for i in (masked.find('//'), masked.find('%')) if i >= 0]
    end = min(positions) if positions else len(line)
    return line[:end], line[end + (2 if line[end:end+2] == '//' else 1):] if positions else '', QUOTED.sub('""', line[:end])


def read_policy_source(source):
    if not isinstance(source, str) or len(source.encode("utf-16-le")) // 2 > 64_000:
        raise ValueError("Policy document exceeds 64,000 characters.")
    predicates, inputs, keys, lines = {}, set(), {}, []
    for line in source.split("\n"):
        code, comment, _ = policy_line(line)
        if not code.lstrip().startswith("."):
            lines.append("" if line.lstrip().startswith(("//", "%")) else line)
            continue
        declaration = re.fullmatch(r"\s*\.decl\s+([A-Za-z][A-Za-z_0-9]*)\s*\(([^()]*)\)\s*", code)
        input_ = re.fullmatch(r"\s*\.input\s+([A-Za-z][A-Za-z_0-9]*)\s*", code)
        key_ = re.fullmatch(r"\s*\.key\s+([A-Za-z][A-Za-z_0-9]*)\s*\(([^()]*)\)\s*", code)
        if key_:
            name, fields = key_.groups()
            if name in keys: raise ValueError('Duplicate key declaration.')
            keys[name] = [field.strip() for field in fields.split(',')] if fields.strip() else []
        elif declaration:
            name, fields = declaration.groups()
            if name in predicates or len(predicates) >= 64:
                raise ValueError("Duplicate or excessive predicate declarations.")
            args, types = [], []
            for field in fields.split(",") if fields.strip() else []:
                match = re.fullmatch(r"\s*([A-Za-z][A-Za-z_0-9]*)\s*:\s*(symbol|number)\s*", field)
                if not match or match[1] in args or len(args) >= 8:
                    raise ValueError("Declare distinct symbol/number arguments (at most eight).")
                args.append(match[1])
                types.append(match[2])
            predicates[name] = {"kind": "derived", "args": args, "meaning": comment.strip() or name}
            if "number" in types:
                predicates[name]["types"] = types
        elif input_:
            name = input_[1]
            if name in inputs:
                raise ValueError("Duplicate input declaration.")
            inputs.add(name)
        else:
            raise ValueError("Only .decl, .input and .key declarations are admitted.")
        lines.append("")
    if inputs - predicates.keys():
        raise ValueError("Every .input needs a .decl in the same policy file.")
    for name in inputs:
        predicates[name]["kind"] = "input"
    for name, key in keys.items():
        schema = predicates.get(name)
        if not schema or schema['kind'] != 'input' or len(set(key)) != len(key) or any(field not in schema['args'] for field in key):
            raise ValueError('Keys must name distinct fields of a declared input relation.')
        schema['key'] = key
    return predicates, "\n".join(lines)


def read_policy_document(source):
    """Separate reviewed static input facts from clauses; no native I/O directives."""
    predicates, rules = read_policy_source(source)
    configuration, lines, in_rule = [], [], False
    for line in rules.split("\n"):
        # A final body atom on its own line still belongs to the preceding rule.
        code, _, syntax = policy_line(line)
        code, syntax = code.strip(), syntax.strip()
        if in_rule or ':-' in syntax:
            lines.append(line)
            in_rule = not code.endswith('.')
            continue
        match = re.fullmatch(r'\s*([A-Za-z][A-Za-z_0-9]*)\s*\((.*)\)\s*\.\s*', code)
        if match:
            try:
                values = json.loads('[' + match[2] + ']')
            except (ValueError, TypeError):
                raise ValueError("Static facts need quoted strings or integer constants.") from None
            if any(not isinstance(v, str) and type(v) is not int for v in values):
                raise ValueError("Static facts need strings or integer constants.")
            configuration.append({"predicate": match[1], "args": [str(v) for v in values]})
            lines.append("")
        else:
            lines.append(line)
    return predicates, "\n".join(lines), configuration
