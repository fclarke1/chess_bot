# Architecture

This document describes the components of the chess board project, the interfaces between them, and the data flow for each type of event. The terms come from [CONTEXT.md](../CONTEXT.md). The decisions come from [docs/adr/](./adr/). The section "Open questions" at the end lists the decisions that the owner has not made yet.

## Scope

In scope for this repository:

- **Controller**: the move generator and the game logic. Pure Python. Runs in CPython and in MicroPython on the ESP32.
- **Engine server**: an HTTP wrapper around Rodent IV, in a Docker image for the Raspberry Pi (`pibot:8030`).
- **Desktop UI**: a debug tool for this computer. It replaces the sensors, the buttons, the display, and the LEDs. It is not part of the final board.

Out of scope:

- The sensor driver (reed switch reads and the removal delay).
- The button driver, the display driver, and the LED driver.
- The real drivers for the ESP32. This repository holds a reference main loop (`esp32/main.py`) with stub drivers, so the controller and the HTTP client run on the device before the real drivers exist.

## Component map

```
                 ESP32 (MicroPython)                              Raspberry Pi "pibot"
 +--------------------------------------------------+       +-----------------------------+
 |  Sensor driver --occupancy map-->+               |       |  Docker container           |
 |  Button driver --button name---->|               |       |                             |
 |  Clock ---------now_ms---------->|  CONTROLLER   |       |  Engine server (HTTP :8030) |
 |                                  |  (pure Python)|       |        |  UCI (stdin/out)   |
 |  Display driver <--display text--|  no I/O       |       |        v                    |
 |  LED driver <------highlight-----|               |       |  Rodent IV + personalities  |
 |  Flash <--------settings---------+---------------+       |            + books          |
 |                                                  |       +-----------------------------+
 |  Main loop (asyncio): HTTP task --POST /move (Wi-Fi)------------>  |                  |
 |             gives engine reply to controller <-------- JSON -------+                  |
 +--------------------------------------------------+

                 This computer (CPython), debug only
 +--------------------------------------------------+
 |  Desktop UI (browser page + stdlib HTTP server)  |
 |  replaces: sensor driver, buttons, display, LEDs |
 |  uses: the same CONTROLLER code                  |
 +--------------------------------------------------+
```

## Repository layout

```
controller/          Pure Python. CPython and MicroPython.
  board.py           Position, move generator, make and unmake move, FEN,
                     UCI move text, SAN move text (for the display).
  occupancy.py       Occupancy map type: 8 bytes, one byte per rank.
  rules.py           Game end checks.
  detector.py        Finds a move from the sequence of occupancy maps.
  game.py            Move list, position history, undo.
  controller.py      State machine. The only public entry point.
  protocol.py        Builds the engine request and checks the engine reply.
server/              CPython only.
  app.py             HTTP server: /move, /personalities, /health.
  uci.py             Rodent IV process wrapper.
  Dockerfile         Builds Rodent IV for ARM64. Copies personalities/ and books/.
desktop/             CPython only. Debug UI.
  app.py             Stdlib HTTP server. Holds one controller object.
  static/index.html  Board page.
tests/
docs/
CONTEXT.md
```

## Controller interface

The controller does no I/O. It does not read the clock, the network, the flash, or the hardware. The caller gives it inputs and acts on its outputs.

### Inputs

| Method | When |
|---|---|
| `on_occupancy(map, now_ms)` | The occupancy map changes. `map` is 8 bytes; byte 0 is rank 1, bit 0 of each byte is file a. |
| `on_button(name, now_ms)` | A button press. Names: `confirm`, `confirm_long`, `undo`, `promote_q`, `promote_r`, `promote_b`, `promote_n`, `side`, `personality`, `strength`, `think_time`. |
| `on_tick(now_ms)` | Every 50 ms. Lets the settle time end when no map changes. |
| `on_engine_reply(request_id, move)` | The engine server answered. `move` is UCI text, for example `b8c6`. |
| `on_engine_error(request_id, text)` | The engine server did not answer, or answered with an error. |
| `on_personalities(names)` | The main loop received the personality list. |
| `load_settings(data)` | At start-up, with the settings from flash, or `None`. |
| `load_game(data)` | At start-up, with the saved game from flash, or `None`. |

`now_ms` must be a counter that does not wrap. On the ESP32, `time.ticks_ms()` wraps after 2^30 ms (12.4 days), so the main loop adds `time.ticks_diff()` values to its own counter.

### Output

Each input method returns one `Output` object:

| Field | Meaning |
|---|---|
| `display` | One line of text, max 16 characters. |
| `highlight` | List of `(square, role)`. Roles: `from`, `to`, `remove`, `restore`, `wrong`. An empty list switches all LEDs off. |
| `engine_request` | A dict for `POST /move`, or `None`. Each request has a new `request_id`, also a retry. |
| `fetch_personalities` | `True` when the main loop must send `GET /personalities`. |
| `save_settings` | A dict to write to flash, or `None`. |
| `save_game` | The settings and the move list to write to flash after each commit, or `None`. An empty dict after a game end deletes the saved game. |

## Controller states

```
 start-up     --saved game exists---------------------------> RESUME
 start-up     --no saved game-------------------------------> SETTINGS
 RESUME       --map = committed map, then confirm-----------> state of the saved game
 RESUME       --confirm_long--------------------------------> SETTINGS (saved game deleted)

 SETTINGS     --confirm, setup check OK----------------------> HUMAN_TURN (human white)
 SETTINGS     --confirm, setup check OK----------------------> ENGINE_WAIT (human black)
 SETTINGS     --confirm, setup check fails-------------------> SETTINGS (SETUP: n WRONG)

 HUMAN_TURN   --one candidate + settle time, or confirm------> commit --> ENGINE_WAIT
 HUMAN_TURN   --promotion candidates only + settle time------> PROMOTION
 HUMAN_TURN   --several non-promotion candidates-------------> HUMAN_TURN (UNCLEAR: REDO)
 PROMOTION    --promote_x--------------------------------------> commit --> ENGINE_WAIT
 PROMOTION    --occupancy map changes-------------------------> HUMAN_TURN

 ENGINE_WAIT  --legal engine reply----------------------------> ENGINE_MOVE (highlight on)
 ENGINE_WAIT  --error or illegal reply-----------------------> ENGINE_WAIT (ENGINE OFFLINE, retry 5 s)
 ENGINE_MOVE  --map = expected map + settle time, or confirm-> commit --> HUMAN_TURN
 ENGINE_MOVE  --map differs + settle time---------------------> ENGINE_MOVE (WRONG, wrong squares lit)

 HUMAN_TURN, PROMOTION, ENGINE_WAIT, ENGINE_MOVE, GAME_END
              --undo, a human move exists---------------------> UNDO_RESET
              --undo, no human move---------------------------> same state (NOTHING TO UNDO)
 UNDO_RESET   --map = committed map + settle time-------------> HUMAN_TURN (CORRECT)
 UNDO_RESET   --undo----------------------------------------> ignored until CORRECT

 any commit   --game end found--------------------------------> GAME_END
 HUMAN_TURN, PROMOTION, ENGINE_WAIT, ENGINE_MOVE
              --confirm_long----------------------------------> GAME_END (resignation)
 GAME_END     --confirm---------------------------------------> SETTINGS
```

An undo from GAME_END after a resignation removes only the resignation. The board does not change, so the state goes to HUMAN_TURN at once.

In ENGINE_WAIT, the controller compares each new occupancy map with the committed map. Each square that differs gets the role `wrong`, so the human sees a moved piece before the engine reply arrives.

In RESUME, the display shows `RESUME MOVE 12` and the highlight gives `wrong` for each square that differs from the committed map of the saved game. The setup check has the same limit as at the game start: the occupancy map cannot show piece types.

## Settings

| Setting | Values | Default |
|---|---|---|
| Human side | white, black | white |
| Personality | from `GET /personalities` | `default` |
| Strength | 800 to 2800 Elo, steps of 100 | 1600 |
| Think time | 1, 2, 3, 5, 10, 30 s | 3 s |

The engine request sends the think time as `movetime_ms`. The engine server accepts any value from 100 to 60000 ms, so the list of values can change in the controller only.

## Move detection

The detector runs in HUMAN_TURN.

1. **At each commit**, the detector generates the legal moves once and calculates the result map of each move. A later map change needs only a byte compare. It does not generate moves again.
2. **History.** The detector records the squares that went empty after the last commit. When the occupancy map equals the committed map, the detector clears this record. This lets the human put the pieces back and start again.
3. **Candidates.** A legal move is a candidate when its result map equals the current occupancy map. A capture is a candidate only when the detector saw its capture square empty after the last commit (capture order). For en passant, the capture square is the square of the captured pawn.
4. **One candidate.** The controller commits it after the settle time, or at once on `confirm`.
5. **Promotion.** When all candidates are promotions of one pawn, the controller waits for the settle time, then goes to PROMOTION.
6. **Several candidates of different moves.** The controller does not select one. The display shows `UNCLEAR: REDO`, and `confirm` has no effect. The human puts the pieces back to the committed map and makes the move again. Example: after Bxf7, the human lifts a d5 pawn to straighten it. Both Bxd5 and Bxf7 now fit, so the controller asks for the move again.
7. **No candidate.** The display does not change. The human can hold a piece in the air for any time. The display shows `NO MATCH` only after the map is unchanged for 3 s and differs from the committed map.

The engine move uses the same capture rule. The controller commits an engine capture only after it saw the capture square empty. Without this rule, a lift of the capturing piece gives the expected map before the piece reaches its square.

The castling order rule (king first) prevents a rook-first castle from committing a rook move.

## Undo

1. The human presses `undo`. The controller removes the last human move and the engine move after it, if there is one.
2. The display shows the move to undo, for example `UNDO 12. Nf3`. While a captured piece is still missing, it names that piece instead, for example `PUT n ON e5`.
3. The highlight gives `from` and `to` for each piece to move back, and `restore` for each captured piece to put back.
4. When the occupancy map equals the earlier committed map for the settle time, the display shows `CORRECT` and the state is HUMAN_TURN.

## Engine server

### API

All requests and replies are JSON.

`POST /move`

```json
{"request_id": 17, "start": "startpos", "moves": ["e2e4", "e7e5"],
 "personality": "tal", "strength": 1600, "movetime_ms": 3000}
```

Reply `200`: `{"request_id": 17, "move": "g1f3"}`. Reply `400` for a bad request, an illegal move in the list, or `movetime_ms` outside 100 to 60000. Reply `503` if Rodent IV does not answer in `movetime_ms + 3000` ms.

`GET /personalities` → `{"personalities": ["default", "tal", "defender", ...]}`

`GET /health` → `{"ok": true}`

### Rodent IV process

- One Rodent IV process stays open. The server sends one search at a time.
- When a new request arrives during a search, the server sends `stop`, discards the old `bestmove`, and starts the new search. The newest request is always the correct one, because the controller ignores old request IDs.
- For each request, the server sends, in this order:
  1. `setoption name PersonalityFile value <name>.txt`. This calls `DefaultWeights()`, so no value from the previous personality stays. It also reads the opening book that the personality names.
  2. `setoption name UCI_LimitStrength value true` and `setoption name UCI_Elo value <strength>`. These must follow step 1, because `DefaultWeights()` changes the weakening setting.
  3. `isready`, then wait for `readyok`.
  4. `ucinewgame`, `position startpos moves ...`, `go movetime N`.
- The server checks every move in the list with its own legality check (python-chess, CPython only) before it sends the list to Rodent IV. Rodent IV skips an illegal move with no error.
- The Docker image targets a Raspberry Pi 4 (4 GB RAM) with a 64-bit operating system (`linux/arm64`).
- The Docker image sets `RODENT4PERSONALITIES` and `RODENT4BOOKS` and copies both folders.
- The server restarts Rodent IV if the process stops.

## ESP32 main loop

`esp32/main.py` is a reference main loop. It runs on the ESP32 with stub drivers. The real drivers replace the stubs and keep the same functions.

- The main loop uses MicroPython `asyncio`. The HTTP request runs as a task on a non-blocking socket, so the sensor reads, the button reads, and `on_tick` continue during an engine search. `urequests` blocks for the full search time and is not permitted.
- The main loop checks the reply move again with the controller before it shows it (the controller does this in `on_engine_reply`).
- The code goes to the ESP32 as `.mpy` files or frozen modules, so the device does not compile source text into its heap.
- The main loop writes an event log (see below).

## Event log

The main loop appends one line to `/log.txt` for each controller input. The controller itself does not log. The format is plain text, so a terminal can read it and the desktop UI can replay it:

```
1200 M 00000000ffff00ff   occupancy map, 16 hex characters, rank 1 first
1850 B confirm            button name
4100 R 17 g1f3            engine reply: request id, move
4100 E 17 timeout         engine error: request id, text
```

The number is `now_ms`. A replay feeds the lines to a new controller in order and must give the same outputs. The desktop UI can load a log file and step through it. The log restarts at each power-up, and the main loop deletes it when it is larger than 256 KB.

## MicroPython constraints on `controller/`

- Use only language features that MicroPython supports: no `dataclasses`, no `typing` at run time, no `enum`, no `abc`.
- A small integer in MicroPython on the ESP32 has 31 bits. A 64-bit value is a heap object, and each operation on it allocates memory. So the occupancy map is 8 bytes, and the position is a `bytearray` of 64.
- Do not use recursion in the move generator.
- Keep the position history as a list of compact keys for threefold repetition, not as full position copies.

## Desktop UI

- A CPython script starts a stdlib HTTP server on `localhost:8000` and holds one controller object.
- The browser page shows the board. A drag lifts a piece and places it, and makes the same map changes as the hardware. A click on a square changes only its occupancy.
- The page has the same buttons as the board and shows the display text and the highlight.
- The page also shows the internal position (piece types), which the hardware cannot show.
- The script sends engine requests to `pibot:8030`, or to the same Docker image on this computer.

## Tests

- **Move generator**: perft tests (counts of legal move sequences to a fixed depth) against published values for six standard positions.
- **Detector**: scenario tests with lists of `(map, now_ms)` inputs: normal move, capture, capture with an accidental lift, a lift with no capture, castling, en passant, promotion, promotion with capture.
- **Controller**: full games with a fake engine that returns fixed moves. Every state and every transition in "Controller states".
- **Engine server**: tests with a fake UCI process. One test with the real Rodent IV in Docker.
- **MicroPython**: the design target is a standard ESP32 without PSRAM (approximately 100 KB free heap). The `controller/` tests also run in the MicroPython Unix port with `-X heapsize=100K`. The Unix port has 64-bit small integers, so a final test runs on an ESP32.

## Open questions

None at this time.
