"""Update the code from GitHub without downloading ZIPs (user, 3 Oct 2026).

Downloads main.zip, checks it is this project, then copies new and changed files over the code folder.
Never touched: statements folders, PDFs (except the fake test ones), databases, .env, .venv and anything of the
user's that is not in the zip (nothing is deleted). Uses the standard library only, so `update.bat` still works
when the rest of the code is broken:  C:\\ftvenv\\Scripts\\python.exe -m fintrack.update
"""
import io
import sys
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

URL = "https://github.com/DF-AI-Lab/financial-tracker/archive/refs/heads/main.zip"
CODE_DIR = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"statements", "real_statements", "output", ".venv", ".git", "__pycache__"}


def download() -> bytes:
    with urllib.request.urlopen(URL, timeout=60) as r:
        return r.read()


def _keep_out(rel: PurePosixPath) -> bool:
    """True for the user's own things that an update must never write."""
    if any(part in SKIP_DIRS for part in rel.parts[:-1]):
        return True
    name = rel.name.lower()
    if name.endswith(".db") or name == ".env" or name == "version.txt":
        return True
    if name.endswith(".pdf") and rel.parts[:2] != ("tests", "data"):
        return True
    return False


def update_code(code_dir: Path = CODE_DIR, fetch=download) -> dict:
    """Returns {"changed": [relative paths written], "version": short commit id or ""}.
    Raises ValueError (and changes nothing) when the download is not this project's zip."""
    code_dir = Path(code_dir)
    data = fetch()
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("The download was not a zip file.")
    files = {}
    for info in z.infolist():
        if info.is_dir():
            continue
        parts = PurePosixPath(info.filename).parts
        if len(parts) < 2 or ".." in parts:
            continue
        files[PurePosixPath(*parts[1:])] = info                   # drop the top folder (financial-tracker-main/)
    if PurePosixPath("web.py") not in files or PurePosixPath("fintrack/home.py") not in files:
        raise ValueError("The download does not look like the Financial Tracker.")

    changed = []
    for rel, info in sorted(files.items()):
        if _keep_out(rel):
            continue
        new = z.read(info)
        target = code_dir.joinpath(*rel.parts)
        if target.exists() and target.read_bytes() == new:
            continue                                               # same as now: not rewritten (start.bat may be running)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(new)
        changed.append(str(rel))

    version = z.comment.decode("ascii", "ignore").strip()[:7]
    if version:
        (code_dir / "version.txt").write_text(version + "\n")
    return {"changed": changed, "version": version}


def main():
    print("Getting the latest version from GitHub...")
    try:
        r = update_code()
    except (OSError, ValueError) as e:
        print(f"Sorry, the update did not work: {e}")
        print("Check the internet, or download the ZIP by hand:", URL)
        return 1
    if r["changed"]:
        print(f"Updated {len(r['changed'])} file(s). Version {r['version']}.")
        print("Close the black Financial Tracker window (if open) and double-click start.bat.")
    else:
        print(f"Already up to date (version {r['version']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
