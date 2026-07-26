#!/usr/bin/env bash

set -euo pipefail

slang_version="${SLANG_VERSION:-v11.0}"
slang_tmp="$(mktemp -d "${RUNNER_TEMP:-/tmp}/sva2rtl-slang.XXXXXX")"

case "$(uname -s)" in
  Linux)
    slang_archive="slang-linux-x86_64.tar.gz"
    slang_sha256="951a170e10e25e54c91565030acfdfc11c3226714ebf225a18ad4166a898d8a4"
    ;;
  Darwin)
    slang_archive="slang-macos-arm64.tar.gz"
    slang_sha256="6d2f86ffedfefe663c6f55fd77348806faafccd69e71f7359986b0c9604f9187"
    ;;
  *)
    echo "unsupported CI host for slang: $(uname -s)" >&2
    exit 2
    ;;
esac

archive_path="${slang_tmp}/${slang_archive}"
curl --fail --location --silent --show-error \
  "https://github.com/MikePopoloski/slang/releases/download/${slang_version}/${slang_archive}" \
  --output "${archive_path}"
printf '%s  %s\n' "${slang_sha256}" "${archive_path}" | shasum -a 256 -c -
tar xzf "${archive_path}" -C "${slang_tmp}"
sudo mv "${slang_tmp}/slang" /usr/local/bin/slang
slang --version
