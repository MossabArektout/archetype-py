"""Example of an installable, shared Archetype rule package.

A real org would publish a package like this one to a private index (or a
public one) so every repository can depend on the same architecture rules
instead of re-writing them in each project's `architecture.py`. See
`../README.md` for how a consuming project uses it.
"""

from archetype import group, imports, rule

with group("Org baseline"):

    @rule("no-direct-db-access-from-api")
    def no_direct_db_access_from_api() -> None:
        imports("api").must_not_import("db")

    @rule("no-services-in-tests")
    def no_services_in_tests() -> None:
        imports("tests").must_not_import("services")
