#!/usr/bin/env python3
"""Fix all v1.3 templates: wire for inter-module signals, wire for combinational assigns"""
import os, sys

TEMPLATES = {
    "prop_or": """
        # Child-driven wires must be `wire`, not `logic`
        s/logic left_active, left_pass, left_fail;/wire left_active, left_pass, left_fail;/
        s/logic right_active, right_pass, right_fail;/wire right_active, right_pass, right_fail;/
        s/logic left_disabled, right_disabled;/wire left_disabled, right_disabled;/
        # Combinational _body_* must be `wire` assignment (not logic init)
        s/logic _body_active =/wire _body_active =/
        s/logic _body_pass   =/wire _body_pass   =/
        s/logic _body_fail   =/wire _body_fail   =/
    """,
    "prop_and": """
        s/logic left_active, left_pass, left_fail;/wire left_active, left_pass, left_fail;/
        s/logic right_active, right_pass, right_fail;/wire right_active, right_pass, right_fail;/
        s/logic left_disabled, right_disabled;/wire left_disabled, right_disabled;/
        s/logic _body_active =/wire _body_active =/
        s/logic _body_pass   =/wire _body_pass   =/
        s/logic _body_fail   =/wire _body_fail   =/
    """,
    "prop_intersect": """
        s/logic left_active, left_pass, left_fail;/wire left_active, left_pass, left_fail;/
        s/logic right_active, right_pass, right_fail;/wire right_active, right_pass, right_fail;/
        s/logic left_disabled, right_disabled;/wire left_disabled, right_disabled;/
        s/logic _body_active =/wire _body_active =/
        s/logic _body_pass   =/wire _body_pass   =/
        s/logic _body_fail   =/wire _body_fail   =/
    """,
    "prop_within": """
        s/logic inner_active, inner_pass, inner_fail;/wire inner_active, inner_pass, inner_fail;/
        s/logic outer_active, outer_pass, outer_fail;/wire outer_active, outer_pass, outer_fail;/
        s/logic inner_disabled, outer_disabled;/wire inner_disabled, outer_disabled;/
        s/logic _body_active =/wire _body_active =/
        s/logic _body_pass   =/wire _body_pass   =/
        s/logic _body_fail   =/wire _body_fail   =/
    """,
    "prop_not": """
        s/logic body_active, body_pass, body_fail, body_disabled;/wire body_active, body_pass, body_fail, body_disabled;/
        s/logic _body_active =/wire _body_active =/
        s/logic _body_pass   =/wire _body_pass   =/
        s/logic _body_fail   =/wire _body_fail   =/
    """,
    "prop_if_else": """
        s/logic true_active, true_pass, true_fail, true_disabled;/wire true_active, true_pass, true_fail, true_disabled;/
        s/logic false_active, false_pass, false_fail, false_disabled;/wire false_active, false_pass, false_fail, false_disabled;/
        s/logic _body_active  =/wire _body_active  =/
        s/logic _body_pass    =/wire _body_pass    =/
        s/logic _body_fail    =/wire _body_fail    =/
    """,
    "prop_throughout": """
        s/logic cond_active, cond_pass, cond_fail;/wire cond_active, cond_pass, cond_fail;/
        s/logic body_active, body_pass, body_fail;/wire body_active, body_pass, body_fail;/
        s/logic cond_disabled, body_disabled;/wire cond_disabled, body_disabled;/
        s/logic _cond_start;/wire _cond_start;/
        s/logic _cond_ok;/wire _cond_ok;/
        s/logic _body_active =/wire _body_active =/
        s/logic _body_pass   =/wire _body_pass   =/
        s/logic _body_fail   =/wire _body_fail   =/
    """,
}

for tpl_name, rules in TEMPLATES.items():
    path = f"templates/{tpl_name}.sv.j2"
    content = open(path).read()
    for rule in rules.strip().split("\n"):
        rule = rule.strip()
        if not rule:
            continue
        # Format: s/old/new/
        if rule.startswith("s/") and rule.count("/") >= 3:
            parts = rule.split("/")
            old = parts[1]
            new = parts[2]
            if old in content:
                content = content.replace(old, new)
                print(f"  {tpl_name}: {old[:50]}... -> {new[:50]}...")
            else:
                print(f"  {tpl_name}: NOT FOUND: {old[:60]}")
    open(path, "w").write(content)
    print(f"Fixed: {tpl_name}")

print("\nAll 7 templates fixed.")
