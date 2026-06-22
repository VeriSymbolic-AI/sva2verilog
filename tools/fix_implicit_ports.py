#!/usr/bin/env python3
"""Replace .* with explicit port connections in v1.3 templates to avoid multiple-driver errors."""
import re

FIXES = {
    "prop_or": {
        "left_prefix": "left",
        "right_prefix": "right",
        "children_count": 2,
    },
    "prop_and": {
        "left_prefix": "left",
        "right_prefix": "right",
        "children_count": 2,
    },
    "prop_intersect": {
        "left_prefix": "left",
        "right_prefix": "right",
        "children_count": 2,
    },
    "prop_within": {
        "left_prefix": "inner",
        "right_prefix": "outer",
        "children_count": 2,
    },
}

EXPLICIT_CHILD = """\
{{ children[{idx}].module_name }} u_{prefix} (
    .{{{{ clock_signal }}}}({{{{ clock_signal }}}}),
    .rst_n(rst_n),
    .start(start),
{%- for port_name, _ in children[{idx}].observed_signals %}
    .{{{{ port_name }}}}({{{{ port_name }}}}),
{%- endfor %}
    .disable_i(disable_i),
    .active({prefix}_active),
    .pass({prefix}_pass),
    .fail({prefix}_fail),
    .attempt_fired(),
    .disabled_o({prefix}_disabled)
);"""

# Fix prop_or
content = open("templates/prop_or.sv.j2").read()
old = "{{ children[0].module_name }} u_left (.*);\n{{ children[1].module_name }} u_right (.*);"
new = EXPLICIT_CHILD.format(idx=0, prefix="left") + "\n" + EXPLICIT_CHILD.format(idx=1, prefix="right")
content = content.replace(old, new)
open("templates/prop_or.sv.j2", "w").write(content)
print("Fixed: prop_or")

# Fix prop_and
content = open("templates/prop_and.sv.j2").read()
old = "{{ children[0].module_name }} u_left (.*);\n{{ children[1].module_name }} u_right (.*);"
new = EXPLICIT_CHILD.format(idx=0, prefix="left") + "\n" + EXPLICIT_CHILD.format(idx=1, prefix="right")
content = content.replace(old, new)
open("templates/prop_and.sv.j2", "w").write(content)
print("Fixed: prop_and")

# Fix prop_intersect
content = open("templates/prop_intersect.sv.j2").read()
old = "{{ children[0].module_name }} u_left (.*);\n{{ children[1].module_name }} u_right (.*);"
new = EXPLICIT_CHILD.format(idx=0, prefix="left") + "\n" + EXPLICIT_CHILD.format(idx=1, prefix="right")
content = content.replace(old, new)
open("templates/prop_intersect.sv.j2", "w").write(content)
print("Fixed: prop_intersect")

# Fix prop_within
content = open("templates/prop_within.sv.j2").read()
old = "{{ children[0].module_name }} u_inner (.*);\n{{ children[1].module_name }} u_outer (.*);"
new = EXPLICIT_CHILD.format(idx=0, prefix="inner") + "\n" + EXPLICIT_CHILD.format(idx=1, prefix="outer")
content = content.replace(old, new)
open("templates/prop_within.sv.j2", "w").write(content)
print("Fixed: prop_within")

# prop_not: single child
content = open("templates/prop_not.sv.j2").read()
old = "{{ children[0].module_name }} u_body (.*);"
not_child = """\
{{ children[0].module_name }} u_body (
    .{{{{ clock_signal }}}}({{{{ clock_signal }}}}),
    .rst_n(rst_n),
    .start(start),
{%- for port_name, _ in children[0].observed_signals %}
    .{{{{ port_name }}}}({{{{ port_name }}}}),
{%- endfor %}
    .disable_i(disable_i),
    .active(body_active),
    .pass(body_pass),
    .fail(body_fail),
    .attempt_fired(),
    .disabled_o(body_disabled)
);"""
content = content.replace(old, not_child)
open("templates/prop_not.sv.j2", "w").write(content)
print("Fixed: prop_not")

# prop_if_else: two children (true branch always, false branch optional)
content = open("templates/prop_if_else.sv.j2").read()
old = "{{ children[0].module_name }} u_true (.*);\n{% if has_else == \"1\" %}\n{{ children[1].module_name }} u_false (.*);"
true_child = """\
{{ children[0].module_name }} u_true (
    .{{{{ clock_signal }}}}({{{{ clock_signal }}}}),
    .rst_n(rst_n),
    .start(start),
{%- for port_name, _ in children[0].observed_signals %}
    .{{{{ port_name }}}}({{{{ port_name }}}}),
{%- endfor %}
    .disable_i(disable_i),
    .active(true_active),
    .pass(true_pass),
    .fail(true_fail),
    .attempt_fired(),
    .disabled_o(true_disabled)
);"""
false_child = """\
{{ children[1].module_name }} u_false (
    .{{{{ clock_signal }}}}({{{{ clock_signal }}}}),
    .rst_n(rst_n),
    .start(start),
{%- for port_name, _ in children[1].observed_signals %}
    .{{{{ port_name }}}}({{{{ port_name }}}}),
{%- endfor %}
    .disable_i(disable_i),
    .active(false_active),
    .pass(false_pass),
    .fail(false_fail),
    .attempt_fired(),
    .disabled_o(false_disabled)
);"""
new = true_child + "\n{% if has_else == \"1\" %}\n" + false_child
content = content.replace(old, new)
open("templates/prop_if_else.sv.j2", "w").write(content)
print("Fixed: prop_if_else")

print("Done")
