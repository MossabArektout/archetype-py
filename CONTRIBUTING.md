# Contributing

## Welcome
Contributions are welcome.
Bug reports, feature requests, documentation improvements, and code contributions of all sizes are appreciated.

## Before you start
For anything beyond a small typo fix, please open an issue before writing code.
This keeps work aligned with the project direction and helps us agree on scope early.
It also avoids wasted effort if a proposal is out of scope or already planned differently.

## Development setup
```bash
# 1) Fork the repo on GitHub (requires GitHub CLI)
gh repo fork MossabArektout/archetype-py --clone=true

# 2) Enter the project directory
cd archetype-py

# 3) Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 4) Install in development mode with dev dependencies
python -m pip install --upgrade pip
pip install -e ".[dev]"

# 5) Run tests to verify setup
pytest
```

## Project structure
- `archetype/` contains the main package code, including analysis, DSL, built-in rules, CLI, reporter, and pytest plugin.
- `tests/` contains the full automated test suite and test fixtures.
- `architecture.py` defines Archetype’s own architecture rules and is used for self-enforcement.
- `pyproject.toml` contains package metadata, dependencies, entry points, and build configuration.
- `.github/workflows/` contains CI and release automation workflows.
- `README.md` is the user-facing documentation and quickstart.
- `CHANGELOG.md` tracks release history and major changes.

## Making changes
```bash
# 1) Create a branch with a descriptive name
git checkout -b fix/import-graph-relative-resolution

# 2) Make your changes and update/add tests
# (edit files)

# 3) Run the full test suite
pytest

# 4) Run Archetype checks against this codebase
archetype check .

# 5) Commit and push your branch
git add -A
git commit -m "Fix relative import resolution in graph builder"
git push -u origin fix/import-graph-relative-resolution
```
Open a pull request from your branch to `main`.

## Pull request guidelines
- The PR description explains what changed and why.
- All tests pass.
- `archetype check .` passes.
- New features include tests.
- Commit messages are clear and descriptive.

<details>
<summary>Pull request template preview</summary>

```md
## Summary
- What changed?
- Why was this change needed?

## Changes
- 
- 

## How to test
- [ ] Ran full test suite: `pytest`
- [ ] Ran architecture checks: `archetype check .`

## Related issue
Closes #

## Checklist
- [ ] PR description explains what changed and why
- [ ] All tests pass
- [ ] `archetype check .` passes
- [ ] New features include tests
- [ ] Commit messages are clear and descriptive
```

</details>

## Reporting bugs
Open a GitHub issue with a minimal reproducible example.
Include your Python version and operating system.

## Suggesting features
Open a GitHub issue that explains the use case and the problem it solves.
Describe the problem first, not only the proposed solution, so we can discuss the best approach.
