"""API layer for the simple fixture project, including one intentional violation.

Note: direct API -> DB imports are a layer-skipping case and are kept as a future
enhancement for strict layering validation.
"""

from simple_project import db
from simple_project import services
