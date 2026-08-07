# OpenTitan corpus provenance and boundary

`prim_flop_2sync.sv` is an unmodified source file from the OpenTitan project:

- repository: <https://github.com/lowRISC/opentitan>
- upstream commit: `aac7794751c9d95275100db6278914f795f9d000`
- upstream path: `hw/ip/prim_generic/rtl/prim_flop_2sync.sv`
- Git blob SHA-1 reported by GitHub: `8f7864ee04e4c89ea4b1ff408afdb98ce4bd0c40`
- license: Apache-2.0, retained in the source header and compatible with this
  repository's root `LICENSE`

The test deliberately vendors only this small RTL slice. `prim_flop_adapter.sv`
is a repository-authored compatibility model for the upstream `prim_flop`
dependency; it is not claimed to reproduce the whole OpenTitan primitive stack.
The property and the injected one-flop mutant are also repository-authored.

The evidence establishes that the open formal workflow can elaborate and prove
a two-cycle relationship over one real external RTL module, and can find the
reviewed latency mutant. It does **not** verify OpenTitan, analog metastability,
CDC safety, physical implementation, the `SIMULATION` random-delay path, or any
industrial sign-off claim.
