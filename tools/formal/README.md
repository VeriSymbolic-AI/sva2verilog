# Pinned open-formal replay image

This image is the portable Linux fallback for hosts where Super Prove is not
available (notably the current macOS OSS CAD Suite). It does not change a proof
contract or upgrade an `UNKNOWN` result: it only supplies the exact open-tool
runtime needed to replay an already generated evidence bundle.

Build from the repository root:

```sh
docker build --platform linux/amd64 \
  --file tools/formal/Dockerfile \
  --tag sva2rtl-formal:2026-07-21 .
```

Replay a bundle, replacing the example path with the evidence directory:

```sh
docker run --rm \
  --volume "$PWD/formal-evidence:/work" \
  sva2rtl-formal:2026-07-21 \
  sby -f formal.sby

docker run --rm \
  --volume "$PWD/formal-evidence:/work" \
  sva2rtl-formal:2026-07-21 \
  sby -f formal_cover.sby
```

The base-image manifest and both OSS CAD Suite archives are SHA-256 pinned.
The evidence manifest separately fingerprints the `sby`, `yosys`, `slang`, and
`suprove` executables. A result is accepted only when its tool identities,
manifest, logs, property, DUT inputs, replay commands, proof result, and cover
result all remain bound and intact.

Limitations:

- Docker itself is not a formal oracle; solver and modeling boundaries remain.
- An image built for `linux/amd64` on Apple Silicon uses emulation and is slower.
- The image replays generated bundles. Generate the bundle with
  `sva2rtl-formal --compile-only`, which intentionally exits 11 (`UNKNOWN`).
- A liveness result needs the `open-live-suprove` backend and complete fairness
  evidence where fairness assumptions are present.
