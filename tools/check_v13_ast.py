#!/usr/bin/env python3
"""Quick script to inspect slang v11 AST for v1.3 operator fixtures."""
import json, sys

def find_expr(obj, path=''):
    if isinstance(obj, dict):
        kind = obj.get('kind', '')
        op = obj.get('op', '')
        info = f'{kind}[{op}]' if op else kind
        for k, v in list(obj.items()):
            if k == 'kind' and v in ('Binary', 'Unary', 'BinaryPropertyExpr',
                    'IntersectPropertyExpr', 'ThroughoutPropertyExpr',
                    'WithinPropertyExpr', 'Conditional', 'IfElsePropertyExpr',
                    'UnaryPropertyExpr', 'SequenceConcat', 'Simple',
                    'PropertySpec', 'Clocking'):
                print(f'{path}: {info}')
                if 'op' in obj: print(f'  op={obj["op"]}')
                if 'left' in obj: print(f'  left.kind={obj["left"].get("kind","?")}')
                if 'right' in obj: print(f'  right.kind={obj["right"].get("kind","?")}')
                if 'expr' in obj: print(f'  expr.kind={obj["expr"].get("kind","?")}')
            if k not in ('sourceRange', 'source_file', 'source_file_start', 'token', 'symbol'):
                find_expr(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_expr(v, f'{path}[{i}]')

for name in ['or_seq', 'and_seq', 'intersect_seq', 'prop_not', 'throughout_seq', 'if_else_prop']:
    print(f'\n=== {name} ===')
    fix = json.loads(open(f'tests/fixtures/v13_{name}.json').read())
    find_expr(fix)
