"""Assemble a self contained Cloud Run source directory from the single source packages.

    python scripts/stage_build.py logistics-gemini            -> build/logistics-gemini/
    gcloud run deploy logistics-agent --source build/logistics-gemini ...

build/ is generated and gitignored; never edit it. Secrets (.env files) are never copied.
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {
    # template: Procfile, requirements.txt and .python-version copied to the build root
    "logistics-gemini": {"packages": ["logistics_core", "logistics_agent"], "template": "deploy_logistics"},
}
IGNORE = shutil.ignore_patterns(".env", ".env.*", "__pycache__", "*.pyc", ".adk", "*.evalset.json")
TEMPLATE_FILES = ("Procfile", "requirements.txt", ".python-version")

def stage(service: str, out: Path) -> list[str]:
    spec = SERVICES[service]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for pkg in spec["packages"]:
        shutil.copytree(ROOT / pkg, out / pkg, ignore=IGNORE)
    for name in TEMPLATE_FILES:
        shutil.copy2(ROOT / spec["template"] / name, out / name)
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    leaked = [f for f in files if Path(f).name.startswith(".env")]
    if leaked:
        raise SystemExit(f"refusing to stage secrets: {leaked}")
    return files

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("service", choices=sorted(SERVICES))
    ap.add_argument("--out", type=Path, help="default: build/<service>")
    args = ap.parse_args()
    out = args.out or ROOT / "build" / args.service
    if args.out is None and out.resolve().parent != (ROOT / "build").resolve():
        sys.exit("unexpected output path")
    for f in stage(args.service, out):
        print(f)
    print(f"staged {args.service} -> {out}")
