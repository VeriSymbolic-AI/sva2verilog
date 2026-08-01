#!/usr/bin/env bash

set -euo pipefail

verilator_version="${VERILATOR_VERSION:-v5.028}"
verilator_release="${verilator_version#v}"
verilator_sha256="02d4b6f34754b46a97cfd70f5fcbc9b730bd1f0a24c3fc37223397778fcb142c"
verilator_tmp="$(mktemp -d "${RUNNER_TEMP:-/tmp}/sva2rtl-verilator.XXXXXX")"

case "$(uname -s)" in
  Linux)
    sudo apt-get update
    # Ubuntu 24.04 splits the C++ Flex header out of the `flex` package.
    # Verilator's generated lexer includes <FlexLexer.h>, so the recommended
    # libfl-dev package is a required source-build dependency.
    sudo apt-get install -y autoconf bison build-essential flex help2man libfl-dev
    test -r /usr/include/FlexLexer.h || {
      echo "libfl-dev did not provide /usr/include/FlexLexer.h" >&2
      exit 1
    }
    verilator_jobs="$(nproc)"
    verilator_prefix="/usr/local"
    verilator_install=(sudo make install)
    ;;
  Darwin)
    export HOMEBREW_NO_AUTO_UPDATE=1
    brew install autoconf bison flex help2man
    flex_prefix="$(brew --prefix flex)"
    bison_prefix="$(brew --prefix bison)"
    export PATH="${flex_prefix}/bin:${bison_prefix}/bin:${PATH}"
    export CPPFLAGS="-I${flex_prefix}/include -I${bison_prefix}/include ${CPPFLAGS:-}"
    export LDFLAGS="-L${flex_prefix}/lib -L${bison_prefix}/lib ${LDFLAGS:-}"
    verilator_jobs="$(sysctl -n hw.logicalcpu)"
    verilator_prefix="$(brew --prefix)"
    verilator_install=(make install)
    ;;
  *)
    echo "unsupported CI host for Verilator build: $(uname -s)" >&2
    exit 2
    ;;
esac

curl --fail --location --silent --show-error \
  "https://github.com/verilator/verilator/archive/refs/tags/${verilator_version}.tar.gz" \
  --output "${verilator_tmp}/verilator.tar.gz"
printf '%s  %s\n' "${verilator_sha256}" "${verilator_tmp}/verilator.tar.gz" \
  | shasum -a 256 -c -
tar xzf "${verilator_tmp}/verilator.tar.gz" -C "${verilator_tmp}"

cd "${verilator_tmp}/verilator-${verilator_release}"
autoconf
./configure --prefix="${verilator_prefix}"
make -j"${verilator_jobs}"
"${verilator_install[@]}"

installed_version="$(verilator --version)"
case "${installed_version}" in
  *"${verilator_release}"*) printf '%s\n' "${installed_version}" ;;
  *)
    echo "expected Verilator ${verilator_release}, got: ${installed_version}" >&2
    exit 1
    ;;
esac
