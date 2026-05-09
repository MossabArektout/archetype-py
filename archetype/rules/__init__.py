"""Built-in architecture rules shipped with Archetype."""

from archetype.rules.layers import layers
from archetype.rules.boundaries import module
from archetype.rules.naming import classes_in, functions_in
from archetype.rules.cycles import no_cycles

__all__ = ["layers", "module", "classes_in", "functions_in", "no_cycles"]
