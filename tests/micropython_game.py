# Play one random game through the controller in MicroPython and report
# the heap. The fake engine picks random legal moves. Run with
# tests/micropython_build.sh, which precompiles the code first.

import gc
import random
import sys

sys.path.insert(0, ".")

gc.collect()
base = gc.mem_alloc()

from controller import occupancy  # noqa: E402
from controller.board import move_from, move_to  # noqa: E402
from controller.controller import ENGINE_WAIT, GAME_END, Controller  # noqa: E402
from controller.detector import capture_square  # noqa: E402

gc.collect()
print("heap for the controller package:", gc.mem_alloc() - base, "bytes")

random.seed(7)
ctrl = Controller()
ctrl.load_settings({"side": "white"})
now = 1000
ctrl.on_occupancy(occupancy.START_MAP, now)
ctrl.on_button("confirm", now)
occ_map = bytearray(occupancy.START_MAP)
peak = 0


def flip(sq):
    global now
    occ_map[sq >> 3] ^= 1 << (sq & 7)
    now += 100
    ctrl.on_occupancy(bytes(occ_map), now)


while ctrl.state != GAME_END and ctrl.game.board.ply < 200:
    board = ctrl.game.board
    move = random.choice(board.legal_moves())
    if ctrl.state == ENGINE_WAIT:
        ctrl.on_engine_reply(ctrl.request_id, board.uci(move))
    cap = capture_square(board, move)
    if cap >= 0:
        flip(cap)
    flip(move_from(move))
    flip(move_to(move))
    now += 600
    ctrl.on_tick(now)
    if ctrl.state == "promotion":
        ctrl.on_button("promote_q", now)
    used = gc.mem_alloc() - base
    if used > peak:
        peak = used
    gc.collect()

gc.collect()
print("plies:", ctrl.game.board.ply, "state:", ctrl.state, "display:", ctrl.on_tick(now).display)
print("heap used at the end:", gc.mem_alloc() - base, "bytes; peak during play:", peak, "bytes")
print("free heap:", gc.mem_free(), "bytes")
