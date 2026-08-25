from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
from pathlib import Path


def digest_tree(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.rglob("*")) if path.is_file()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True, help="Command template; {input} and {output} are replaced")
    parser.add_argument("--input", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    work = Path(args.work_dir)
    run_a, run_b = work / "run-a", work / "run-b"
    for path in (run_a, run_b):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
        command = args.command.format(input=str(Path(args.input).resolve()), output=str(path.resolve()))
        subprocess.run(command, shell=True, check=True)
    a, b = digest_tree(run_a), digest_tree(run_b)
    if a != b:
        print("NON-DETERMINISTIC OUTPUT")
        for name in sorted(set(a) | set(b)):
            if a.get(name) != b.get(name):
                print(f"- {name}: {a.get(name)} != {b.get(name)}")
        raise SystemExit(1)
    print(f"DETERMINISTIC: {len(a)} files are byte-identical")


if __name__ == "__main__":
    main()
