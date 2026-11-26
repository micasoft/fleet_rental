# Known bugs (pinned by failing tests)

No known bugs right now: `make test` passes and `make test-check` expects no
failure.

When you find a bug, write a test that asserts the **correct** behaviour,
start its docstring with `Bug:` and add a row below (test, bug, file and
line). `make test-check` then passes while exactly those tests fail. When the
bug is fixed, the test turns green: drop its `Bug:` prefix and its row in the
same commit.

| Test | Bug | Where |
|---|---|---|
