"""Synthetic project generators for benchmark scenarios."""

from __future__ import annotations

import random
from pathlib import Path


def generate_synthetic_project(
    root_dir: Path,
    package_name: str,
    num_modules: int,
    imports_per_module: int,
) -> Path:
    """Generate an acyclic synthetic Python project for benchmarking."""
    if num_modules <= 0:
        raise ValueError("num_modules must be greater than 0")
    if imports_per_module < 0:
        raise ValueError("imports_per_module cannot be negative")

    root_dir.mkdir(parents=True, exist_ok=True)
    package_dir = root_dir / package_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "init.py").write_text("", encoding="utf-8")

    layers = ("api", "services", "db")
    layer_dirs: dict[str, Path] = {}
    for layer in layers:
        layer_dir = package_dir / layer
        layer_dir.mkdir(parents=True, exist_ok=True)
        (layer_dir / "init.py").write_text("", encoding="utf-8")
        layer_dirs[layer] = layer_dir

    modules: list[tuple[str, str, Path]] = []
    for index in range(num_modules):
        layer = layers[index % len(layers)]
        module_name = f"module_{index:04d}"
        module_qualified_name = f"{package_name}.{layer}.{module_name}"
        module_path = layer_dirs[layer] / f"{module_name}.py"
        modules.append((layer, module_qualified_name, module_path))

    rng = random.Random(
        f"{root_dir.resolve()}|{package_name}|{num_modules}|{imports_per_module}"
    )

    for index, (_, module_qualified_name, module_path) in enumerate(modules):
        import_lines: list[str] = ["from __future__ import annotations", "", "import math"]

        available_targets = [target for _, target, _ in modules[:index]]
        target_count = min(imports_per_module, len(available_targets))
        selected_targets = rng.sample(available_targets, k=target_count) if target_count else []

        for target in sorted(selected_targets):
            import_lines.append(f"import {target}")

        class_name = f"Module{index:04d}Service"
        function_name = f"handle_module_{index:04d}"

        body = [
            *import_lines,
            "",
            "",
            f"class {class_name}:",
            "    def __init__(self) -> None:",
            f"        self.name = \"{module_qualified_name}\"",
            "",
            "    def execute(self) -> str:",
            "        return self.name.upper()",
            "",
            "",
            f"def {function_name}(value: int) -> int:",
            "    return int(math.sqrt((value + 1) * (value + 1)))",
            "",
        ]
        module_path.write_text("\n".join(body), encoding="utf-8")

    return package_dir


def generate_layered_project(root_dir: Path, scale_factor: int = 1) -> Path:
    """Generate a layered benchmark project using predefined scale targets."""
    presets = {
        1: (50, 3),
        2: (150, 5),
        4: (500, 8),
        10: (1000, 10),
    }
    if scale_factor in presets:
        module_count, imports_per_module = presets[scale_factor]
    else:
        module_count = max(50, 50 * scale_factor)
        imports_per_module = max(3, min(10, 2 + scale_factor))

    package_name = f"synthetic_scale_{scale_factor}"
    return generate_synthetic_project(
        root_dir=root_dir,
        package_name=package_name,
        num_modules=module_count,
        imports_per_module=imports_per_module,
    )
