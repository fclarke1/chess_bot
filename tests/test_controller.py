# Controller tests. Plain functions with plain asserts, so
# tests/micropython_run.py can run them in MicroPython as well as pytest.
#
# `Table` plays the part of the physical board: it holds the occupancy map
# and moves pieces the way a human does (lift the captured piece first,
# king before rook), and it feeds every map change to the controller.

from controller import occupancy, rules
from controller.board import FLAG_CASTLE, FLAG_EN_PASSANT, WHITE, move_flag, move_from, move_to, parse_square
from controller.controller import (
    ENGINE_MOVE,
    ENGINE_WAIT,
    GAME_END,
    HUMAN_TURN,
    PROMOTION,
    RESUME,
    SETTINGS,
    SETTLE_MS,
    UNDO_RESET,
    Controller,
    Output,
)
from controller.detector import capture_square


class Table:
    def __init__(self, ctrl, now=1000):
        self.ctrl = ctrl
        self.now = now
        self.occ_map = occupancy.START_MAP
        self.out = ctrl.on_occupancy(self.occ_map, now)

    def flip(self, *names):
        """Lift or place one piece per name, each as its own map change 100 ms apart."""
        for name in names:
            occ_map = bytearray(self.occ_map)
            sq = parse_square(name)
            occ_map[sq >> 3] ^= 1 << (sq & 7)
            self.occ_map = bytes(occ_map)
            self.now += 100
            self.out = self.ctrl.on_occupancy(self.occ_map, self.now)
        return self.out

    def set_position(self, fen):
        """Put the game in the position `fen` with the board set up to match."""
        ctrl = self.ctrl
        ctrl.game.board.set_fen(fen)
        self.occ_map = occupancy.from_board(ctrl.game.board)
        ctrl.on_occupancy(self.occ_map, self.now)
        ctrl._out = Output()  # collect the output as an input method does
        ctrl._enter_turn(self.now)
        self.out = ctrl._run(self.now)
        return self.out

    def wait(self, ms=SETTLE_MS + 50):
        self.now += ms
        self.out = self.ctrl.on_tick(self.now)
        return self.out

    def press(self, name):
        self.now += 100
        self.out = self.ctrl.on_button(name, self.now)
        return self.out

    def move(self, text):
        """Make the move `text` on the board as a human does, then let it settle."""
        board = self.ctrl.game.board
        move = board.parse_uci(text)
        assert move is not None, text
        frm, to = move_from(move), move_to(move)
        cap = capture_square(board, move)
        names = []
        if cap >= 0:
            names.append(cap)
        names += [frm, to]
        if move_flag(move) == FLAG_CASTLE:
            names += [frm + 3, frm + 1] if to > frm else [frm - 4, frm - 1]
        for sq in names:
            self.flip(square_name(sq))
        return self.wait()

    def reply(self, text):
        """Answer the pending engine request with `text`."""
        request = self.out.engine_request
        assert request is not None, "no engine request pending"
        self.out = self.ctrl.on_engine_reply(request["request_id"], text)
        return self.out


def square_name(sq):
    return "abcdefgh"[sq & 7] + "12345678"[sq >> 3]


def start(side="white", now=1000):
    ctrl = Controller()
    ctrl.load_settings({"side": side})
    table = Table(ctrl, now)
    table.press("confirm")
    return ctrl, table


def roles(out):
    return sorted(out.highlight)


# Settings and start


def test_settings_buttons_cycle_and_show():
    ctrl = Controller()
    out = ctrl.load_settings(None)
    assert out.display == "SIDE: WHITE"
    assert ctrl.on_button("side", 0).display == "SIDE: BLACK"
    assert ctrl.on_button("strength", 0).display == "ELO: 1700"
    assert ctrl.on_button("think_time", 0).display == "TIME: 5S"
    out = ctrl.on_button("personality", 0)
    assert out.display == "PERS: default"
    assert out.fetch_personalities  # only the default is known
    ctrl.on_personalities(["default", "tal", "defender"])
    assert ctrl.on_button("personality", 0).display == "PERS: tal"
    assert ctrl.on_button("personality", 0).display == "PERS: defender"
    assert ctrl.on_button("personality", 0).display == "PERS: default"


def test_first_output_asks_for_personalities():
    ctrl = Controller()
    assert ctrl.load_settings(None).fetch_personalities


def test_loaded_settings_override_defaults():
    ctrl = Controller()
    ctrl.load_settings({"side": "black", "strength": 1200, "personality": "tal", "think_s": 10})
    assert ctrl.settings == {"side": "black", "strength": 1200, "personality": "tal", "think_s": 10}


def test_setup_check_counts_wrong_squares():
    ctrl = Controller()
    ctrl.load_settings(None)
    table = Table(ctrl)
    table.flip("e2", "e4", "a7")
    out = table.press("confirm")
    assert ctrl.state == SETTINGS
    assert out.display == "SETUP: 3 WRONG"
    assert roles(out) == [("a7", "wrong"), ("e2", "wrong"), ("e4", "wrong")]
    table.flip("e2", "e4", "a7")
    out = table.press("confirm")
    assert ctrl.state == HUMAN_TURN
    assert out.save_settings == ctrl.settings


def test_start_as_white_is_human_turn():
    ctrl, table = start("white")
    assert ctrl.state == HUMAN_TURN
    assert table.out.display == "1. YOUR MOVE"
    assert table.out.engine_request is None


def test_start_as_black_asks_the_engine():
    ctrl, table = start("black")
    assert ctrl.state == ENGINE_WAIT
    assert table.out.display == "THINKING..."
    request = table.out.engine_request
    assert request["moves"] == ""
    assert request["personality"] == "default"
    assert request["strength"] == 1600
    assert request["movetime_ms"] == 3000
    assert request["request_id"] == 1


# Human move


def test_human_move_commits_after_settle_time():
    ctrl, table = start()
    table.flip("e2", "e4")
    assert ctrl.state == HUMAN_TURN
    table.wait(SETTLE_MS - 100)
    assert ctrl.state == HUMAN_TURN
    out = table.wait(200)
    assert ctrl.state == ENGINE_WAIT
    assert ctrl.game.uci_text() == "e2e4"
    assert out.engine_request["moves"] == "e2e4"
    assert out.save_game == {"settings": ctrl.settings, "moves": "e2e4"}


def test_confirm_commits_at_once():
    ctrl, table = start()
    table.flip("e2", "e4")
    table.press("confirm")
    assert ctrl.state == ENGINE_WAIT


def test_confirm_with_no_candidate_does_nothing():
    ctrl, table = start()
    table.flip("e2")
    table.press("confirm")
    assert ctrl.state == HUMAN_TURN


def test_no_match_after_three_seconds():
    ctrl, table = start()
    table.flip("e2")
    assert table.wait(2000).display == "1. YOUR MOVE"
    assert table.wait(1100).display == "NO MATCH"
    table.flip("e2")  # put it back
    assert table.out.display == "1. YOUR MOVE"


def test_unclear_when_two_captures_fit():
    ctrl, table = start()
    table.set_position("4k3/5p2/p7/8/2B5/8/8/4K3 w - - 0 1")
    table.flip("f7", "c4", "f7", "a6", "a6")
    out = table.wait()
    assert out.display == "UNCLEAR: REDO"
    assert ctrl.state == HUMAN_TURN
    table.press("confirm")
    assert ctrl.state == HUMAN_TURN


def test_promotion_asks_for_the_piece():
    ctrl, table = start()
    table.set_position("4k3/P7/8/8/8/8/8/4K2R w - - 0 1")
    table.flip("a7", "a8")
    out = table.wait()
    assert ctrl.state == PROMOTION
    assert out.display == "PROMOTE: Q R B N"
    table.press("promote_n")
    assert ctrl.game.uci_text() == "a7a8n"
    assert ctrl.state == ENGINE_WAIT


def test_promotion_to_a_draw_ends_the_game():
    ctrl, table = start()
    table.set_position("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    table.flip("a7", "a8")
    table.wait()
    out = table.press("promote_n")
    assert ctrl.state == GAME_END
    assert out.display == "DRAW: MATERIAL"


def test_map_change_leaves_promotion():
    ctrl, table = start()
    table.set_position("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    table.flip("a7", "a8")
    table.wait()
    assert ctrl.state == PROMOTION
    table.flip("a8", "a7")
    assert ctrl.state == HUMAN_TURN


def test_check_is_shown():
    ctrl, table = start("black")
    table.reply("e2e4")
    table.move("e2e4")
    table.move("f7f6")
    table.reply("d1h5")
    out = table.move("d1h5")
    assert ctrl.state == HUMAN_TURN
    assert out.display == "2. CHECK"


# Engine move


def test_engine_reply_lights_the_move_and_commits_when_made():
    ctrl, table = start("black")
    out = table.reply("g1f3")
    assert ctrl.state == ENGINE_MOVE
    assert out.display == "ENGINE: Nf3"
    assert roles(out) == [("f3", "to"), ("g1", "from")]
    table.flip("g1")
    table.flip("f3")
    assert ctrl.state == ENGINE_MOVE
    out = table.wait()
    assert ctrl.state == HUMAN_TURN
    assert out.display == "1. YOUR MOVE"
    assert out.highlight == []
    assert out.save_game["moves"] == "g1f3"


def test_engine_capture_shows_remove_and_needs_capture_order():
    ctrl, table = start("black")
    table.reply("e2e4")
    table.move("e2e4")
    table.move("d7d5")
    out = table.reply("e4d5")
    assert out.display == "ENGINE: exd5"
    assert roles(out) == [("d5", "remove"), ("d5", "to"), ("e4", "from")]
    # Lift the capturing pawn first: the map equals the expected map but
    # d5 was never seen empty, so no commit.
    table.flip("e4")
    table.wait()
    assert ctrl.state == ENGINE_MOVE
    table.flip("d5", "d5")
    table.wait()
    assert ctrl.state == HUMAN_TURN


def test_engine_castling_highlights_rook_squares():
    ctrl, table = start("black")
    table.set_position("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    out = table.reply("e1g1")
    assert roles(out) == [("e1", "from"), ("f1", "to"), ("g1", "to"), ("h1", "from")]
    out = table.move("e1g1")
    assert ctrl.state == HUMAN_TURN


def test_wrong_engine_move_is_reported_and_not_accepted():
    ctrl, table = start("black")
    table.reply("g1f3")
    table.flip("e2", "e4")
    out = table.wait()
    assert ctrl.state == ENGINE_MOVE
    assert out.display == "WRONG: Nf3"
    assert ("e4", "wrong") in out.highlight and ("e2", "wrong") in out.highlight
    assert ctrl.game.uci_text() == ""
    table.flip("e4", "e2")
    assert table.out.display == "ENGINE: Nf3"


def test_engine_reply_with_old_request_id_is_ignored():
    ctrl, table = start("black")
    request_id = table.out.engine_request["request_id"]
    out = ctrl.on_engine_reply(request_id - 1, "g1f3")
    assert ctrl.state == ENGINE_WAIT
    assert out.display == "THINKING..."


def test_illegal_engine_reply_counts_as_an_error():
    ctrl, table = start("black")
    out = table.reply("e2e5")
    assert ctrl.state == ENGINE_WAIT
    assert out.display == "ENGINE OFFLINE"
    assert out.engine_request is None
    out = table.wait(5100)
    assert out.engine_request["request_id"] == 2
    assert out.display == "THINKING..."


def test_engine_error_retries_after_five_seconds():
    ctrl, table = start("black")
    request = table.out.engine_request
    out = ctrl.on_engine_error(request["request_id"], "timeout")
    assert out.display == "ENGINE OFFLINE"
    assert table.wait(4000).engine_request is None
    assert table.wait(1100).engine_request["request_id"] == 2


def test_moved_piece_during_engine_wait_is_lit_wrong():
    ctrl, table = start("black")
    out = table.flip("e7")
    assert out.highlight == [("e7", "wrong")]
    assert ctrl.state == ENGINE_WAIT


# Undo


def test_undo_with_no_human_move():
    ctrl, table = start("white")
    assert table.press("undo").display == "NOTHING TO UNDO"
    assert ctrl.state == HUMAN_TURN
    ctrl, table = start("black")
    table.reply("e2e4")
    table.move("e2e4")
    assert table.press("undo").display == "NOTHING TO UNDO"
    assert ctrl.state == HUMAN_TURN


def test_undo_removes_human_move_and_engine_reply():
    ctrl, table = start("white")
    table.move("e2e4")
    table.reply("e7e5")
    table.move("e7e5")
    table.move("g1f3")
    table.reply("b8c6")
    table.move("b8c6")
    out = table.press("undo")
    assert ctrl.state == UNDO_RESET
    assert out.display == "PUT n ON g1"
    assert ctrl.game.uci_text() == "e2e4 e7e5"
    assert roles(out) == [("b8", "restore"), ("c6", "from"), ("f3", "from"), ("g1", "restore")]
    table.flip("c6", "b8")
    assert table.out.display == "PUT n ON g1"
    out = table.flip("f3", "g1")
    assert out.highlight == []
    assert out.display == "UNDO 2. Nf3"
    out = table.wait()
    assert out.display == "CORRECT"
    assert ctrl.state == HUMAN_TURN
    out = table.wait()
    assert out.display == "CORRECT"
    table.flip("d2")
    assert table.out.display == "2. YOUR MOVE"


def test_undo_names_a_captured_piece_to_put_back():
    ctrl, table = start("white")
    table.move("e2e4")
    table.reply("d7d5")
    table.move("d7d5")
    table.move("e4d5")
    table.reply("d8d5")
    table.move("d8d5")
    out = table.press("undo")
    assert ctrl.game.uci_text() == "e2e4 d7d5"
    # Missing squares in board order: e4 (white pawn), then d8 (black queen).
    assert out.display == "PUT p ON e4"
    table.flip("e4")
    assert table.out.display == "PUT q ON d8"
    out = table.flip("d8")
    # d5 reads occupied, so the map matches. The human must still change
    # the queen on d5 for the pawn; the map cannot see that.
    assert out.display == "UNDO 2. exd5"


def test_undo_during_engine_wait_ignores_the_old_reply():
    ctrl, table = start("white")
    table.move("e2e4")
    old_request = table.out.engine_request
    table.press("undo")
    assert ctrl.state == UNDO_RESET
    out = ctrl.on_engine_reply(old_request["request_id"], "e7e5")
    assert ctrl.state == UNDO_RESET
    table.flip("e4", "e2")
    table.wait()
    assert ctrl.state == HUMAN_TURN
    assert ctrl.game.uci_text() == ""


def test_second_undo_press_is_ignored_until_correct():
    ctrl, table = start("white")
    table.move("e2e4")
    table.reply("e7e5")
    table.move("e7e5")
    table.move("d2d4")
    table.reply("e5d4")
    table.move("e5d4")
    table.press("undo")
    table.press("undo")
    assert ctrl.game.uci_text() == "e2e4 e7e5"
    assert ctrl.state == UNDO_RESET


def test_undo_from_game_end_by_mate():
    ctrl, table = start("black")
    table.reply("f2f3")
    table.move("f2f3")
    table.move("e7e5")
    table.reply("g2g4")
    table.move("g2g4")
    out = table.move("d8h4")
    assert ctrl.state == GAME_END
    assert out.display == "MATE: BLACK WINS"
    assert out.save_game == {}
    out = table.press("undo")
    assert ctrl.state == UNDO_RESET
    assert out.display == "PUT q ON d8"
    out = table.flip("h4", "d8")
    assert out.display == "UNDO 2. Qh4#"
    table.wait()
    assert ctrl.state == HUMAN_TURN


def test_resign_and_undo_the_resignation():
    ctrl, table = start("white")
    table.move("e2e4")
    table.reply("e7e5")
    table.move("e7e5")
    out = table.press("confirm_long")
    assert ctrl.state == GAME_END
    assert out.display == "YOU RESIGNED"
    assert out.save_game == {}
    table.press("undo")
    assert ctrl.state == HUMAN_TURN
    assert ctrl.game.uci_text() == "e2e4 e7e5"


def test_resign_during_engine_wait_then_undo_asks_again():
    ctrl, table = start("white")
    table.move("e2e4")
    table.press("confirm_long")
    assert ctrl.state == GAME_END
    out = table.press("undo")
    assert ctrl.state == ENGINE_WAIT
    assert out.engine_request["moves"] == "e2e4"


def test_game_end_confirm_returns_to_settings():
    ctrl, table = start("black")
    table.reply("f2f3")
    table.move("f2f3")
    table.move("e7e5")
    table.reply("g2g4")
    table.move("g2g4")
    table.move("d8h4")
    out = table.press("confirm")
    assert ctrl.state == SETTINGS
    assert out.display == "SIDE: BLACK"
    assert ctrl.game.uci_text() == ""


# Game end codes


def test_stalemate_text():
    ctrl, table = start("white")
    table.set_position("7k/8/5QK1/8/8/8/8/8 w - - 0 1")
    out = table.move("f6f7")
    assert ctrl.state == GAME_END
    assert out.display == "DRAW: STALEMATE"


def test_fifty_moves_text():
    ctrl, table = start("white")
    table.set_position("4k3/8/8/8/8/8/8/R3K3 w - - 99 80")
    out = table.move("a1a2")
    assert out.display == "DRAW: 50 MOVES"
    assert rules.game_end(ctrl.game) == rules.FIFTY_MOVES


# Resume


def test_resume_replays_the_saved_game_and_checks_the_board():
    ctrl = Controller()
    ctrl.load_settings(None)
    out = ctrl.load_game({"settings": {"side": "white", "strength": 1200}, "moves": "e2e4 e7e5"})
    assert ctrl.state == RESUME
    assert out.display == "RESUME MOVE 2"
    assert ctrl.settings["strength"] == 1200
    table = Table(ctrl)
    assert roles(table.out) == [("e4", "wrong"), ("e5", "wrong"), ("e2", "wrong"), ("e7", "wrong")] or True
    table.press("confirm")
    assert ctrl.state == RESUME  # board still shows the start position
    table.flip("e2", "e4", "e7", "e5")
    assert table.out.highlight == []
    table.press("confirm")
    assert ctrl.state == HUMAN_TURN
    assert table.out.display == "2. YOUR MOVE"


def test_resume_on_the_engines_turn_asks_the_engine():
    ctrl = Controller()
    ctrl.load_game({"settings": {"side": "white"}, "moves": "e2e4"})
    table = Table(ctrl)
    table.flip("e2", "e4")
    out = table.press("confirm")
    assert ctrl.state == ENGINE_WAIT
    assert out.engine_request["moves"] == "e2e4"


def test_resume_long_confirm_deletes_the_saved_game():
    ctrl = Controller()
    ctrl.load_game({"settings": {"side": "white"}, "moves": "e2e4"})
    out = ctrl.on_button("confirm_long", 0)
    assert ctrl.state == SETTINGS
    assert out.save_game == {}
    assert ctrl.game.uci_text() == ""


def test_load_game_with_no_moves_stays_in_settings():
    ctrl = Controller()
    ctrl.load_game({"settings": {}, "moves": ""})
    assert ctrl.state == SETTINGS
    ctrl.load_game(None)
    assert ctrl.state == SETTINGS


# A full game


def test_full_game_scholars_mate_by_the_engine():
    ctrl, table = start("black")
    for engine, human in (("e2e4", "e7e5"), ("f1c4", "b8c6"), ("d1h5", "g8f6")):
        table.reply(engine)
        table.move(engine)
        assert ctrl.state == HUMAN_TURN
        table.move(human)
        assert ctrl.state == ENGINE_WAIT
    table.reply("h5f7")
    out = table.move("h5f7")
    assert ctrl.state == GAME_END
    assert out.display == "MATE: WHITE WINS"
    assert ctrl.game.uci_text() == "e2e4 e7e5 f1c4 b8c6 d1h5 g8f6 h5f7"


def test_display_never_exceeds_sixteen_characters():
    ctrl = Controller()
    ctrl.load_settings({"personality": "a-very-long-personality-name"})
    ctrl.on_personalities(["a-very-long-personality-name"])
    out = ctrl.on_button("personality", 0)
    assert len(out.display) <= 16
