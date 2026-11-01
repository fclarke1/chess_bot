# The controller infers moves from occupancy maps

The reed switches report only "occupied" or "empty" for each square. The controller receives an occupancy map, not a move, and finds the legal move that gives that map, because only the controller knows the position. The sensor driver applies the removal delay (150 ms) to each square before it sends a map. The controller applies the settle time (500 ms) with a clock that the caller supplies, so the controller contains no hardware timing code and runs the same way in CPython and MicroPython.

## Considered Options

- The sensor driver converts sensor events to moves. Rejected: the sensor driver then needs chess rules and the position.
- The controller reads raw reed switch values and applies both delays. Rejected: per-square timing is hardware work and needs no chess knowledge.
