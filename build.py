#!/usr/bin/env python3
import os

# 读取.gitmodules文件，并提取所有path
with open('.gitmodules', 'r') as file:
    lines = file.readlines()

paths = [line.strip().split(' = ')[1] for line in lines if "path = " in line]

for path in paths:
    # 构造子模块的完整路径
    full_path = os.path.join(os.getcwd(), path)
    
    # 执行一系列命令
    print(f"begin {full_path}")
    os.system(f"cd {full_path} &&sudo rm -r build")
    assert(0 == os.system(f"cd {full_path} && cmake -S . -B build"))
    assert(0 == os.system(f"cd {full_path} && cmake --build build -j"))
    # assert(0 == os.system(f"cd {full_path}/build && ctest"))
    assert(0 == os.system(f"cd {full_path} && sudo cmake --install build"))

print(f"build success {paths}")