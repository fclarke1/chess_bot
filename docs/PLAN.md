# Plan

Each step follows the loop in [CODE_LOOP.md](./CODE_LOOP.md). Each step ends with tests that pass in CPython and in MicroPython with a 100 KB heap. The design is in [ARCHITECTURE.md](./ARCHITECTURE.md).

| Step | Branch | Deliverable | Test | Status |
|---|---|---|---|---|
| 0 | `feat/board-move-generator` | `controller/board.py`: position, legal moves, FEN, UCI and SAN text | Perft for six standard positions; 49 tests | Done |
| 1 | `feat/detector` | `occupancy.py` (8-byte map, diff, map from a position) and `detector.py` (candidates from the map sequence, capture rule, promotion set, `UNCLEAR`, `NO MATCH`) | Scenario tests: normal move, capture, en passant, castling king first, promotion, accidental lift, slide across a square, two captures that fit, put back and redo | Done |
| 2 | `feat/game-rules` | `game.py` (move list, position keys, undo) and `rules.py` (checkmate, stalemate, insufficient material, threefold repetition, 50-move rule) | Rule tests; undo tests through captures and promotions | Done |
| 3 | `feat/controller` | `controller.py` state machine (9 states) and `protocol.py` (request build, reply check, request IDs) | Full games with a fake engine; every transition in ARCHITECTURE.md; undo during `ENGINE_WAIT`; resume after power loss | |
| 4 | same | MicroPython runner for all controller tests | Runs under `-X heapsize=100K`; report free heap after an 80-move game | |
| 5 | `feat/engine-server` | `server/Dockerfile` for Rodent IV on `linux/arm64`. Build and run on the Pi 4 first | `uci` and `go movetime 1000` answer in the container | |
| 6 | same | `server/app.py` and `server/uci.py`: `/move`, `/personalities`, `/health`, `PersonalityFile` order, stop on a new request, legality check | Tests with a fake UCI process; one test with the real container | |
| 7 | `feat/desktop-ui` | `desktop/app.py` and `static/index.html`: drag a piece, buttons, display text, highlight, piece types, replay of an event log | A full game against `pibot:8030` from this computer | |
| 8 | `feat/esp32-main` | `esp32/main.py`: asyncio main loop, HTTP client, stub drivers, flash save, event log | Runs on the ESP32 with `mpremote`; one game with maps from the desktop UI over serial | |
| 9 | — | Run the controller tests on the ESP32 with `mpremote` | Finds 31-bit integer and real-heap faults that Linux MicroPython cannot find | |

Steps 1 to 4 need no hardware and no network. Step 5 needs the Pi. Step 7 needs step 6. Steps 8 and 9 need the ESP32.

## Facts for later steps

- Step 3: `Game` has no move list of its own; `board.history` (5 ints per ply) and `board.ply` hold the game. A resume replays the saved UCI moves with `push()`.
- Step 3: `rules.RESIGNATION` is the end code the controller sets on a long press; `game_end()` never returns it.
- MicroPython heap: long-lived objects allocated one per ply (tuples, keys) fragment the heap and a list growth then fails at about ply 127. Keep per-ply state in flat arrays. Call `gc.collect()` after each commit in the main loop.
- Step 3: the controller commits the engine move only when it is the single candidate. Two candidates give `UNCLEAR: REDO`.
- Step 3: the controller keeps its own last occupancy map for the 3 s `NO MATCH` timer; the detector does not store it.
- Step 3: `occupancy.diff` has no caller yet. It is for the `wrong` highlight in SETTINGS, ENGINE_WAIT, UNDO_RESET, and RESUME.
- Steps 7 and 8: `occupancy.from_text` and `to_text` give the event log format (16 hex characters).
- `tests/micropython_run.py` runs pytest-free test modules in MicroPython. Add each new module to its `MODULES` tuple.

- The display has one line of 16 characters. Every display text in ARCHITECTURE.md fits this size.
- Snap MicroPython cannot read `/tmp`. Compiled `.mpy` files go to `build/mpy`.
- `board.py` uses 19.0 KB of heap from source and 14.1 KB from a `.mpy` file.
- MicroPython on Linux has 64-bit small integers. Only step 9 can find 31-bit integer faults.
