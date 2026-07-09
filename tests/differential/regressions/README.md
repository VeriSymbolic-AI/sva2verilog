# Differential Regression Fixtures

This directory is for minimized source-level differential failures promoted
from Hypothesis runs.

Only add fixtures after reviewing that the case is:

- small enough to inspect;
- generated from the supported finite-state subset;
- free of absolute local paths, usernames, tokens, private environment values,
  and company information;
- reproducible without rerunning Hypothesis.

Each JSON fixture should use the schema produced by
`tests.differential_cases.write_failure_artifact()`: case metadata, source text
inside the mismatch payload, full stimulus, oracle trace, backend trace, and the
first mismatch reason.

Do not commit every random example. Commit minimized failures and curated smoke
fixtures only.
