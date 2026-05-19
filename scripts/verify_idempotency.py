from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fixlog.normalizer.python import normalize_python_error


DEFAULT_FIXTURE_ROOT = Path("tests/normalizer/fixtures/python")


@dataclass(frozen=True)
class FixtureResult:
    path: Path
    canonical_ok: bool
    hash_ok: bool
    exception_type_ok: bool
    exception_message_ok: bool
    first_error_kind: str
    second_error_kind: str
    first_canonical: str
    second_canonical: str
    raw: str

    @property
    def passed(self) -> bool:
        return (
            self.canonical_ok
            and self.hash_ok
            and self.exception_type_ok
            and self.exception_message_ok
        )


def _fixture_paths(root: Path, only: list[str]) -> list[Path]:
    paths = sorted(root.rglob("*.txt"))
    if not only:
        return paths
    selected: list[Path] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if any(item == path.stem or item == relative for item in only):
            selected.append(path)
    return selected


def _verify_fixture(path: Path) -> FixtureResult:
    raw = path.read_text()
    first = normalize_python_error(raw)
    second = normalize_python_error(first.canonical_string)
    return FixtureResult(
        path=path,
        canonical_ok=first.canonical_string == second.canonical_string,
        hash_ok=first.hash == second.hash,
        exception_type_ok=first.exception_type == second.exception_type,
        exception_message_ok=first.exception_message == second.exception_message,
        first_error_kind=first.error_kind.value,
        second_error_kind=second.error_kind.value,
        first_canonical=first.canonical_string,
        second_canonical=second.canonical_string,
        raw=raw,
    )


def _display_canonical(value: str) -> str:
    return value.replace("\x1f", "\\x1f")


def _print_verbose(result: FixtureResult, root: Path) -> None:
    print(f"\n--- {result.path.relative_to(root).as_posix()} ---")
    print("raw:")
    print(result.raw.rstrip())
    print("result1.canonical_string:")
    print(_display_canonical(result.first_canonical))
    print("result2.canonical_string:")
    print(_display_canonical(result.second_canonical))


def main(argv: Sequence[str] | None = None) -> int:
    """Verify normalizer idempotency across the fixture corpus.

    Walks tests/normalizer/fixtures/python by default. For each raw fixture,
    normalizes raw text, normalizes the resulting canonical_string, and checks
    canonical_string, hash, exception_type, and exception_message round-trip
    equality. Prints a summary of fixtures whose error_kind changes on
    canonical round-trip; those transitions are informational, not failures.

    Supports --verbose to print raw text, first canonical_string, and second
    canonical_string. Supports repeated --only <relative-fixture-path-or-stem>
    to limit verbose/manual spot checks to selected fixtures. Returns 0 on
    success and nonzero on any idempotency failure.
    """
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=DEFAULT_FIXTURE_ROOT,
        help="Fixture root to walk. Defaults to tests/normalizer/fixtures/python.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit to a fixture stem or path relative to the fixture root. Can repeat.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print raw and both canonical strings for selected fixtures.",
    )
    args = parser.parse_args(argv)

    root = args.fixtures_root
    results = [_verify_fixture(path) for path in _fixture_paths(root, args.only)]
    failures = [result for result in results if not result.passed]
    kind_changes = [
        result
        for result in results
        if result.first_error_kind != result.second_error_kind
    ]

    if args.verbose:
        for result in results:
            _print_verbose(result, root)

    print(f"fixtures verified: {len(results)}")
    print(f"error_kind changes on round-trip: {len(kind_changes)}")
    for result in kind_changes:
        print(
            "- "
            f"{result.path.relative_to(root).as_posix()}: "
            f"{result.first_error_kind} -> {result.second_error_kind}"
        )

    if failures:
        print(f"failures: {len(failures)}")
        for result in failures:
            print(f"- {result.path.relative_to(root).as_posix()}")
            print(f"  canonical_ok={result.canonical_ok}")
            print(f"  hash_ok={result.hash_ok}")
            print(f"  exception_type_ok={result.exception_type_ok}")
            print(f"  exception_message_ok={result.exception_message_ok}")
        return 1

    print("idempotency verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
