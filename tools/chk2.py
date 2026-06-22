#!/usr/bin/env python3
import json, subprocess, tempfile, os, sys
sys.path.insert(0, os.getcwd())
from pathlib import Path
from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.normalizer import normalize
from tests.simulation.tb_generator import extra_inputs_from_checker, generate_testbench, _parse_output

ast = json.loads(open('tests/fixtures/v13_or_seq.json').read())
node, clock, text, label = import_assertion(ast)
node = normalize(node)
checker = compose(node, clock, label, text)
mods = emit_all(checker)
ins = extra_inputs_from_checker(checker)

stim = [{'start': True, 'a': True, 'b': True}]
stim += [{'start': False, 'a': False, 'b': False}] * 12

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    tb = generate_testbench(checker.module_name, checker.params['clock_signal'], ins, stim)
    dut_path = tmp / "dut.sv"
    dut_path.write_text("\n\n".join(mods.values()))
    tb_path = tmp / "tb.sv"
    tb_path.write_text(tb)
    
    r = subprocess.run(['iverilog', '-g2012', '-o', str(tmp/'sim.vvp'), str(tb_path), str(dut_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("COMPILE:", r.stderr[:500])
        sys.exit(1)
    
    r = subprocess.run(['vvp', str(tmp/'sim.vvp')], capture_output=True, text=True, cwd=str(tmp))
    print("RAW STDOUT:")
    for line in r.stdout.splitlines():
        print(f"  [{line}]")
    print("\nRAW STDERR:", r.stderr[:300])
    
    parsed = _parse_output(r.stdout)
    print(f"\nPARSED: {len(parsed)} cycles")
    for i, p in enumerate(parsed):
        print(f"  c{i}: a={int(p['active'])} p={int(p['pass'])} f={int(p['fail'])}")
