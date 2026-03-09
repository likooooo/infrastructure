#!/usr/bin/env python3
import os
import subprocess
import sys

# infrastructure 仓库根目录
INFRA_ROOT = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS = os.path.join(INFRA_ROOT, "py_visualizer", "requirements.txt")
VENV_DIR = os.path.join(INFRA_ROOT, ".venv")
VENV_ACTIVATE = os.path.join(VENV_DIR, "bin", "activate")


def ensure_venv_and_deps():
    """创建 venv（若不存在）并安装 simulation_toykits/requirements.txt"""
    if not os.path.exists(VENV_DIR):
        print(f"Creating venv at {VENV_DIR}")
        assert subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)
    pip = os.path.join(VENV_DIR, "bin", "pip")
    if not os.path.exists(REQUIREMENTS):
        print(f"Skip pip install: {REQUIREMENTS} not found")
        return
    print(f"Installing dependencies from {REQUIREMENTS}")
    assert subprocess.run([pip, "install", "-r", REQUIREMENTS], check=True)


def run_ctest_with_venv(build_dir: str, submodule_path: str = "") -> int:
    """在激活 venv 的 shell 中执行 ctest。CI 且无物理 GPU 时跳过 cuda 子模块的测试。"""
    # GitHub Actions 等 CI 无物理显卡，cuda 的 ctest 会报错，用 -E ".*" 排除全部用例
    if os.environ.get("CI") and submodule_path == "cuda":
        cmd = f'cd "{build_dir}" && ctest -V -E ".*"'
        print("(CI: skip cuda tests, no GPU)")
    else:
        cmd = f'cd "{build_dir}" && source "{VENV_ACTIVATE}" && ctest -V'
    return subprocess.run(["bash", "-c", cmd]).returncode


# 安装 simulation_toykits 依赖
ensure_venv_and_deps()

# 读取.gitmodules文件，并提取所有path
with open(os.path.join(INFRA_ROOT, ".gitmodules"), "r") as file:
    lines = file.readlines()

paths = [line.strip().split(" = ")[1] for line in lines if "path = " in line]

for path in paths:
    # 构造子模块的完整路径
    full_path = os.path.join(INFRA_ROOT, path)

    # 执行一系列命令
    print(f"begin {full_path}")
    os.system(f"cd {full_path} && sudo rm -r build")
    assert 0 == os.system(f"cd {full_path} && cmake -S . -B build")
    assert 0 == os.system(f"cd {full_path} && cmake --build build -j")
    assert 0 == run_ctest_with_venv(os.path.join(full_path, "build"), path)
    if "fft" in full_path:
        continue
    assert 0 == os.system(f"cd {full_path} && sudo cmake --install build")

print(f"build success {paths}")