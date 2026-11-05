#!/bin/sh
# Precompile the controller and the tests to .mpy files, then run them in
# MicroPython with a 100 KB heap, as the ESP32 would. Run from the
# repository root. Needs `micropython` on the PATH and `uv`.
set -e
out=build/mpy
rm -rf "$out"
mkdir -p "$out/controller" "$out/tests"
for f in controller/*.py tests/__init__.py tests/perft_data.py tests/test_detector.py tests/test_game.py tests/test_controller.py; do
    uv run --with mpy-cross mpy-cross -o "$out/${f%.py}.mpy" "$f"
done
cp tests/micropython_run.py tests/micropython_game.py tests/micropython_board.py "$out/"
cd "$out"
echo "== tests"
micropython -X heapsize=100K micropython_run.py
echo "== board perft"
micropython -X heapsize=100K micropython_board.py | tail -2
echo "== random game"
micropython -X heapsize=100K micropython_game.py
