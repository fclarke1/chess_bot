# Run the pytest-free test modules in MicroPython.
# From the repository root:
#   micropython -X heapsize=100K tests/micropython_run.py
# The script also runs in CPython: python3 tests/micropython_run.py

import gc
import sys

sys.path.insert(0, ".")

MODULES = ("tests.test_detector",)

failures = 0
count = 0
for name in MODULES:
    module = __import__(name)
    for part in name.split(".")[1:]:
        module = getattr(module, part)
    for attr in dir(module):
        if not attr.startswith("test_"):
            continue
        count += 1
        try:
            getattr(module, attr)()
        except Exception as exc:
            failures += 1
            print("FAIL", name, attr, repr(exc))
        gc.collect()

if hasattr(gc, "mem_free"):
    print("free heap at end:", gc.mem_free(), "bytes")
print("tests:", count, "failures:", failures)
sys.exit(1 if failures else 0)
