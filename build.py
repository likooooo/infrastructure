#!/usr/bin/env python3
import os

os.system("git submodule foreach  cmake -S . -B build")
os.system("git submodule foreach  cmake --build build")
os.system("git submodule foreach  sudo cmake --install build")