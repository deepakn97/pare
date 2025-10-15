# are/simulation/list_all_app_imports.py
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------- discovery ----------
def discover_module_paths(pkg_name: str) -> list[Path]:
    """Discover all filesystem paths for a Python package."""
    spec = importlib.util.find_spec(pkg_name)
    if spec is None or spec.submodule_search_locations is None:
        raise ModuleNotFoundError(f"Package '{pkg_name}' not found or is not a package.")
    return [Path(p) for p in spec.submodule_search_locations]


def iter_all_py_files(pkg_name: str) -> list[tuple[str, Path]]:
    """Return (module_name, file_path) for every .py in the package tree."""
    roots = discover_module_paths(pkg_name)
    out: list[tuple[str, Path]] = []
    for root in roots:
        for path in root.rglob("*.py"):
            rel = path.relative_to(root)
            if rel.name == "__init__.py":
                parts = [pkg_name, *list(rel.parent.parts)]
            else:
                parts = [pkg_name, *list(rel.with_suffix("").parts)]
            mod_name = ".".join([p for p in parts if p])
            out.append((mod_name, path))
    return out


# ---------- AST helpers ----------
def _doc_firstline(text: str | None, max_len: int) -> str:
    if not text:
        return ""
    first = text.strip().splitlines()[0].strip()
    return (first[: max_len - 1] + "…") if max_len and len(first) > max_len else first


def _format_function_argument(arg: ast.arg, has_default: bool = False) -> str:
    """Format a single function argument."""
    base = arg.arg
    return f"{base}=…" if has_default else base


def _calculate_default_flags(positional_args: list[ast.arg], defaults: list[ast.expr]) -> list[bool]:
    """Calculate which positional arguments have defaults."""
    default_flags = [False] * len(positional_args)
    for i in range(len(defaults)):
        default_flags[-(i + 1)] = True
    return default_flags


def _add_positional_args_to_signature(
    args: ast.arguments, default_flags: list[bool], parts: list[str], max_params: int
) -> None:
    """Add positional-only and regular positional arguments to signature parts."""
    idx = 0

    # Positional-only (py>=3.8)
    posonly = getattr(args, "posonlyargs", []) or []
    for a in posonly:
        if len(parts) >= max_params - 1:  # -1 for potential "..."
            break
        parts.append(_format_function_argument(a, has_default=default_flags[idx]))
        idx += 1
    if posonly:
        parts.append("/")

    # Regular positional args
    pos = args.args or []
    for a in pos:
        if len(parts) >= max_params - 1:  # -1 for potential "..."
            break
        parts.append(_format_function_argument(a, has_default=default_flags[idx]))
        idx += 1


def _add_varargs_and_kwargs_to_signature(args: ast.arguments, parts: list[str], max_params: int) -> None:
    """Add varargs (*args) and kwargs (**kwargs) to signature parts."""
    if args.vararg:
        if len(parts) < max_params:
            parts.append("*" + args.vararg.arg)
    elif args.kwonlyargs and len(parts) < max_params:
        # keyword-only section marker if any kwonlyargs exist
        parts.append("*")

    for i, a in enumerate(args.kwonlyargs):
        if len(parts) >= max_params:
            break
        has_def = bool(args.kw_defaults and args.kw_defaults[i] is not None)
        parts.append(_format_function_argument(a, has_default=has_def))

    if args.kwarg and len(parts) < max_params:
        parts.append("**" + args.kwarg.arg)


def _sig_from_func(node: ast.FunctionDef, max_params: int = 8) -> str:
    """Very light, static signature: fn(a, b, *, c=..., **kwargs)."""
    args = node.args
    parts: list[str] = []

    # Calculate which arguments have defaults
    posonly = getattr(args, "posonlyargs", []) or []
    pos = args.args or []
    all_positional = posonly + pos
    defaults = args.defaults or []
    default_flags = _calculate_default_flags(all_positional, defaults)

    # Add positional arguments
    _add_positional_args_to_signature(args, default_flags, parts, max_params)

    # Add varargs and kwargs
    _add_varargs_and_kwargs_to_signature(args, parts, max_params)

    # Truncate if too many parameters
    shown = parts[:max_params]
    if len(parts) > max_params:
        shown.append("…")
    return f"{node.name}({', '.join(shown)})"


def _extract_exports_from_all(tree: ast.Module) -> set[str]:
    """Extract exported names from __all__ declarations."""
    exports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (
                    isinstance(t, ast.Name)
                    and t.id == "__all__"
                    and isinstance(node.value, (ast.List, ast.Tuple, ast.Set))
                ):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Str):
                            exports.add(elt.s)
    return exports


def _should_include_name(name: str, exports: set[str]) -> bool:
    """Check if a name should be included based on export rules."""
    return not (name.startswith("_") and not (exports and name in exports))


def _process_class_node(
    node: ast.ClassDef, exports: set[str], want_docs: bool, want_sigs: bool, doclen: int
) -> dict[str, str | None] | None:
    """Process a ClassDef node and return class info if it should be included."""
    name = node.name
    if not _should_include_name(name, exports):
        return None

    item: dict[str, str | None] = {"name": name}
    if want_docs:
        item["doc"] = _doc_firstline(ast.get_docstring(node), doclen)
    if want_sigs:
        # For classes, provide __init__ signature if available
        init_fn = None
        for b in node.body:
            if isinstance(b, ast.FunctionDef) and b.name == "__init__":
                init_fn = b
                break
        item["sig"] = _sig_from_func(init_fn, max_params=8) if init_fn else f"{name}(...)"
    return item


def _process_function_node(
    node: ast.FunctionDef, exports: set[str], want_docs: bool, want_sigs: bool, doclen: int
) -> dict[str, str | None] | None:
    """Process a FunctionDef node and return function info if it should be included."""
    name = node.name
    if not _should_include_name(name, exports):
        return None

    func_item: dict[str, str | None] = {"name": name}
    if want_docs:
        func_item["doc"] = _doc_firstline(ast.get_docstring(node), doclen)
    if want_sigs:
        func_item["sig"] = _sig_from_func(node, max_params=8)
    return func_item


def parse_module_exports(
    file_path: Path, want_docs: bool, want_sigs: bool, doclen: int
) -> tuple[list[dict[str, str | None]], list[dict[str, str | None]]]:
    """Returns (classes, functions) where each item = {"name", "doc"?, "sig"?}.

    Only lists top-level class/def names (no underscores unless in __all__).
    """
    try:
        src = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src, filename=str(file_path))
    except Exception:
        return [], []

    # Extract exports from __all__
    exports = _extract_exports_from_all(tree)

    cls_out: list[dict[str, str | None]] = []
    fn_out: list[dict[str, str | None]] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_item = _process_class_node(node, exports, want_docs, want_sigs, doclen)
            if class_item:
                cls_out.append(class_item)

        elif isinstance(node, ast.FunctionDef):
            func_item = _process_function_node(node, exports, want_docs, want_sigs, doclen)
            if func_item:
                fn_out.append(func_item)

    return cls_out, fn_out


# ---------- main scan ----------
def scan_package(
    pkg_name: str, doclen: int = 140, include_docs: bool = True, include_sigs: bool = False
) -> dict[str, Any]:
    """Scan a Python package and extract module/class/function information."""
    roots = discover_module_paths(pkg_name)
    modules: list[dict[str, Any]] = []
    import_modules: set[str] = set()
    from_imports: set[str] = set()

    for mod_name, file_path in iter_all_py_files(pkg_name):
        classes, funcs = parse_module_exports(file_path, include_docs, include_sigs, doclen)

        modules.append({
            "module": mod_name,
            "path": str(file_path),
            "exports": {"classes": classes, "functions": funcs},
        })

        import_modules.add(f"import {mod_name}")
        for item in classes:
            from_imports.add(f"from {mod_name} import {item['name']}")
        for item in funcs:
            from_imports.add(f"from {mod_name} import {item['name']}")

    return {
        "package": pkg_name,
        "scanned_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "root_paths": [str(p) for p in roots],
        "modules": sorted(modules, key=lambda m: m["module"]),
        "import_suggestions": {"modules": sorted(import_modules), "from_imports": sorted(from_imports)},
    }


# ---------- presentation for LLM prompt ----------
def make_import_instructions(
    catalog: dict[str, Any], max_mods: int = 20, max_per_mod: int = 12, include_sigs: bool = True
) -> str:
    """Produce a concise, human-readable text blob the LLM can follow."""
    lines: list[str] = []
    pkg = catalog.get("package", "")
    lines.append("AVAILABLE PYTHON IMPORTS")
    lines.append(f"- Package root: {pkg}")
    lines.append("- You may import ONLY the symbols listed below.")
    lines.append("- Prefer `from <module> import <Symbol>` shown here. Do not guess hidden names.")
    lines.append("")

    mods = catalog.get("modules", [])
    mods = mods[:max_mods]

    for m in mods:
        module = m["module"]
        classes = m["exports"]["classes"][:max_per_mod]
        funcs = m["exports"]["functions"][:max_per_mod]
        if not classes and not funcs:
            continue
        lines.append(f"[{module}]")
        for item in classes:
            name = item["name"]
            extra = ""
            if include_sigs and item.get("sig"):
                extra = f" — {item['sig']}"
            elif item.get("doc"):
                extra = f" — {item['doc']}"
            lines.append(f"  from {module} import {name}{extra}")
        for item in funcs:
            name = item["name"]
            extra = ""
            if include_sigs and item.get("sig"):
                extra = f" — {item['sig']}"
            elif item.get("doc"):
                extra = f" — {item['doc']}"
            lines.append(f"  from {module} import {name}{extra}")
        lines.append("")  # spacer

    # some extra imports to notice:
    lines.append("  from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult")
    lines.append("  from are.simulation.scenarios.utils.registry import register_scenario")
    lines.append("  from are.simulation.types import Action, EventRegisterer, EventType")

    # Fallback example if the agent needs a template
    lines.append("EXAMPLE:")
    lines.append("  from are.simulation.apps.app import App")
    lines.append("  from are.simulation.apps.contacts import ContactsApp, Contact")
    return "\n".join(lines).rstrip()  # trim trailing newline


# ---------- CLI ----------
def main(argv: list[str] | None = None) -> int:
    """Command-line interface for scanning Python packages."""
    ap = argparse.ArgumentParser(description="Static scan of a package then emit JSON or import instructions text.")
    ap.add_argument("package", help="e.g. are.simulation.apps")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print JSON catalog.")
    ap.add_argument("--compact", action="store_true", help="Compact JSON catalog.")
    ap.add_argument("--doclen", type=int, default=140, help="Max docstring first-line length.")
    ap.add_argument("--include-sigs", action="store_true", help="Include light static signatures.")
    ap.add_argument("--emit", choices=["json", "import_instructions"], default="json", help="What to print.")
    ap.add_argument("--max-mods", type=int, default=20, help="Max modules to include in import_instructions.")
    ap.add_argument("--max-per-mod", type=int, default=12, help="Max symbols per module in import_instructions.")
    args = ap.parse_args(argv)

    catalog = scan_package(
        args.package,
        doclen=args.doclen,
        include_docs=not args.include_sigs,  # if we include sigs, we keep docs short anyway
        include_sigs=args.include_sigs,
    )

    if args.emit == "import_instructions":
        text = make_import_instructions(
            catalog, max_mods=args.max_mods, max_per_mod=args.max_per_mod, include_sigs=args.include_sigs
        )
        print(text)
        return 0

    if args.pretty:
        print(json.dumps(catalog, indent=2, ensure_ascii=False))
    elif args.compact:
        print(json.dumps(catalog, separators=(",", ":"), ensure_ascii=False))
    else:
        print(json.dumps(catalog, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # Run with: python -m are.simulation.list_all_app_imports are.simulation.apps
    sys.exit(main())
