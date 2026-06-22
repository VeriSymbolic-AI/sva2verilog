#!/usr/bin/env python3
"""Fix: only change combinational _body_* lines from wire_type to wire"""
import os

TEMPLATES = ["prop_or", "prop_and", "prop_intersect", "prop_within", "prop_not", "prop_if_else", "prop_throughout"]

for tpl in TEMPLATES:
    path = f"templates/{tpl}.sv.j2"
    content = open(path).read()
    # Fix: {{ wire_type(verilog_mode) }} _body_* = expr
    # → wire _body_* = expr (always wire for combinational assignments)
    fixed = False
    for signal in ["_body_active", "_body_pass", "_body_fail"]:
        old = "{{ wire_type(verilog_mode) }} " + signal + " "
        if old in content:
            content = content.replace(old, "wire " + signal + " ")
            fixed = True
    if fixed:
        open(path, "w").write(content)
        print(f"Fixed: {tpl}")
    else:
        print(f"No changes: {tpl}")

# Special: throughot has _cond_start and _cond_ok
path = "templates/prop_throughout.sv.j2"
content = open(path).read()
for sig in ["_cond_start", "_cond_ok"]:
    old = "{{ wire_type(verilog_mode) }} " + sig + ";"
    if old in content:
        content = content.replace(old, "wire " + sig + ";")
        print(f"Fixed throughout: {sig}")

# Also fix: cond_active/pass/fail/body_active/pass/fail in throughot should be wire
for sig in ["cond_active, cond_pass, cond_fail", "body_active, body_pass, body_fail",
            "cond_disabled, body_disabled"]:
    old = "{{ wire_type(verilog_mode) }} " + sig + ";"
    if old in content:
        content = content.replace(old, "wire " + sig + ";")
        print(f"Fixed throughout: {sig}")
open(path, "w").write(content)

print("\nDone.")
