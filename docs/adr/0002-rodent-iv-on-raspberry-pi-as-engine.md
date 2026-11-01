# Rodent IV on a Raspberry Pi is the engine

The human wants opponents with a selectable style (for example aggressive, defensive, or a preference for knights) and a selectable strength. Rodent IV supports both: personality files change its evaluation terms, and `UCI_Elo` sets a strength from 800 to 2800. Rodent IV runs in Docker on a Raspberry Pi 4 (4 GB RAM, 64-bit operating system) on the home network (`pibot:8030`). The ESP32 sends each position to it over Wi-Fi.

## Considered Options

- Stockfish. Rejected: modern Stockfish has no style options. A style filter over its candidate list selects only among moves that Stockfish already rates as playable, so the style does not show over a whole game.
- Public APIs (Lichess cloud evaluation, chess-api.com). Rejected: no style, and no reliable candidate list or strength settings.
- Chess.com bots. Rejected: chess.com has no API to play moves, and automation of its website breaks its terms of service.
- Komodo 14.1 (free). Rejected for now: it has the same 8 personalities as the chess.com bots and covers 800–1500 Elo with `Skill` levels, but it is freeware, not open source, and has only an x86-64 build, so the Pi 4 needs the box64 emulator.
- Maia-3. Rejected for now: it plays human-like moves for ratings from 600 to 2600, but it has no style control.
- Lichess Board API. Deferred: it gives Lichess AI levels and bot accounts, but no style control for our own engine. It can be a later option.

## Consequences

Rodent IV has had no commits since 29 April 2021. The project must keep its own Docker image and does not expect upstream fixes.
