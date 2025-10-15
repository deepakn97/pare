#!/usr/bin/env python3
"""Fixes common LLM-generation issues in Python scenario files.

  1) Convert JSON booleans/null (true/false/null) -> True/False/None (outside strings/comments).
  2) Rewrite bad imports (e.g., 'from mare import (...)') to correct modules
     using an import map derived from 'import_instructions' you already generate.

USAGE:
  # If you already have the import_instructions text file (from make_import_instructions)
  python fix_generated_scenario.py --in scenario.py --out scenario.fixed.py \
      --imports-file import_instructions.txt

  # Or build the map from a precomputed JSON catalog (from scan_package)
  python fix_generated_scenario.py --in scenario.py --out scenario.fixed.py \
      --catalog-json apps_catalog.json

  # In-place edit
  python fix_generated_scenario.py --in scenario.py --write
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import tokenize
from pathlib import Path
from typing import Any

# -------------------------
# 1) Literal normalization
# -------------------------


def normalize_json_literals(src: str) -> str:
    """Replace bare identifiers true/false/null with True/False/None.

    ONLY when they appear as NAME tokens (not inside strings/comments).

    """
    out_tokens: list[tokenize.TokenInfo] = []
    g = tokenize.generate_tokens(io.StringIO(src).readline)
    for tok in g:
        if tok.type == tokenize.NAME and tok.string in {"true", "false", "null"}:
            repl = {"true": "True", "false": "False", "null": "None"}[tok.string]
            tok = tokenize.TokenInfo(tok.type, repl, tok.start, tok.end, tok.line)
        out_tokens.append(tok)
    return tokenize.untokenize(out_tokens)


# ---------------------------------
# 2) Build symbol -> module mapping
# ---------------------------------

_IMPORT_LINE_RE = re.compile(r"^\s*from\s+([a-zA-Z0-9_.]+)\s+import\s+([A-Za-z0-9_,\s]+)")


def parse_import_instructions(text: str) -> dict[str, str]:
    """Parse lines like.

      'from are.simulation.apps.contacts import Contact, ContactsApp'
    into {'Contact': 'are.simulation.apps.contacts', 'ContactsApp': 'are.simulation.apps.contacts'}
    Ignores comment/preamble lines.

    """
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        m = _IMPORT_LINE_RE.match(line)
        if not m:
            continue
        module, names_blob = m.group(1), m.group(2)
        for name in [n.strip() for n in names_blob.split(",") if n.strip()]:
            mapping[name] = module
    return mapping


def mapping_from_catalog_json(catalog: dict[str, Any]) -> dict[str, str]:
    """Convert catalog JSON to symbol-to-module mapping."""
    mapping: dict[str, str] = {}
    for m in catalog.get("modules", []):
        module = m.get("module")
        for item in m.get("exports", {}).get("classes", []):
            mapping[item["name"]] = module
        for item in m.get("exports", {}).get("functions", []):
            mapping[item["name"]] = module
    return mapping


# ----------------------------
# 3) Import rewriting on AST
# ----------------------------


class ImportRewriter(ast.NodeTransformer):
    """Rewrites 'from X import (A, B, ...)' to grouped per-correct-module imports.

    using a symbol->module mapping. Drops unknown symbols (optionally).

    """

    def __init__(self, sym2mod: dict[str, str], drop_unknown: bool = False) -> None:
        """Initialize the ImportRewriter with symbol-to-module mapping."""
        self.sym2mod = sym2mod
        self.drop_unknown = drop_unknown
        self.collected_needed: set[str] = set()  # symbols referenced in code

    def visit_Name(self, node: ast.Name) -> ast.Name:
        """Visit a Name node in the AST."""
        if isinstance(node.ctx, (ast.Load, ast.Store, ast.Del)) and node.id in self.sym2mod:
            self.collected_needed.add(node.id)
        return node

    def _collect_imported_symbols(self, tree: ast.Module) -> tuple[list[ast.stmt], set[str]]:
        """Collect imported symbols and filter statements."""
        new_body: list[ast.stmt] = []
        imported_symbols: set[str] = set()

        for stmt in tree.body:
            if isinstance(stmt, ast.ImportFrom):
                # Keep non-symbol imports (e.g., "from x import *") untouched
                if stmt.names and all(a.name != "*" for a in stmt.names):
                    # Accumulate imported symbols (for potential use even if not referenced yet)
                    for alias in stmt.names:
                        imported_symbols.add(alias.asname or alias.name)
                    # Skip rewriting here; we will rebuild clean imports later
                    new_body.append(stmt)
                else:
                    new_body.append(stmt)
            else:
                new_body.append(stmt)

        return new_body, imported_symbols

    def _group_symbols_by_module(self, required_symbols: set[str]) -> dict[str, list[str]]:
        """Group required symbols by their canonical module."""
        group: dict[str, list[str]] = {}
        for sym in sorted(required_symbols):
            if sym in self.sym2mod:
                group.setdefault(self.sym2mod[sym], []).append(sym)
        return group

    def _filter_duplicate_imports(self, new_body: list[ast.stmt], required_symbols: set[str]) -> list[ast.stmt]:
        """Remove duplicate imports that will be replaced by canonical imports."""
        filtered_body: list[ast.stmt] = []
        for stmt in new_body:
            if isinstance(stmt, ast.ImportFrom) and stmt.names and all(a.name != "*" for a in stmt.names):
                remaining_aliases = []
                for alias in stmt.names:
                    name = alias.asname or alias.name
                    # if we are going to re-add this symbol canonically, drop it here
                    if name not in required_symbols:
                        remaining_aliases.append(alias)
                if remaining_aliases:
                    stmt.names = remaining_aliases
                    filtered_body.append(stmt)
                # if none remain, drop the stmt entirely
            else:
                filtered_body.append(stmt)
        return filtered_body

    def _create_canonical_imports(self, symbol_groups: dict[str, list[str]]) -> list[ast.stmt]:
        """Create canonical grouped import statements."""
        canonical_imports: list[ast.stmt] = []
        for module in sorted(symbol_groups.keys()):
            names = [ast.alias(name=sym, asname=None) for sym in sorted(symbol_groups[module])]
            canonical_imports.append(ast.ImportFrom(module=module, names=names, level=0))
        return canonical_imports

    def rewrite_imports(self, tree: ast.Module) -> ast.Module:
        """Rewrite imports in the AST to use the correct modules."""
        # Collect imported symbols and filter statements
        new_body, imported_symbols = self._collect_imported_symbols(tree)

        # Determine required set = used symbols U originally imported symbols that we can map
        required = {s for s in (self.collected_needed | imported_symbols) if s in self.sym2mod}

        # Group required symbols by their canonical module
        symbol_groups = self._group_symbols_by_module(required)

        # Remove any existing per-symbol imports for those symbols to avoid duplicates
        filtered_body = self._filter_duplicate_imports(new_body, required)

        # Prepend canonical grouped imports (nicely sorted)
        canonical_imports = self._create_canonical_imports(symbol_groups)

        tree.body = canonical_imports + filtered_body
        return tree


# ----------------------------
# 4) Driver
# ----------------------------


def fix_file(src_text: str, import_map: dict[str, str], drop_unknown: bool = False) -> str:
    """Fix imports and normalize literals in generated scenario file."""
    # Step 1: normalize True/False/None (safe even if file initially unparsable)
    normalized = normalize_json_literals(src_text)

    # Step 2: AST import fix (only if parseable)
    try:
        tree = ast.parse(normalized)
    except SyntaxError:
        # Return literals-normalized code so at least it runs
        return normalized

    # Walk once to collect used symbol names
    rewriter = ImportRewriter(import_map, drop_unknown=drop_unknown)
    rewriter.visit(tree)
    tree = rewriter.rewrite_imports(tree)

    # Unparse (3.9+)
    fixed = ast.unparse(tree)
    return fixed + ("\n" if not fixed.endswith("\n") else "")


def main() -> None:
    """Command-line interface for fixing generated scenario files."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True, help="Path to generated .py file")
    ap.add_argument("--out", dest="outfile", help="Write to this file (or use --write)")
    ap.add_argument("--write", action="store_true", help="Edit in place")
    ap.add_argument("--imports-file", help="Path to text from make_import_instructions()")
    ap.add_argument("--catalog-json", help="Path to JSON from scan_package()")
    ap.add_argument("--drop-unknown", action="store_true", help="Drop symbols not found in mapping")
    args = ap.parse_args()

    if not args.imports_file and not args.catalog_json:
        ap.error("Provide either --imports-file or --catalog-json to build symbol->module mapping.")

    if args.imports_file:
        txt = Path(args.imports_file).read_text(encoding="utf-8")
        import_map = parse_import_instructions(txt)
    else:
        catalog = json.loads(Path(args.catalog_json).read_text(encoding="utf-8"))
        import_map = mapping_from_catalog_json(catalog)

    src = Path(args.infile).read_text(encoding="utf-8")
    fixed = fix_file(src, import_map, drop_unknown=args.drop_unknown)

    outpath = args.infile if args.write else (args.outfile or (args.infile + ".fixed.py"))
    Path(outpath).write_text(fixed, encoding="utf-8")
    print(f"Wrote {outpath}")


if __name__ == "__main__":
    main()
