# Compile-time environment initialization (source before cmake / build.py).
#   source /path/to/infrastructure/scripts/init-build-env.sh
#
# Sets: Clang 20, MKL (MKLROOT, setvars, include/lib paths, mkl.h check), CUDA (optional).
# In GitHub Actions, also persists MKL/CUDA vars to GITHUB_ENV when present.
#
# One-time system packages (requires sudo):
#   sudo apt update
#   sudo apt install -y clang-20 llvm-20-dev
#
# CMake 3.30+ (if system cmake is older):
#   pip install --upgrade 'cmake>=3.30'

_infra_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_init_mkl() {
    if [ -n "${MKLROOT:-}" ] && [ -d "${MKLROOT}" ]; then
        :
    elif [ -d /opt/intel/oneapi/mkl/latest ]; then
        export MKLROOT=/opt/intel/oneapi/mkl/latest
    else
        local _mkl_fallback
        _mkl_fallback=$(ls -d /opt/intel/oneapi/mkl/20* 2>/dev/null | head -1)
        if [ -n "$_mkl_fallback" ] && [ -d "$_mkl_fallback" ]; then
            export MKLROOT="$_mkl_fallback"
        fi
    fi

    if [ -z "${MKLROOT:-}" ] || [ ! -d "${MKLROOT}" ]; then
        echo "init-build-env: MKLROOT not found. Install intel-oneapi-mkl-devel." >&2
        return 1 2>/dev/null || exit 1
    fi

    if [ -f /opt/intel/oneapi/setvars.sh ]; then
        # shellcheck source=/dev/null
        source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true
    fi

    # Re-apply after setvars (setvars may alter or clear MKLROOT).
    if [ ! -d "${MKLROOT}" ]; then
        if [ -d /opt/intel/oneapi/mkl/latest ]; then
            export MKLROOT=/opt/intel/oneapi/mkl/latest
        else
            local _mkl_fb
            _mkl_fb=$(ls -d /opt/intel/oneapi/mkl/20* 2>/dev/null | head -1)
            [ -n "$_mkl_fb" ] && export MKLROOT="$_mkl_fb"
        fi
    fi

    export MKL_LIB_DIR="${MKLROOT}/lib/intel64"
    export CPLUS_INCLUDE_PATH="${MKLROOT}/include${CPLUS_INCLUDE_PATH:+:${CPLUS_INCLUDE_PATH}}"
    export C_INCLUDE_PATH="${MKLROOT}/include${C_INCLUDE_PATH:+:${C_INCLUDE_PATH}}"
    export LD_LIBRARY_PATH="${MKL_LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

    if [ ! -f "${MKLROOT}/include/mkl.h" ]; then
        echo "init-build-env: mkl.h not found at ${MKLROOT}/include/mkl.h" >&2
        return 1 2>/dev/null || exit 1
    fi

    echo "init-build-env: MKLROOT=${MKLROOT} MKL_LIB_DIR=${MKL_LIB_DIR} mkl.h=${MKLROOT}/include/mkl.h" >&2
}

_init_cuda() {
    local _cuda=""
    if [ -n "${CUDA_PATH:-}" ] && [ -d "${CUDA_PATH}" ]; then
        _cuda="${CUDA_PATH}"
    elif [ -n "${CUDA_HOME:-}" ] && [ -d "${CUDA_HOME}" ]; then
        _cuda="${CUDA_HOME}"
    elif [ -d /usr/local/cuda-12.6 ]; then
        _cuda=/usr/local/cuda-12.6
    elif [ -d /usr/local/cuda ]; then
        _cuda=/usr/local/cuda
    fi

    if [ -z "$_cuda" ]; then
        echo "init-build-env: CUDA not found (optional); cuda submodule may be skipped locally." >&2
        return 0
    fi

    export CUDA_HOME="$_cuda"
    export CUDA_PATH="$_cuda"
    export PATH="${CUDA_PATH}/bin:${PATH}"
    export LD_LIBRARY_PATH="${CUDA_PATH}/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

    if command -v nvcc >/dev/null 2>&1; then
        echo "init-build-env: CUDA_PATH=${CUDA_PATH} nvcc=$(command -v nvcc)" >&2
        nvcc --version 2>&1 | head -1 >&2 || true
    else
        echo "init-build-env: CUDA_PATH=${CUDA_PATH} (nvcc not in PATH)" >&2
    fi
}

_persist_ci_env() {
    [ -n "${GITHUB_ENV:-}" ] || return 0

    {
        echo "MKLROOT=${MKLROOT}"
        [ -n "${MKL_LIB_DIR:-}" ] && echo "MKL_LIB_DIR=${MKL_LIB_DIR}"
        [ -n "${CUDA_HOME:-}" ] && echo "CUDA_HOME=${CUDA_HOME}"
        [ -n "${CUDA_PATH:-}" ] && echo "CUDA_PATH=${CUDA_PATH}"
        echo "LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-}"
    } >> "$GITHUB_ENV"

    if [ -n "${GITHUB_PATH:-}" ] && [ -n "${CUDA_PATH:-}" ] && [ -d "${CUDA_PATH}/bin" ]; then
        echo "${CUDA_PATH}/bin" >> "$GITHUB_PATH"
    fi
}

export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v clang++-20 >/dev/null 2>&1; then
    echo "init-build-env: clang++-20 not found. Install: sudo apt install -y clang-20" >&2
    return 1 2>/dev/null || exit 1
fi

export CC=clang-20
export CXX=clang++-20
export CMAKE_C_COMPILER="${CC}"
export CMAKE_CXX_COMPILER="${CXX}"

_init_mkl
_init_cuda
_persist_ci_env

echo "init-build-env: CC=${CC} CXX=${CXX} MKLROOT=${MKLROOT:-unset} CUDA_PATH=${CUDA_PATH:-unset} cmake=$(command -v cmake 2>/dev/null || echo missing)" >&2
