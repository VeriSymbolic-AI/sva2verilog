#!/usr/bin/env python3
"""Fix attempt_fired_q in v1.3 templates."""
templates = ['prop_intersect', 'prop_within', 'prop_not', 'prop_if_else', 'prop_throughout']

for tpl in templates:
    path = f'templates/{tpl}.sv.j2'
    content = open(path).read()
    # Add declaration before macro
    content = content.replace(
        '\n{{ attempt_fired_logic(',
        '\n\n    // HARDEN-01: attempt_fired_q never cleared by disable_i\n'
        '    {{ signal_type(verilog_mode) }} attempt_fired_q;\n\n'
        '{{ attempt_fired_logic('
    )
    # Add assignment
    content = content.replace(
        '    assign disabled_o = disabled_q;\n',
        '    assign disabled_o = disabled_q;\n'
        '    assign attempt_fired = attempt_fired_q;\n'
    )
    open(path, 'w').write(content)
    print(f'Fixed: {tpl}')
print('Done')
