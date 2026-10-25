import subprocess
import sys
from pathlib import Path


command = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name",
    "ImageArchive",
    "--collect-all",
    "webview",
]

if sys.platform == "darwin":
    command.extend(["--osx-bundle-identifier", "com.imagearchive.desktop"])

project_dir = Path(__file__).resolve().parent
command.append(str(project_dir / "agent.py"))
subprocess.run(command, check=True, cwd=project_dir)
