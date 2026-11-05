# Chess Board Controller

The controller tracks a game on a physical board that has a reed switch under each square. It finds each human move from sensor data, asks an engine for the engine move, and tells the human which piece to move.

## Language

### Components

**Controller**:
The program on the ESP32 that keeps the position, detects human moves, and asks the engine for each engine move.
_Avoid_: Chess engine, back end, bot

**Engine**:
The program that selects the engine move for a position. The main engine is Rodent IV on the engine server.
_Avoid_: AI, bot, chess AI

**Engine server**:
The Raspberry Pi on the home network that runs the engine and answers requests from the controller.
_Avoid_: Pi, backend server, API

**Sensor driver**:
The hardware component that reads the reed switches and sends an occupancy map to the controller. It is outside this project.
_Avoid_: Sensor engine, sensor layer, hardware layer

**Display**:
A small screen that shows one line of 16 characters, for example the move number and messages to the human.
_Avoid_: LED output, screen, LCD

**Event log**:
A text file on the ESP32 with one line per controller input and its time. A replay of the file gives the same controller outputs.
_Avoid_: Trace, debug log, history file

### Board state

**Position**:
The full chess state: the piece on each square, the side to move, castling rights, the en passant square, and the move counters.
_Avoid_: Board, board state, game state

**Occupancy map**:
A set of 64 values that tells, for each square, if a piece is on it. It does not tell which piece.

**Committed map**:
The occupancy map of the position after the last commit.
_Avoid_: Last map, base map
_Avoid_: Sensor state, bitmap, board reading

### Opponent

**Personality**:
A named set of engine evaluation settings that gives the engine a style of play, for example "tal" or "defender".
_Avoid_: Style, character, profile, bot

**Strength**:
The Elo rating that the engine plays at, from 800 to 2800.
_Avoid_: Difficulty, level, skill

**Think time**:
The time that the engine searches for each engine move. The human selects it before the game. The default is 3 s.
_Avoid_: Move time, search time, thinking delay

**Human side**:
The colour that the human plays, white or black. The human selects it with a button before the game starts.
_Avoid_: Player colour, user side

**Engine side**:
The colour that the engine plays. It is always the colour opposite to the human side.
_Avoid_: AI side, computer side

**Setup check**:
The comparison of the occupancy map with the start occupancy (ranks 1, 2, 7, and 8 occupied) before a game starts. Every game starts from the standard position.
_Avoid_: Board check, start validation

### Moves

**Human move**:
A move that the human player makes with a piece of the human side.
_Avoid_: Player move, user move

**Engine move**:
The move that the engine selects for the engine side. The human moves the piece on the board for the engine.
_Avoid_: AI move, suggested move, computer move

**Removal delay**:
The time (150 ms) that a square must read empty before the sensor driver reports that a piece has left it.
_Avoid_: Debounce, lift delay

**Settle time**:
The time (500 ms) that an occupancy map must stay unchanged before the controller acts on it: a commit, a `CORRECT` after an undo, or a `WRONG` message.
_Avoid_: Lock-in delay, wait time

**Commit**:
The step that makes a detected move part of the game. After a commit, the move cannot change except by an undo.
_Avoid_: Lock in, finalize, accept

**Capture order**:
The rule that the human removes the captured piece and keeps its square empty for at least 200 ms before placing the moving piece on that square. The controller accepts a capture only when it saw the capture square empty since the last commit, or since the board last matched the committed map.
_Avoid_: Capture delay, removal rule

**Castling order**:
The rule that the human moves the king before the rook when castling.
_Avoid_: Castle sequence, king-first rule

**Promotion choice**:
The piece type that the human selects with a button when a pawn reaches the last rank.
_Avoid_: Promotion piece, underpromotion selection

**Highlight**:
The list of squares that the hardware must light. Each square has a role: `from`, `to`, `remove` (a piece to take off), `restore` (a piece to put back after an undo), or `wrong` (a square that differs from the expected map).
_Avoid_: LED pattern, lit squares, indication

**Expected map**:
The occupancy map that the board must show after the human makes the engine move.
_Avoid_: Target map, goal state

### Game end

**Game end**:
The point where the controller stops the game: checkmate, stalemate, insufficient material, threefold repetition, the 50-move rule, or resignation by the human. The controller ends a draw at once, with no claim.
_Avoid_: Game over, finish, termination

**Resignation**:
The end of the game that the human selects with a long press of the confirm button. The engine never resigns.
_Avoid_: Forfeit, concede

**Resume**:
The continuation of a saved game after a power loss. The human sets up the saved position, and the controller checks it before the game continues.
_Avoid_: Restore, reload, recover

### Controls

**Confirm button**:
A button that commits the current move at once, without the settle time.
_Avoid_: Done button, move-complete button

**Undo**:
The removal of the last human move, and of the engine move after it if there is one. The human sets up the earlier position on the board, and the controller shows `CORRECT` when the occupancy map matches. The human can then make a new human move or undo again.
_Avoid_: Takeback, rollback, revert
