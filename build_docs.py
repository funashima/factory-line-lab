#!/usr/bin/env python3
"""Build both LuaLaTeX guides without modifying their source directories.

Requires lualatex on PATH and the TeX packages/fonts described in README.md.
Python's standard library is sufficient. Run: python build_docs.py --out build/docs
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
DOCUMENTS = (
    ROOT / "docs/easy-guide.tex",
    ROOT / "research_data_pack/data_sources_guide.tex",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/docs",
                        help="New or empty output directory (default: build/docs)")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error("Use a new or empty output directory")
    engine = shutil.which("lualatex")
    if engine is None:
        parser.error("lualatex was not found on PATH; install the TeX environment in README.md")
    for source in DOCUMENTS:
        for required in (source, source.parent / "myfont-setting.sty"):
            if not required.is_file():
                parser.error(f"Required document file is missing: {required}")
    out.mkdir(parents=True, exist_ok=True)
    for source in DOCUMENTS:
        print(f"Building {source.name} (2 passes)", flush=True)
        with tempfile.TemporaryDirectory(prefix="factory-line-docs-") as temporary:
            work = Path(temporary)
            shutil.copyfile(source, work / source.name)
            shutil.copyfile(source.parent / "myfont-setting.sty", work / "myfont-setting.sty")
            for pass_number in (1, 2):
                result = subprocess.run(
                    [engine, "-interaction=nonstopmode", "-halt-on-error",
                     "-file-line-error", "-no-shell-escape", source.name],
                    cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                )
                if result.returncode:
                    log_path = out / f"{source.stem}.failed.log"
                    log_path.write_bytes(result.stdout)
                    parser.exit(1, f"LuaLaTeX failed on pass {pass_number}: {log_path}\n")
            for suffix in (".pdf", ".log"):
                shutil.copyfile(work / f"{source.stem}{suffix}", out / f"{source.stem}{suffix}")
        print(f"Saved {out / (source.stem + '.pdf')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
