"""Example architecture.py for a project that adopts a shared rule pack.

This is what an individual repository's own `architecture.py` looks like
once `acme-archetype-rules` (the package defined next to this file, under
`acme_archetype_rules/`) has been published and installed with
`pip install acme-archetype-rules`. Copy this pattern into your own
project's `architecture.py`; you do not need anything else from this
`examples/shared-rules/` directory.
"""

import acme_archetype_rules
from archetype import group, imports, rule
from archetype.rule import use

# Register every org-wide baseline rule exported by the shared package.
# Passing the module itself registers every @rule-decorated function found
# in it. Use this form (rather than a bare `import acme_archetype_rules`
# relying on its side effects) so the rules are registered correctly even
# if Python has already cached the module from an earlier import elsewhere
# in the same process — see the docstring on `archetype.rule.use` for why
# that matters.
use(acme_archetype_rules)

# Add repository-specific rules alongside the shared baseline.
with group("Repo-specific"):

    @rule("no-legacy-imports")
    def no_legacy_imports() -> None:
        imports("myapp").must_not_import("myapp.legacy")


# A shared rule's severity can still be relaxed or disabled for this one
# repository without touching the shared package, via archetype.toml:
#
#   [rules."no-services-in-tests"]
#   policy = "warning"
