#!/usr/bin/env python3
"""Build and install all infrastructure git submodules listed in .gitmodules."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

INFRA_ROOT = os.path.dirname(os.path.abspath(__file__))
INF_INSTALL_DIR = os.path.join(INFRA_ROOT, ".inf_install")
REQUIREMENTS = os.path.join(INFRA_ROOT, "py_visualizer", "requirements.txt")
VENV_DIR = os.path.join(INFRA_ROOT, ".venv")
VENV_ACTIVATE = os.path.join(VENV_DIR, "bin", "activate")
GITMODULES = os.path.join(INFRA_ROOT, ".gitmodules")


def prepend_env_path(var: str, value: str) -> None:
    old = os.environ.get(var, "")
    os.environ[var] = f"{value}:{old}" if old else value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build infrastructure git submodules")
    parser.add_argument(
        "--root",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Install into /usr/local (system-wide). "
            "Uses sudo for cmake --install when /usr/local is not writable."
        ),
    )
    parser.add_argument(
        "--skip-test",
        action="store_true",
        help="Skip ctest for all submodules",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove build/ before configure (full rebuild)",
    )
    return parser.parse_args()


@dataclass(frozen=True)
class InstallMode:
    label: str
    cmake_configure_args: tuple[str, ...]
    sudo_install: bool

    def setup_env(self) -> None:
        if self.label == "user":
            os.makedirs(INF_INSTALL_DIR, exist_ok=True)
            print(f"Install mode: user ({INF_INSTALL_DIR})")
            prepend_env_path("CMAKE_PREFIX_PATH", INF_INSTALL_DIR)
            prepend_env_path("CPLUS_INCLUDE_PATH", os.path.join(INF_INSTALL_DIR, "include"))
            return
        suffix = " via sudo" if self.sudo_install else ""
        print(f"Install mode: root (/usr/local{suffix})")


def resolve_install_mode(use_root: bool) -> InstallMode:
    if not use_root:
        prefix = f'-DCMAKE_INSTALL_PREFIX="{INF_INSTALL_DIR}"'
        path = f'-DCMAKE_PREFIX_PATH="{INF_INSTALL_DIR}"'
        return InstallMode("user", (prefix, path), sudo_install=False)

    usr_local_writable = os.access("/usr/local", os.W_OK)
    return InstallMode("root", (), sudo_install=not usr_local_writable)


def ensure_venv_and_deps() -> None:
    """Create venv if missing and install py_visualizer/requirements.txt."""
    if not os.path.exists(VENV_DIR):
        print(f"Creating venv at {VENV_DIR}")
        subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)
    pip = os.path.join(VENV_DIR, "bin", "pip")
    if not os.path.exists(REQUIREMENTS):
        print(f"Skip pip install: {REQUIREMENTS} not found")
        return
    print(f"Installing dependencies from {REQUIREMENTS}")
    subprocess.run([pip, "install", "-r", REQUIREMENTS], check=True)


def require_build_env() -> None:
    cxx = os.environ.get("CMAKE_CXX_COMPILER", "")
    if cxx and "clang" in os.path.basename(cxx):
        return
    print(
        "Error: source scripts/init-build-env.sh before build.py (Clang 20 + MKLROOT)",
        file=sys.stderr,
    )
    sys.exit(1)


def load_submodule_paths() -> list[str]:
    with open(GITMODULES, encoding="utf-8") as file:
        lines = file.readlines()
    return [line.strip().split(" = ", 1)[1] for line in lines if line.strip().startswith("path = ")]


def run_shell(cmd: str, cwd: str, label: str) -> None:
    try:
        subprocess.run(cmd, shell=True, cwd=cwd, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Command failed in {label} (exit {exc.returncode}): {cmd}", file=sys.stderr)
        raise


def clean_build_dir(full_path: str, allow_sudo: bool) -> None:
    build_dir = os.path.join(full_path, "build")
    if not os.path.isdir(build_dir):
        return
    try:
        shutil.rmtree(build_dir)
    except OSError as err:
        if not allow_sudo:
            print(
                f"Error: cannot remove {build_dir}: {err}. "
                "Fix permissions or re-run with --root if the directory is root-owned.",
                file=sys.stderr,
            )
            raise
        run_shell("sudo rm -rf build", full_path, full_path)


def run_ctest_with_venv(build_dir: str, submodule_path: str) -> None:
    """Run ctest in bash with venv activated. Skip cuda tests on CI without GPU."""
    if os.environ.get("CI") and submodule_path == "cuda":
        cmd = "ctest -V -E '.*'"
        print("(CI: skip cuda tests, no GPU)")
    else:
        cmd = f'source "{VENV_ACTIVATE}" && ctest -V'
    try:
        subprocess.run(["bash", "-c", cmd], cwd=build_dir, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Command failed in {build_dir} (exit {exc.returncode}): {cmd}", file=sys.stderr)
        raise


def run_cmake_configure(full_path: str, mode: InstallMode) -> None:
    args = " ".join(mode.cmake_configure_args)
    suffix = f" {args}" if args else ""
    run_shell(f"cmake -S . -B build{suffix}", full_path, full_path)


def run_cmake_install(full_path: str, mode: InstallMode) -> None:
    install = "sudo cmake --install build" if mode.sudo_install else "cmake --install build"
    run_shell(install, full_path, full_path)


def build_submodule(rel_path: str, mode: InstallMode, *, skip_test: bool, clean: bool) -> None:
    full_path = os.path.join(INFRA_ROOT, rel_path)
    print(f"begin {full_path}")

    if clean:
        clean_build_dir(full_path, allow_sudo=mode.sudo_install)
    run_cmake_configure(full_path, mode)
    run_shell("cmake --build build -j", full_path, full_path)
    if not skip_test:
        run_ctest_with_venv(os.path.join(full_path, "build"), rel_path)

    if "fft" in full_path:
        return
    run_cmake_install(full_path, mode)


def main() -> int:
    args = parse_args()
    ensure_venv_and_deps()
    require_build_env()

    mode = resolve_install_mode(args.root)
    mode.setup_env()

    paths = load_submodule_paths()
    for rel_path in paths:
        build_submodule(rel_path, mode, skip_test=args.skip_test, clean=args.clean)

    print(f"build success {paths}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
