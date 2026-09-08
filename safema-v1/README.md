# SafeMA shared runtime — v1

This directory is the application-independent SafeMA v1 runtime. It loads API
effect, trusted-origin, and policy models; intercepts modeled calls; resolves
trusted metadata; evaluates policy; and records decisions before raw effects.

Application-specific API targets, model YAML, policies, runners, mechanism
tests, and baseline/treatment evaluations do not live here. They belong under
the relevant application version, for example:

```text
apps/recommendation-submission/v1/safema-v1/
```

Install locally from the repository root:

```bash
python -m pip install -e ./safema-v1
```

The `safema-register-resource` command is a generic trusted control-plane
utility. Application-specific launch commands are documented with each app's
integration artifacts.
