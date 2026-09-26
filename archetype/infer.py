"""Infer architecture rules from a project's current import graph.

`archetype init --infer` uses this module to turn the structure a codebase
already has into an ``architecture.py`` that passes today, so the first
`archetype check` is green and every later run guards against new drift.

Inference works on *components*: the direct children of the package that
holds the project's code (``myapp.api``, ``myapp.services``, ...). Module-level
imports are rolled up into component-level dependencies, and from those:

- the longest downward dependency chain becomes a ``layers()`` rule,
- consumer packages that never reach each other become an ``independent()`` rule,
- ``internal`` / ``_private`` packages imported only from their parent become
  ``module().only_imported_within()`` rules,
- a ``no_cycles()`` rule is added, as a warning when cycles already exist,
- when two components import each other but one direction is rare, the rare
  direction is flagged as a suspected leak (warning only).

Every generated file is executed through the real rule engine before it is
returned; any rule that would fail is downgraded to ``@warn``.
"""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import networkx as nx

import archetype.dsl.query as query_module
from archetype.analysis.imports import build_import_graph
from archetype.analysis.models import RuleResult, Violation
from archetype.analysis.path_filters import normalize_exclude_patterns
from archetype.config import load_check_config
from archetype.init import detect_project_structure
from archetype.rule import registry

# Module path segments that never describe production architecture. Any module
# with one of these segments is left out of inference.
_IGNORED_SEGMENTS = {
    "architecture",
    "benchmark",
    "benchmarks",
    "build",
    "conftest",
    "dist",
    "doc",
    "docs",
    "example",
    "examples",
    "noxfile",
    "scripts",
    "setup",
    "test",
    "testing",
    "tests",
}

# Directories whose code is left out of inference even when it sits inside a
# discovered package root (for example `examples/*/src`).
_IGNORED_DIRECTORIES = (
    "benchmark/",
    "benchmarks/",
    "build/",
    "dist/",
    "doc/",
    "docs/",
    "example/",
    "examples/",
    "scripts/",
    "test/",
    "testing/",
    "tests/",
)

_MAX_BOUNDARY_RULES = 10
_MAX_LEAK_RULES = 5
_MAX_EVIDENCE_LINES = 3
# Imports that tangle packages into a loop are flagged as leaks when cutting
# them removes at most a quarter of the imports inside that loop; otherwise the
# packages are genuinely intertwined and are reported as tangled instead.
_LEAK_RATIO = 3


@dataclass
class ComponentEdge:
    """Module-level imports rolled up between two components."""

    source: str
    target: str
    count: int
    locations: list[str]
    # For a suspected leak: the existing dependency path it turns into a loop.
    closes: list[str] = field(default_factory=list)


@dataclass
class InferredRule:
    """One rule to render into the generated architecture.py."""

    name: str
    group: str
    call: list[str]
    comment: list[str]
    warn: bool = False
    base_imports: tuple[str, ...] = ()
    rule_imports: tuple[str, ...] = ()
    # Set when verification found violations the inference did not expect
    # (for example tests importing an internal package): where it failed.
    downgraded_at: list[str] = field(default_factory=list)


@dataclass
class Inference:
    """Everything inferred from one project's import graph."""

    scope: str
    module_count: int
    import_count: int
    components: list[str]
    layers: list[str] = field(default_factory=list)
    layers_adjacent: bool = False
    layers_leaky: bool = False
    # Suspected leaks that point upward inside the layer chain.
    layer_leaks: list[ComponentEdge] = field(default_factory=list)
    # Modules that import the scope package itself (`import myapp`), which
    # hides the parts of it they actually use.
    facade_importers: list[str] = field(default_factory=list)
    independent: list[str] = field(default_factory=list)
    protected: list[tuple[str, str, bool]] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    tangled: list[list[str]] = field(default_factory=list)
    leaks: list[ComponentEdge] = field(default_factory=list)
    rules: list[InferredRule] = field(default_factory=list)

    @property
    def warning_rules(self) -> list[InferredRule]:
        return [inferred for inferred in self.rules if inferred.warn]


@dataclass
class InferredArchitecture:
    """The inference, the rendered file, and its verification results."""

    inference: Inference
    content: str
    results: list[RuleResult]


def _is_ignored_segment(segment: str) -> bool:
    if segment in _IGNORED_SEGMENTS:
        return True
    if segment.startswith("test_") or segment.endswith("_test"):
        return True
    return segment.startswith("__") and segment.endswith("__")


def _is_dunder_free_private(segment: str) -> bool:
    return segment.startswith("_") and not segment.startswith("__")


def _within(module_name: str, pattern: str) -> bool:
    if not pattern:
        return True
    return module_name == pattern or module_name.startswith(f"{pattern}.")


def _short(module_name: str, scope: str) -> str:
    if scope and module_name.startswith(f"{scope}."):
        return module_name[len(scope) + 1 :]
    return module_name


def _relative_location(edge_data: dict[str, object], project_root: Path) -> str:
    file_attr = edge_data.get("file")
    line = edge_data.get("line") or 0
    if not file_attr:
        return "<unknown>"
    file_path = Path(str(file_attr))
    try:
        display = file_path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        display = file_path.as_posix()
    return f"{display}:{line}" if line else display


def _choose_scope(modules: list[str]) -> str:
    """Pick the package whose direct children are the components.

    Descends from the top while there is exactly one package to descend into.
    At the very top, loose single-file modules (``manage.py``, ``app.py``) do
    not stop the descent into a lone package.
    """
    split = [module_name.split(".") for module_name in modules]
    prefix: list[str] = []
    while True:
        depth = len(prefix)
        below = [parts for parts in split if len(parts) > depth and parts[:depth] == prefix]
        children = {parts[depth] for parts in below}
        if depth == 0:
            packages = {parts[0] for parts in below if len(parts) > 1}
            if len(packages) == 1:
                prefix.append(next(iter(packages)))
                continue
            return ""
        if len(children) == 1:
            only_child = next(iter(children))
            has_grandchildren = any(len(parts) > depth + 1 for parts in below)
            if not has_grandchildren:
                return ".".join(prefix)
            prefix.append(only_child)
            continue
        return ".".join(prefix)


def _component_of(module_name: str, scope: str) -> str | None:
    if not scope:
        return module_name.split(".", 1)[0]
    if not module_name.startswith(f"{scope}."):
        return None
    child = module_name[len(scope) + 1 :].split(".", 1)[0]
    return f"{scope}.{child}"


def _longest_chain(dag: nx.DiGraph) -> list[str]:
    """Longest path by node count, then by import weight, then by name."""
    best: dict[str, tuple[int, int, list[str]]] = {}
    for node in reversed(list(nx.lexicographical_topological_sort(dag))):
        best_length, best_weight, best_path = 1, 0, [node]
        for successor in sorted(dag.successors(node)):
            length, weight, path = best[successor]
            weight += dag.edges[node, successor]["count"]
            if (length + 1, weight) > (best_length, best_weight):
                best_length, best_weight, best_path = length + 1, weight, [node, *path]
        best[node] = (best_length, best_weight, best_path)

    chain: list[str] = []
    chain_key = (0, 0)
    for node in sorted(best):
        length, weight, path = best[node]
        if (length, weight) > chain_key:
            chain_key = (length, weight)
            chain = path
    return chain


def _break_tangles(
    component_graph: nx.DiGraph,
) -> tuple[list[tuple[str, str]], list[list[str]]]:
    """Split component loops into suspected leaks and genuine tangles.

    Within each strongly connected group, repeatedly cut the lightest import
    edge that still sits on a loop until no loop remains. If the cut edges are
    a small minority of the group's imports they are most likely accidents
    (leaks); otherwise the whole group is reported as tangled.
    """
    leaks: list[tuple[str, str]] = []
    tangled: list[list[str]] = []
    groups = sorted(
        sorted(component_set)
        for component_set in nx.strongly_connected_components(component_graph)
        if len(component_set) > 1
    )
    for members in groups:
        remaining = component_graph.subgraph(members).copy()
        total = sum(data["count"] for _, _, data in remaining.edges(data=True))
        cut: list[tuple[str, str]] = []
        while True:
            looping = [
                edge
                for loop in nx.strongly_connected_components(remaining)
                if len(loop) > 1
                for edge in remaining.subgraph(loop).edges
            ]
            if not looping:
                break
            lightest = min(looping, key=lambda edge: (remaining.edges[edge]["count"], edge))
            cut.append(lightest)
            remaining.remove_edge(*lightest)
        cut_weight = sum(component_graph.edges[edge]["count"] for edge in cut)
        if cut_weight * _LEAK_RATIO <= total - cut_weight:
            leaks.extend(cut)
        else:
            tangled.append(members)
    return leaks, tangled


def _is_adjacent_chain(chain: list[str], component_graph: nx.DiGraph) -> bool:
    position = {component: index for index, component in enumerate(chain)}
    for source, target in component_graph.edges:
        if source in position and target in position:
            if position[target] - position[source] != 1:
                return False
    return True


def _independent_group(
    component_graph: nx.DiGraph,
    candidates: list[str],
) -> list[str]:
    """Greedy maximal set of candidates that never reach one another."""
    condensed = nx.condensation(component_graph)
    mapping = condensed.graph["mapping"]
    descendants = {
        node: nx.descendants(condensed, node) for node in condensed.nodes
    }

    def comparable(first: str, second: str) -> bool:
        first_id, second_id = mapping[first], mapping[second]
        return (
            first_id == second_id
            or second_id in descendants[first_id]
            or first_id in descendants[second_id]
        )

    comparability = {
        candidate: sum(
            1 for other in candidates if other != candidate and comparable(candidate, other)
        )
        for candidate in candidates
    }
    chosen: list[str] = []
    for candidate in sorted(candidates, key=lambda name: (comparability[name], name)):
        if all(not comparable(candidate, member) for member in chosen):
            chosen.append(candidate)
    return sorted(chosen) if len(chosen) >= 2 else []


def summarize_names(names: list[str], separator: str, *, limit: int = 6) -> str:
    """Join names, cutting long lists down to the first few."""
    if len(names) <= limit:
        return separator.join(names)
    return f"{separator.join(names[:limit])} (+{len(names) - limit} more)"


def _q(text: str) -> str:
    """Quote a module name or label the way the README's examples do."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "rule"


def infer_architecture(graph: nx.DiGraph, project_root: Path) -> Inference:
    """Infer passing architecture rules from an import graph."""
    modules = sorted(
        node
        for node in graph.nodes
        if not any(_is_ignored_segment(part) for part in node.split("."))
    )
    module_set = set(modules)
    scope = _choose_scope(modules)
    scoped_modules = [module_name for module_name in modules if _within(module_name, scope)]
    scoped_set = set(scoped_modules)
    scoped_edges = [
        (source, target)
        for source, target in graph.edges
        if source in scoped_set and target in scoped_set and source != target
    ]

    component_graph = nx.DiGraph()
    for module_name in scoped_modules:
        component = _component_of(module_name, scope)
        if component is not None and component != scope:
            component_graph.add_node(component)

    rollup: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for source, target in scoped_edges:
        source_component = _component_of(source, scope)
        target_component = _component_of(target, scope)
        if (
            source_component is None
            or target_component is None
            or source_component == target_component
            or source_component not in component_graph
            or target_component not in component_graph
        ):
            continue
        rollup.setdefault((source_component, target_component), []).append((source, target))

    component_edges: dict[tuple[str, str], ComponentEdge] = {}
    for (source_component, target_component), pairs in sorted(rollup.items()):
        locations = sorted(
            _relative_location(graph.edges[source, target], project_root)
            for source, target in pairs
        )
        component_edges[(source_component, target_component)] = ComponentEdge(
            source=source_component,
            target=target_component,
            count=len(pairs),
            locations=locations,
        )
        component_graph.add_edge(source_component, target_component, count=len(pairs))

    facade_importers = sorted(
        {
            source
            for source, target in graph.edges
            if scope and target == scope and source in scoped_set and source != scope
        }
    )

    inference = Inference(
        scope=scope,
        facade_importers=facade_importers,
        module_count=len(scoped_modules),
        import_count=len(scoped_edges),
        components=sorted(component_graph.nodes),
    )

    connected = [
        component
        for component in component_graph.nodes
        if component_graph.degree(component) > 0
    ]
    # Loops between packages: a few rare imports are suspected leaks and are
    # set aside for the layering analysis; anything else is genuinely tangled.
    leak_edges, inference.tangled = _break_tangles(component_graph)
    tangled_members = {member for members in inference.tangled for member in members}
    clean_graph = component_graph.copy()
    clean_graph.remove_edges_from(leak_edges)
    for source_component, target_component in leak_edges:
        leak = component_edges[(source_component, target_component)]
        # The edge sat inside a loop, so a path back exists without it.
        without_leak = component_graph.copy()
        without_leak.remove_edge(source_component, target_component)
        leak.closes = nx.shortest_path(without_leak, target_component, source_component)
        inference.leaks.append(leak)
    inference.leaks.sort(key=lambda leak: (leak.count, leak.source, leak.target))
    inference.leaks = inference.leaks[:_MAX_LEAK_RULES]

    # Layers: the longest chain of direct downward dependencies. An upward
    # import between two chain members would close a loop, so once leaks are
    # set aside the rule holds by construction.
    layered = clean_graph.subgraph(
        component for component in connected if component not in tangled_members
    ).copy()
    chain = _longest_chain(layered) if layered.number_of_edges() else []
    if len(chain) >= 2:
        position = {component: index for index, component in enumerate(chain)}
        inference.layers = chain
        inference.layer_leaks = [
            component_edges[(source, target)]
            for source, target in leak_edges
            if source in position and target in position and position[target] < position[source]
        ]
        inference.layers_leaky = bool(inference.layer_leaks)
        inference.layers_adjacent = (
            len(chain) >= 3
            and not inference.layers_leaky
            and _is_adjacent_chain(chain, component_graph)
        )

    # Independence: packages that consume others (so they have a role, not
    # just shared utilities) and never reach each other, even indirectly and
    # even through a suspected leak. Packages that import the scope package
    # itself are left out: what they use through it is invisible.
    facade_components = {_component_of(module_name, scope) for module_name in facade_importers}
    consumers = [
        component
        for component in connected
        if component not in tangled_members
        and component not in facade_components
        and clean_graph.out_degree(component) > 0
    ]
    inference.independent = _independent_group(component_graph, consumers)

    # Boundaries: internal/_private packages only imported from their parent.
    packages = {
        ".".join(parts[:index])
        for parts in (module_name.split(".") for module_name in scoped_modules)
        for index in range(1, len(parts))
    }
    candidates = sorted(
        (
            package
            for package in packages | module_set
            if _within(package, scope)
            and package != scope
            and (
                package.rsplit(".", 1)[-1] == "internal"
                or (
                    package in packages
                    and _is_dunder_free_private(package.rsplit(".", 1)[-1])
                )
            )
        ),
        key=lambda name: (name.count("."), name),
    )
    for candidate in candidates:
        if len(inference.protected) >= _MAX_BOUNDARY_RULES:
            break
        parent = candidate.rsplit(".", 1)[0] if "." in candidate else ""
        if not parent or parent == scope:
            continue
        if any(_within(candidate, protected) for protected, _, _ in inference.protected):
            continue
        importers = {
            source
            for source, target in graph.edges
            if _within(target, candidate) and not _within(source, candidate)
        }
        outsiders = {source for source in importers if not _within(source, parent)}
        is_internal = candidate.rsplit(".", 1)[-1] == "internal"
        if outsiders and not is_internal:
            continue
        if not importers and not is_internal:
            continue
        inference.protected.append((candidate, parent, bool(outsiders)))

    # Cycles between modules.
    scoped_graph = graph.subgraph(scoped_modules)
    cycle_sets = sorted(
        (
            sorted(component_set)
            for component_set in nx.strongly_connected_components(scoped_graph)
            if len(component_set) > 1
        ),
        key=lambda members: (-len(members), members),
    )
    for members in cycle_sets:
        cycle = nx.find_cycle(scoped_graph.subgraph(members), source=members[0])
        inference.cycles.append([edge[0] for edge in cycle] + [cycle[0][0]])
    for module_name in sorted(scoped_set):
        if scoped_graph.has_edge(module_name, module_name):
            inference.cycles.append([module_name, module_name])

    inference.rules = _build_rules(inference, component_edges)
    return inference


def _build_rules(
    inference: Inference,
    component_edges: dict[tuple[str, str], ComponentEdge],
) -> list[InferredRule]:
    scope = inference.scope
    rules: list[InferredRule] = []

    if inference.layers:
        chain = inference.layers

        def layers_call(members: list[str]) -> list[str]:
            return [
                "layers(",
                "    [",
                *[f"        {_q(layer)}," for layer in members],
                "    ]",
                ").are_ordered()",
            ]

        flow = []
        for upper, lower in zip(chain, chain[1:]):
            edge = component_edges[(upper, lower)]
            plural = "import" if edge.count == 1 else "imports"
            flow.append(f"  {upper} -> {lower} ({edge.count} {plural})")

        if not inference.layers_leaky:
            comment = ["Dependencies flow top to bottom; nothing imports upward today:", *flow]
            if inference.layers_adjacent:
                comment.append(
                    "No layer is skipped either: swap in are_adjacent() for the strict version."
                )
            rules.append(
                InferredRule(
                    name="layers-flow-downward",
                    group="Layers",
                    call=layers_call(chain),
                    comment=comment,
                    rule_imports=("layers",),
                )
            )
        else:
            # The layers the stray imports reach into are left out of an
            # enforced rule, so every other upward import still fails today.
            reached = {leak.target for leak in inference.layer_leaks}
            enforced = [layer for layer in chain if layer not in reached]
            reached_names = ", ".join(_short(layer, scope) for layer in chain if layer in reached)
            if len(enforced) >= 2:
                rules.append(
                    InferredRule(
                        name="layers-flow-downward",
                        group="Layers",
                        call=layers_call(enforced),
                        comment=[
                            "Enforced today: the layering below, minus "
                            f"{reached_names}, which an upward",
                            "import already reaches into (see the next rule).",
                        ],
                        rule_imports=("layers",),
                    )
                )

            upward = sum(leak.count for leak in inference.layer_leaks)
            upward_text = "1 import goes" if upward == 1 else f"{upward} imports go"
            fix_text = "Fix it" if upward == 1 else "Fix them"
            comment = [
                "Dependencies flow top to bottom:",
                *flow,
                f"except that {upward_text} upward, most likely by accident:",
            ]
            for leak in inference.layer_leaks:
                for location in leak.locations[:_MAX_EVIDENCE_LINES]:
                    comment.append(
                        f"  {_short(leak.source, scope)} -> {_short(leak.target, scope)} at {location}"
                    )
            comment.append(
                f"{fix_text}, then remove @warn (and the rule above, which this one covers)."
            )
            rules.append(
                InferredRule(
                    name="all-layers-flow-downward",
                    group="Layers",
                    call=layers_call(chain),
                    comment=comment,
                    warn=True,
                    rule_imports=("layers",),
                )
            )

    if inference.independent:
        rules.append(
            InferredRule(
                name="independent-packages",
                group="Independence",
                call=[
                    "independent(",
                    "    [",
                    *[f"        {_q(member)}," for member in inference.independent],
                    "    ]",
                    ")",
                ],
                comment=[
                    "These packages never import each other today, directly or indirectly.",
                    "Keep them decoupled: share code through a lower layer instead.",
                ],
                rule_imports=("independent",),
            )
        )

    for protected, parent, has_outsiders in inference.protected:
        if has_outsiders:
            comment = [
                f"{protected} is named as internal, but code outside {parent}",
                "already imports it. Route those imports through the public API of",
                f"{parent}, then remove @warn.",
            ]
        else:
            comment = [f"{protected} is only imported from inside {parent} today."]
        rules.append(
            InferredRule(
                name=f"protect-{_slug(_short(protected, scope))}",
                group="Boundaries",
                call=[f"module({_q(protected)}).only_imported_within({_q(parent)})"],
                comment=comment,
                warn=has_outsiders,
                rule_imports=("module",),
            )
        )

    cycle_call = f"no_cycles({_q(scope)})" if scope else "no_cycles()"
    if inference.cycles:
        count = len(inference.cycles)
        places = "1 place" if count == 1 else f"{count} places"
        comment = [f"Modules import each other in a loop in {places} today, for example:"]
        for cycle in inference.cycles[:_MAX_EVIDENCE_LINES]:
            comment.append("  " + " -> ".join(_short(module_name, scope) for module_name in cycle))
        comment.append("Reported as a warning until the loops are broken; then remove @warn.")
    else:
        comment = ["There are no import cycles today. Keep it that way."]
    rules.append(
        InferredRule(
            name="no-import-cycles",
            group="Cycles",
            call=[cycle_call],
            comment=comment,
            warn=bool(inference.cycles),
            rule_imports=("no_cycles",),
        )
    )

    for leak in inference.leaks:
        if leak in inference.layer_leaks:
            continue  # already reported, with its location, by the layers rule
        plural = "import" if leak.count == 1 else "imports"
        loop = " -> ".join(_short(name, scope) for name in [*leak.closes, leak.closes[0]])
        comment = [
            f"{_short(leak.source, scope)} -> {_short(leak.target, scope)} ({leak.count} {plural}) "
            "runs against the rest of the code",
            f"and closes a loop: {loop}.",
            "Most likely an accident:",
            *[f"  {location}" for location in leak.locations[:_MAX_EVIDENCE_LINES]],
        ]
        if len(leak.locations) > _MAX_EVIDENCE_LINES:
            comment.append(f"  ... and {len(leak.locations) - _MAX_EVIDENCE_LINES} more")
        source_name = _slug(_short(leak.source, scope))
        target_name = _slug(_short(leak.target, scope))
        rules.append(
            InferredRule(
                name=f"{source_name}-must-not-import-{target_name}",
                group="Suspected leaks",
                call=[f"imports({_q(leak.source)}).must_not_import({_q(leak.target)})"],
                comment=comment,
                warn=True,
                base_imports=("imports",),
            )
        )

    return rules


def _function_name(rule_name: str, used: set[str]) -> str:
    base = re.sub(r"\W+", "_", rule_name).strip("_").lower() or "rule"
    if base[0].isdigit() or keyword.iskeyword(base):
        base = f"rule_{base}"
    name = base
    counter = 2
    while name in used:
        name = f"{base}_{counter}"
        counter += 1
    used.add(name)
    return name


def render_architecture_py(inference: Inference, *, today: date | None = None) -> str:
    """Render an inference as a commented, ready-to-run architecture.py."""
    generated_on = (today or date.today()).isoformat()
    subject = inference.scope or "this project"
    warn_count = len(inference.warning_rules)
    module_noun = "module" if inference.module_count == 1 else "modules"
    import_noun = "import" if inference.import_count == 1 else "imports"

    docstring = [
        f'"""Architecture rules for {subject}, inferred by `archetype init --infer`.',
        "",
        f"Generated on {generated_on} from the import graph as it stands",
        f"({inference.module_count} {module_noun}, {inference.import_count} internal {import_noun}).",
        "Every rule describes structure the code already has, so it passes today",
        "and fails only when a change introduces new drift.",
    ]
    if warn_count:
        docstring += [
            "",
            f"{warn_count} rule(s) are marked @warn: they point at problems that",
            "already exist. They are reported but never fail the run. Fix them,",
            "then delete the @warn line to lock the fix in.",
        ]
    if inference.tangled:
        docstring += [
            "",
            "Packages that import each other in both directions cannot be layered",
            "yet, so they are left out of the layer and independence rules:",
            *[
                "  " + summarize_names([_short(name, inference.scope) for name in members], " <-> ")
                for members in inference.tangled
            ],
        ]
    if inference.facade_importers:
        count = len(inference.facade_importers)
        noun = "module imports" if count == 1 else "modules import"
        docstring += [
            "",
            f"{count} {noun} the {inference.scope} package itself (`import {inference.scope}`).",
            "Whatever they use through it is invisible to import rules, so those",
            "packages are left out of the independence rule.",
        ]
    docstring += [
        "",
        "This file is yours now: rename, tighten, or delete rules freely.",
        '"""',
    ]

    base_imports = {"rule"}
    rule_imports: set[str] = set()
    groups: dict[str, list[InferredRule]] = {}
    for inferred in inference.rules:
        base_imports.update(inferred.base_imports)
        rule_imports.update(inferred.rule_imports)
        if inferred.warn:
            base_imports.add("warn")
        groups.setdefault(inferred.group, []).append(inferred)
    if groups:
        base_imports.add("group")

    lines = [*docstring, ""]
    lines.append(f"from archetype import {', '.join(sorted(base_imports))}")
    if rule_imports:
        lines.append(f"from archetype.rules import {', '.join(sorted(rule_imports))}")

    used_names: set[str] = set()
    for group_name, members in groups.items():
        lines += ["", "", f"with group({_q(group_name)}):"]
        for index, inferred in enumerate(members):
            if index:
                lines.append("")
            for comment_line in inferred.comment:
                lines.append(f"    # {comment_line}".rstrip())
            if inferred.downgraded_at:
                count = len(inferred.downgraded_at)
                noun = "violation" if count == 1 else "violations"
                lines.append(
                    f"    # Marked @warn: checking it found {count} {noun} outside the code"
                )
                lines.append("    # analyzed for inference (tests, examples, ...), for example:")
                for location in inferred.downgraded_at[:_MAX_EVIDENCE_LINES]:
                    lines.append(f"    #   {location}")
            lines.append(f"    @rule({_q(inferred.name)})")
            if inferred.warn:
                lines.append("    @warn")
            lines.append(f"    def {_function_name(inferred.name, used_names)}() -> None:")
            for call_line in inferred.call:
                lines.append(f"        {call_line}")

    return "\n".join(lines) + "\n"


def run_architecture_source(
    source: str,
    graph: nx.DiGraph,
    *,
    analysis_root: Path,
    project_root: Path,
) -> list[RuleResult]:
    """Execute architecture.py source against a graph and return rule results.

    Runs in isolation: the global rule registry and loaded-project state are
    restored afterwards, so this is safe to call from a CLI command or a test.
    """
    saved_registry = (
        list(registry._rules),
        list(registry._entries),
        dict(registry._by_name),
    )
    saved_state = (
        query_module._current_graph,
        query_module._current_root,
        query_module._project_root,
        query_module._exclude_patterns,
    )
    try:
        registry.clear()
        query_module._current_graph = graph
        query_module._current_root = analysis_root
        query_module._project_root = project_root
        query_module._exclude_patterns = ()
        namespace: dict[str, object] = {"__name__": "_archetype_inferred_architecture"}
        exec(compile(source, "architecture.py", "exec"), namespace)  # noqa: S102
        return registry.run_all()
    finally:
        registry._rules[:] = saved_registry[0]
        registry._entries[:] = saved_registry[1]
        registry._by_name.clear()
        registry._by_name.update(saved_registry[2])
        (
            query_module._current_graph,
            query_module._current_root,
            query_module._project_root,
            query_module._exclude_patterns,
        ) = saved_state


def _violation_location(violation: Violation, project_root: Path) -> str:
    return _relative_location(
        {"file": str(violation.file), "line": violation.line}, project_root
    )


def _is_blocking_failure(result: RuleResult) -> bool:
    return result.error is not None or (not result.passed and not result.warned)


def build_inferred_architecture(
    project_root: Path,
    *,
    today: date | None = None,
) -> InferredArchitecture:
    """Build the project's import graph, infer rules, and verify they pass.

    The graph is built the same way `archetype check` builds it: src layouts
    are analyzed from ``src/`` and exclusions from ``archetype.toml`` apply.
    """
    resolved_root = project_root.resolve()
    structure = detect_project_structure(resolved_root)
    analysis_root = resolved_root / "src" if structure.get("layout") == "src" else resolved_root
    config = load_check_config(resolved_root)
    excludes = normalize_exclude_patterns(config.exclude_patterns)
    graph = build_import_graph(analysis_root, exclude_patterns=excludes)
    # Infer from production code only, but verify against the same graph
    # `archetype check` will see.
    production_graph = build_import_graph(
        analysis_root,
        exclude_patterns=normalize_exclude_patterns([*excludes, *_IGNORED_DIRECTORIES]),
    )

    inference = infer_architecture(production_graph, resolved_root)
    content = render_architecture_py(inference, today=today)
    results = run_architecture_source(
        content, graph, analysis_root=analysis_root, project_root=resolved_root
    )

    failing = {result.name: result for result in results if _is_blocking_failure(result)}
    if failing:
        for inferred in inference.rules:
            result = failing.get(inferred.name)
            if result is None or inferred.warn:
                continue
            inferred.warn = True
            inferred.downgraded_at = [
                _violation_location(violation, resolved_root)
                for violation in result.violations
            ] or [f"error: {result.error}"]
        content = render_architecture_py(inference, today=today)
        results = run_architecture_source(
            content, graph, analysis_root=analysis_root, project_root=resolved_root
        )

    return InferredArchitecture(inference=inference, content=content, results=results)
