# The controller state machine. See ARCHITECTURE.md, "Controller interface"
# and "Controller states". The controller does no I/O: each input method
# changes the state and returns one Output.

from controller import occupancy, protocol, rules
from controller.board import (
    BISHOP,
    BLACK,
    FLAG_CASTLE,
    KNIGHT,
    PIECE_LETTERS,
    QUEEN,
    ROOK,
    WHITE,
    move_flag,
    move_from,
    move_promotion,
    move_to,
    square_name,
)
from controller.detector import Detector, capture_square, is_promotion_set
from controller.game import Game

SETTLE_MS = 500
NO_MATCH_MS = 3000
RETRY_MS = 5000

SETTINGS = "settings"
RESUME = "resume"
HUMAN_TURN = "human_turn"
PROMOTION = "promotion"
ENGINE_WAIT = "engine_wait"
ENGINE_MOVE = "engine_move"
UNDO_RESET = "undo_reset"
GAME_END = "game_end"

STRENGTHS = tuple(range(800, 2900, 100))
THINK_SECONDS = (1, 2, 3, 5, 10, 30)
PROMOTE_BUTTONS = {"promote_q": QUEEN, "promote_r": ROOK, "promote_b": BISHOP, "promote_n": KNIGHT}

END_TEXT = {
    rules.MATE_WHITE_WINS: "MATE: WHITE WINS",
    rules.MATE_BLACK_WINS: "MATE: BLACK WINS",
    rules.STALEMATE: "DRAW: STALEMATE",
    rules.MATERIAL: "DRAW: MATERIAL",
    rules.REPETITION: "DRAW: REPETITION",
    rules.FIFTY_MOVES: "DRAW: 50 MOVES",
    rules.RESIGNATION: "YOU RESIGNED",
}


def default_settings():
    return {"side": "white", "personality": "default", "strength": 1600, "think_s": 3}


class Output:
    def __init__(self):
        self.display = ""
        self.highlight = []
        self.engine_request = None
        self.fetch_personalities = False
        self.save_settings = None
        self.save_game = None


class Controller:
    def __init__(self):
        self.state = SETTINGS
        self.settings = default_settings()
        self.personalities = ["default"]
        self.setting_shown = "side"
        self.game = Game()
        self.detector = Detector(self.game.board)
        self.occ_map = occupancy.START_MAP
        self.now = 0  # the last now_ms seen; the engine inputs carry no clock
        self.map_since = 0
        self.candidates = []
        self.message = None  # text that replaces the state's display until the map changes
        self.end_code = None
        self.engine_move = None
        self.engine_san = ""
        self.expected_map = None  # the occupancy map after the engine move
        self.request_id = 0
        self.retry_at = None
        self.undo_text = ""
        self._out = Output()

    # Inputs

    def load_settings(self, data):
        self._out.fetch_personalities = True
        self._apply_settings(data)
        return self._run(0)

    def load_game(self, data):
        if data and data.get("moves"):
            self._apply_settings(data.get("settings"))
            self.game.reset()
            for text in data["moves"].split():
                move = self.game.board.parse_uci(text)
                if move is None:
                    self.game.reset()
                    self._out.save_game = {}
                    return self._run(0)
                self.game.push(move)
            end = rules.game_end(self.game)
            if end:
                self._end_game(end)
            else:
                self.detector = Detector(self.game.board)
                self.state = RESUME
        return self._run(0)

    def _apply_settings(self, data):
        """Take each saved value that is in its allowed list; keep the default for the rest."""
        if not data:
            return
        s = self.settings
        if data.get("side") in ("white", "black"):
            s["side"] = data["side"]
        if data.get("strength") in STRENGTHS:
            s["strength"] = data["strength"]
        if data.get("think_s") in THINK_SECONDS:
            s["think_s"] = data["think_s"]
        if isinstance(data.get("personality"), str):
            s["personality"] = data["personality"]

    def on_personalities(self, names):
        if names:
            self.personalities = list(names)
            if self.settings["personality"] not in names:
                self.settings["personality"] = names[0]
        return self._run(0)

    def on_occupancy(self, occ_map, now):
        self.now = now
        if occ_map != self.occ_map:
            self.occ_map = occ_map
            self.map_since = now
            self.message = None
            if self.state in (HUMAN_TURN, PROMOTION, ENGINE_MOVE):
                self.candidates = self.detector.update(occ_map)
                if self.state == PROMOTION:
                    self.state = HUMAN_TURN
        return self._run(now)

    def on_tick(self, now):
        self.now = now
        return self._run(now)

    def on_engine_reply(self, request_id, text):
        if self.state == ENGINE_WAIT and request_id == self.request_id:
            move = self.game.board.parse_uci(text)
            if move is None:
                self._engine_failed()
            else:
                self.engine_move = move
                self.engine_san = self.game.board.san(move)  # once; san() is slow on the ESP32
                for candidate, result, cap in self.detector.moves:
                    if candidate == move:
                        self.expected_map = result
                self.candidates = self.detector.update(self.occ_map)
                self.map_since = self.now
                self.retry_at = None
                self.state = ENGINE_MOVE
        return self._run(self.now)

    def on_engine_error(self, request_id, text):
        if self.state == ENGINE_WAIT and request_id == self.request_id:
            self._engine_failed()
        return self._run(self.now)

    def on_button(self, name, now):
        self.now = now
        state = self.state
        if name == "undo" and state not in (SETTINGS, RESUME, UNDO_RESET):
            self._undo(now)
        elif name == "confirm_long" and state in (HUMAN_TURN, PROMOTION, ENGINE_WAIT, ENGINE_MOVE):
            self._end_game(rules.RESIGNATION)
        elif state == SETTINGS:
            self._settings_button(name)
        elif state == RESUME:
            if name == "confirm" and self.occ_map == self.detector.committed:
                self._enter_turn(now)
            elif name == "confirm_long":
                self._out.save_game = {}
                self.state = SETTINGS
        elif name == "confirm" and state in (HUMAN_TURN, ENGINE_MOVE):
            self._settle(now, force=True)
        elif state == PROMOTION and name in PROMOTE_BUTTONS:
            for move in self.candidates:
                if move_promotion(move) == PROMOTE_BUTTONS[name]:
                    self._commit(move, now)
        elif state == GAME_END and name == "confirm":
            self.state = SETTINGS
        return self._run(now)

    # Buttons in SETTINGS

    def _settings_button(self, name):
        s = self.settings
        self.message = None
        if name == "side":
            s["side"] = "black" if s["side"] == "white" else "white"
        elif name == "personality":
            names = self.personalities
            i = names.index(s["personality"]) + 1 if s["personality"] in names else 0
            s["personality"] = names[i % len(names)]
            if len(names) == 1:
                self._out.fetch_personalities = True
        elif name == "strength":
            s["strength"] = STRENGTHS[(STRENGTHS.index(s["strength"]) + 1) % len(STRENGTHS)]
        elif name == "think_time":
            s["think_s"] = THINK_SECONDS[(THINK_SECONDS.index(s["think_s"]) + 1) % len(THINK_SECONDS)]
        elif name == "confirm":
            if self.occ_map == occupancy.START_MAP:
                self._out.save_settings = dict(s)
                self.game.reset()
                self._enter_turn(self.now)
            else:
                self.message = "SETUP: %d WRONG" % len(occupancy.diff(self.occ_map, occupancy.START_MAP))
            return
        self.setting_shown = name

    # Game flow

    def _human_side(self):
        return WHITE if self.settings["side"] == "white" else BLACK

    def _enter_turn(self, now):
        """After a start, a commit, an undo, or a resume: the human's turn, or ask the engine."""
        self.detector = Detector(self.game.board)
        self.candidates = self.detector.update(self.occ_map)
        self.message = None
        self.map_since = now
        self._out.save_game = {"settings": dict(self.settings), "moves": self.game.uci_text()}
        if self.game.board.turn == self._human_side():
            self.state = HUMAN_TURN
        else:
            self._request_engine_move()

    def _request_engine_move(self):
        self.request_id += 1
        self.retry_at = None
        self._out.engine_request = protocol.build_request(self.request_id, self.game, self.settings)
        self.state = ENGINE_WAIT

    def _engine_failed(self):
        self.retry_at = self.now + RETRY_MS

    def _commit(self, move, now):
        self.game.push(move)
        end = rules.game_end(self.game)
        if end:
            self._end_game(end)
        else:
            self._enter_turn(now)

    def _end_game(self, code):
        self.end_code = code
        self.message = None
        self._out.save_game = {}
        self.state = GAME_END

    def _settle(self, now, force=False):
        """Commit or report, once the map has stayed unchanged for the settle time."""
        settled = force or now - self.map_since >= SETTLE_MS
        candidates = self.candidates
        if self.state == HUMAN_TURN:
            if not candidates:
                if self.occ_map != self.detector.committed and now - self.map_since >= NO_MATCH_MS:
                    self.message = "NO MATCH"
            elif settled:
                if len(candidates) == 1:
                    self._commit(candidates[0], now)
                elif is_promotion_set(candidates):
                    self.state = PROMOTION
                else:
                    self.message = "UNCLEAR: REDO"
        elif self.state == ENGINE_MOVE and settled:
            if self.engine_move in candidates and (len(candidates) == 1 or is_promotion_set(candidates)):
                self._commit(self.engine_move, now)
            elif len(candidates) > 1:
                self.message = "UNCLEAR: REDO"
            elif self.occ_map == self.expected_map:
                # The capture square never read empty: the piece must come off first.
                self.message = "LIFT " + square_name(capture_square(self.game.board, self.engine_move))
            elif self.occ_map != self.detector.committed:
                self.message = "WRONG: " + self.engine_san
        elif self.state == UNDO_RESET and settled and self.occ_map == self.detector.committed:
            self._enter_turn(now)
            self.message = "CORRECT"

    def _undo(self, now):
        board = self.game.board
        human = self._human_side()
        if self.state == GAME_END and self.end_code == rules.RESIGNATION:
            self._enter_turn(now)
            return
        if board.ply == 0 or (board.ply == 1 and human == BLACK):
            self.message = "NOTHING TO UNDO"
            return
        if board.turn == human:
            self.game.pop()  # the engine move
        move = self.game.pop()  # the human move
        san = self._san(move)
        self.undo_text = "UNDO %d. %s" % (board.fullmove_number, san)
        if len(self.undo_text) > 16:
            self.undo_text = "UNDO " + san
        self.message = None
        self.detector = Detector(board)
        self.state = UNDO_RESET

    def _san(self, move):
        return self.game.board.san(move)

    # Output

    def _run(self, now):
        if self.state in (HUMAN_TURN, ENGINE_MOVE, UNDO_RESET):
            self._settle(now)
        elif self.state == ENGINE_WAIT and self.retry_at is not None and now >= self.retry_at:
            self._request_engine_move()
        out = self._out
        out.display = self._display()[:16]
        out.highlight = self._highlight()
        self._out = Output()
        return out

    def _display(self):
        state = self.state
        if self.message:
            return self.message
        board = self.game.board
        if state == SETTINGS:
            s = self.settings
            shown = self.setting_shown
            if shown == "side":
                return "SIDE: " + s["side"].upper()
            if shown == "personality":
                return "PERS: " + s["personality"]
            if shown == "strength":
                return "ELO: %d" % s["strength"]
            return "TIME: %dS" % s["think_s"]
        if state == RESUME:
            return "RESUME MOVE %d" % board.fullmove_number
        if state == HUMAN_TURN:
            return "%d. %s" % (board.fullmove_number, "CHECK" if board.is_check() else "YOUR MOVE")
        if state == PROMOTION:
            return "PROMOTE: Q R B N"
        if state == ENGINE_WAIT:
            return "ENGINE OFFLINE" if self.retry_at is not None else "THINKING..."
        if state == ENGINE_MOVE:
            return "ENGINE: " + self.engine_san
        if state == UNDO_RESET:
            for sq in occupancy.diff(self.occ_map, self.detector.committed):
                if not occupancy.occupied(self.occ_map, sq):
                    return "PUT %s ON %s" % (PIECE_LETTERS[board.squares[sq] & 7], square_name(sq))
            return self.undo_text
        return END_TEXT[self.end_code]

    def _highlight(self):
        state = self.state
        if state == UNDO_RESET:
            lit = []
            for sq in occupancy.diff(self.occ_map, self.detector.committed):
                lit.append((square_name(sq), "from" if occupancy.occupied(self.occ_map, sq) else "restore"))
            return lit
        if state == ENGINE_MOVE:
            return self._engine_move_highlight()
        if state in (RESUME, ENGINE_WAIT):
            target = self.detector.committed
        elif state == SETTINGS and self.message:
            target = occupancy.START_MAP
        else:
            return []
        return [(square_name(sq), "wrong") for sq in occupancy.diff(self.occ_map, target)]

    def _engine_move_highlight(self):
        move = self.engine_move
        frm, to = move_from(move), move_to(move)
        lit = [(square_name(frm), "from"), (square_name(to), "to")]
        cap = capture_square(self.game.board, move)
        if cap >= 0:
            lit.append((square_name(cap), "remove"))
        if move_flag(move) == FLAG_CASTLE:
            if to > frm:
                lit += [(square_name(frm + 3), "from"), (square_name(frm + 1), "to")]
            else:
                lit += [(square_name(frm - 4), "from"), (square_name(frm - 1), "to")]
        if self.message and self.message.startswith("WRONG"):
            for sq in occupancy.diff(self.occ_map, self.expected_map):
                lit.append((square_name(sq), "wrong"))
        return lit
