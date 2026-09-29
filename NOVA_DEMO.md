# Executable Nova demo

The existing Rakazo facts inspector and Datalog terminal are in the adjacent
`../rakazo-policy-clean` checkout. The executable demo based on this workspace's
`main.tex` is implemented there using the existing UI and Datalog evaluator.

```bash
cd ../rakazo-policy-clean
./scripts/nova-demo.sh
```

Open http://127.0.0.1:5180/nova.html.

See [architecture, semantics, tests, and commands](../rakazo-policy-clean/docs/nova-reasoning-demo.md).

Git backup: [nova-reasoning-demo branch](https://github.com/thaddywu/AgentProperties/tree/nova-reasoning-demo).
