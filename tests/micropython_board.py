# Run the board checks in MicroPython, which cannot run pytest.
# From the repository root:
#   micropython -X heapsize=100K tests/micropython_board.py
# The script also runs in CPython: python3 tests/micropython_board.py

import gc
import sys
import time

sys.path.insert(0, ".")

gc.collect()
heap_before = gc.mem_alloc() if hasattr(gc, "mem_alloc") else None

from controller.board import Board  # noqa: E402
from tests.perft_data import PERFT_CASES, perft  # noqa: E402

gc.collect()
if heap_before is not None:
    print("heap used by board.py and its tables:", gc.mem_alloc() - heap_before, "bytes")

# Keep the run short on a slow interpreter: skip cases above 50000 nodes.
MAX_NODES = 50000

failures = 0
for fen, depth, expected in PERFT_CASES:
    if expected > MAX_NODES:
        continue
    start = time.time()
    board = Board(fen)
    result = perft(board, depth)
    status = "ok" if result == expected and board.fen() == fen else "FAIL"
    if status == "FAIL":
        failures += 1
    print(status, depth, expected, result, "%.2f s" % (time.time() - start), fen)

if hasattr(gc, "mem_free"):
    gc.collect()
    print("free heap at end:", gc.mem_free(), "bytes")
print("failures:", failures)
sys.exit(1 if failures else 0)
