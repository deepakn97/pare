#!/usr/bin/env python3
# save as deduplicate_scenarios.py
from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
import tokenize
from collections import Counter


def load_and_normalize(path: str, keep_strings: bool = False) -> str:
    """Read a Python file and return a normalized text.

    - remove comments and (optionally) strings/docstrings
    - collapse whitespace
    """
    with open(path, "rb") as f:
        tokens = tokenize.tokenize(f.readline)
        out = []
        prev_was_name = False
        for tok in tokens:
            ttype, tstr = tok.type, tok.string
            if ttype in (
                tokenize.COMMENT,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.ENCODING,
                tokenize.INDENT,
                tokenize.DEDENT,
            ):
                continue
            if ttype == tokenize.STRING and not keep_strings:
                # skip string literals including docstrings
                continue
            # normalize identifiers & keywords spacing a bit
            if ttype == tokenize.NAME:
                if prev_was_name:
                    out.append(" ")
                out.append(tstr)
                prev_was_name = True
            else:
                out.append(tstr)
                prev_was_name = False
        text = "".join(out)
    # collapse whitespace to a single space for stability
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokens_from_text(text: str) -> list[str]:
    """Extract identifiers and keywords from text.

    - identifiers & keywords only (ignore numbers and punctuation)

    Note: This includes ALL identifiers including API class names, method names,
    and framework terms. Cosine similarity will be high for scenarios using the
    same API framework, even if their content differs significantly.
    """
    return re.findall(r"[A-Za-z_][A-Za-z_0-9]*", text)


def shingles(tokens: list[str], k: int = 3) -> set[str]:
    """Generate k-gram token shingles from a list of tokens."""
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b) or 1
    return inter / union


def cosine_counter(ca: Counter[str], cb: Counter[str]) -> float:
    """Calculate cosine similarity between two Counter objects."""
    if not ca and not cb:
        return 1.0
    keys = set(ca) | set(cb)
    dot = sum(ca[k] * cb[k] for k in keys)
    na = sum(v * v for v in ca.values()) ** 0.5
    nb = sum(v * v for v in cb.values()) ** 0.5
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def difflib_ratio(a: str, b: str) -> float:
    """Calculate edit similarity ratio using difflib."""
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio()


def compare_files(f1: str, f2: str, keep_strings: bool = False, k: int = 3) -> dict[str, float | int]:
    """Compare two files using multiple similarity metrics."""
    t1 = load_and_normalize(f1, keep_strings=keep_strings)
    t2 = load_and_normalize(f2, keep_strings=keep_strings)

    # Metric 1: difflib (good general-purpose edit similarity)
    sm_ratio = difflib_ratio(t1, t2)

    # Metric 2: Jaccard over token shingles (robust to minor edits)
    toks1, toks2 = tokens_from_text(t1), tokens_from_text(t2)
    sh1, sh2 = shingles(toks1, k=k), shingles(toks2, k=k)
    jac = jaccard(sh1, sh2)

    # Metric 3: Cosine over token frequency (bag-of-words style)
    # Note: This will often be high (>0.8) since scenarios share framework vocabulary
    # (API class names, method names, common identifiers). Use with caution for duplicate detection.
    c1, c2 = Counter(toks1), Counter(toks2)
    cos = cosine_counter(c1, c2)

    return {
        "difflib_ratio": sm_ratio,
        "jaccard_shingles": jac,
        "cosine_tokens": cos,
        "len_tokens_1": len(toks1),
        "len_tokens_2": len(toks2),
    }


def main() -> None:
    """Main function to detect near-duplicate scenario classes.

    Note: Cosine similarity (cosine_tokens) will typically be high (>0.8) for scenarios
    using the same API framework, even when their content and objectives differ significantly.
    This is expected behavior since all scenarios share common framework vocabulary
    (class names, method names, API terms).

    The scenario generation agent uses different thresholds for different metrics:
    - difflib_ratio ≥0.8 (structural similarity)
    - jaccard_shingles ≥0.8 (pattern similarity)
    - cosine_tokens ≥0.93 (vocabulary similarity, higher threshold due to framework overlap)

    For detecting true duplicates, consider using difflib_ratio or jaccard_shingles
    with a lower threshold, or use the 'max' metric which triggers on any high score.
    """
    p = argparse.ArgumentParser(
        description="Detect near-duplicate scenario files using multiple similarity metrics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python deduplicate_scenarios.py file1.py file2.py --threshold 0.8 --metric max
  python deduplicate_scenarios.py file1.py file2.py --metric difflib --threshold 0.85

Note: Cosine similarity often exceeds 0.8 for scenarios using the same API framework.
Consider using difflib or jaccard metrics for duplicate detection.
        """,
    )
    p.add_argument("file1")
    p.add_argument("file2")
    p.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Similarity threshold for flagging duplicates (default: 0.85). "
        "Note: cosine similarity often exceeds 0.8 for scenarios using the same API framework. "
        "The agent uses different thresholds: difflib/jaccard ≥0.8, cosine ≥0.93.",
    )
    p.add_argument(
        "--metric",
        choices=["difflib", "jaccard", "cosine", "max"],
        default="max",
        help="Which metric to use for the decision. 'max' = if any metric ≥ threshold.",
    )
    p.add_argument(
        "--keep-strings", action="store_true", help="Keep string literals/docstrings in similarity (off by default)."
    )
    p.add_argument("--k", type=int, default=3, help="Shingle size for Jaccard (default: 3).")
    args = p.parse_args()

    if not os.path.exists(args.file1) or not os.path.exists(args.file2):
        print("File not found.", file=sys.stderr)
        sys.exit(2)

    res = compare_files(args.file1, args.file2, keep_strings=args.keep_strings, k=args.k)
    print("=== Similarity Scores ===")
    print(f"difflib_ratio   : {res['difflib_ratio']:.4f}")
    print(f"jaccard_shingles: {res['jaccard_shingles']:.4f} (k={args.k})")
    print(f"cosine_tokens   : {res['cosine_tokens']:.4f}")
    print(f"len(tokens)     : {res['len_tokens_1']} vs {res['len_tokens_2']}")

    # decision
    if args.metric == "difflib":
        score = res["difflib_ratio"]
    elif args.metric == "jaccard":
        score = res["jaccard_shingles"]
    elif args.metric == "cosine":
        score = res["cosine_tokens"]
    else:  # max
        score = max(res["difflib_ratio"], res["jaccard_shingles"], res["cosine_tokens"])

    is_dup = score >= args.threshold
    print("\nDecision:")
    print(f"metric={args.metric} score={score:.4f} threshold={args.threshold:.2f}")
    print("=> NEAR-DUPLICATE ✅" if is_dup else "=> Different enough ❌")
    # sys.exit(0 if is_dup else 1)


if __name__ == "__main__":
    main()
