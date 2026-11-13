# Policy viewer

`review_units(review)` creates stable literal sentence spans and connects existing requirements/behaviors to source text. `alignment.py` links frozen independent descriptions to original sentences in a separate model pass. A link means relevance, not full coverage or correctness.

```python
from policyscope.policy_viewer import review_units
from policyscope.policy_viewer.alignment import align_execution
```

Open the shared UI with `policyscope review`. It displays original policy, corresponding checks, categories and human judgments. Review records and local HTTP composition live in `workbench`. Ratings never approve or install a policy.

Portable execution readings can be opened with `--back-translation` and an explicit `--policy`; see [the student workflow](../../../docs/student-workflow.md).
