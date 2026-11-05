# Tests for game.py and rules.py. Plain functions with plain asserts, so
# tests/micropython_run.py can run them in MicroPython as well as pytest.

from controller.board import START_FEN, Board
from controller.game import Game, position_key
from controller.rules import (
    FIFTY_MOVES,
    MATE_BLACK_WINS,
    MATE_WHITE_WINS,
    MATERIAL,
    REPETITION,
    STALEMATE,
    game_end,
)


def play(game, *texts):
    for text in texts:
        move = game.board.parse_uci(text)
        assert move is not None, text
        game.push(move)


def game_from(fen):
    """A game whose board holds `fen`. Only the position matters in these tests."""
    game = Game()
    game.board.set_fen(fen)
    return game


# game.py


def test_new_game_starts_from_the_standard_position():
    game = Game()
    assert game.board.fen() == START_FEN
    assert game.uci_text() == ""
    assert game.repetitions() == 1


def test_push_and_uci_text():
    game = Game()
    play(game, "e2e4", "e7e5", "g1f3")
    assert game.uci_text() == "e2e4 e7e5 g1f3"
    assert game.board.fullmove_number == 2


def test_pop_restores_position_and_keys_through_capture_and_promotion():
    game = Game()
    play(game, "a2a4", "b7b5", "a4b5", "a7a6", "b5a6", "g8f6", "a6a7", "f6g8")
    before = game.board.fen()
    move = game.board.parse_uci("a7b8q")
    game.push(move)
    assert game.board.fen() != before
    assert game.pop() == move
    assert game.board.fen() == before
    assert game.uci_text().endswith("f6g8")


def test_repetitions_count_the_current_position():
    game = Game()
    play(game, "g1f3", "g8f6", "f3g1", "f6g8")
    assert game.repetitions() == 2
    play(game, "g1f3", "g8f6", "f3g1", "f6g8")
    assert game.repetitions() == 3
    game.pop()
    assert game.repetitions() == 2


def test_position_key_includes_turn_castling_and_usable_en_passant():
    # Black pawn on d4 can capture on e3, so the en passant square counts.
    a = position_key(Board("rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"))
    b = position_key(Board("rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"))
    c = position_key(Board("rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b Qkq - 0 1"))
    d = position_key(Board("rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"))
    assert len({a, b, c, d}) == 4
    assert len(a) == 67
    # No pawn can capture on e3: the square does not count.
    e = position_key(Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"))
    f = position_key(Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"))
    assert e == f


# rules.py


def test_game_continues_at_the_start():
    assert game_end(Game()) is None


def test_fools_mate_is_mate_black_wins():
    game = Game()
    play(game, "f2f3", "e7e5", "g2g4", "d8h4")
    assert game_end(game) == MATE_BLACK_WINS


def test_back_rank_mate_is_mate_white_wins():
    assert game_end(game_from("R5k1/5ppp/8/8/8/8/8/6K1 b - - 1 1")) == MATE_WHITE_WINS


def test_stalemate():
    assert game_end(game_from("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")) == STALEMATE


def test_insufficient_material_cases():
    assert game_end(game_from("4k3/8/8/8/8/8/8/4K3 w - - 0 1")) == MATERIAL
    assert game_end(game_from("4k3/8/8/8/8/8/8/4KN2 w - - 0 1")) == MATERIAL
    assert game_end(game_from("4k3/8/8/8/8/8/8/4KB2 w - - 0 1")) == MATERIAL
    # Bishops on c1 and f8 both stand on dark squares.
    assert game_end(game_from("4kb2/8/8/8/8/8/8/2B1K3 w - - 0 1")) == MATERIAL
    # Bishops on c1 (dark) and f1 (light): not a draw.
    assert game_end(game_from("4k3/8/8/8/8/8/8/2B1KB2 w - - 0 1")) is None
    # Two knights are not a forced draw. A pawn or a rook never is.
    assert game_end(game_from("4k3/8/8/8/8/8/8/3NKN2 w - - 0 1")) is None
    assert game_end(game_from("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")) is None
    assert game_end(game_from("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")) is None


def test_threefold_repetition_ends_at_the_third_occurrence():
    game = Game()
    play(game, "g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1")
    assert game_end(game) is None
    play(game, "f6g8")
    assert game_end(game) == REPETITION


def test_fifty_move_rule_at_100_plies():
    assert game_end(game_from("4k3/8/8/8/8/8/8/R3K3 w - - 99 80")) is None
    assert game_end(game_from("4k3/8/8/8/8/8/8/R3K3 w - - 100 80")) == FIFTY_MOVES


def test_mate_wins_over_fifty_moves():
    assert game_end(game_from("R5k1/5ppp/8/8/8/8/8/6K1 b - - 100 80")) == MATE_WHITE_WINS


def test_unusable_en_passant_square_does_not_prevent_repetition():
    # After 1.e4 no black pawn can capture on e3, so the position equals the
    # one after the knights return (FIDE 9.2.2).
    game = Game()
    play(game, "e2e4", "g8f6", "g1f3", "f6g8", "f3g1", "g8f6", "g1f3", "f6g8", "f3g1")
    assert game.repetitions() == 3
    assert game_end(game) == REPETITION


def test_usable_en_passant_square_makes_a_different_position():
    game = game_from("rnbqkbnr/ppp1pppp/8/8/3p4/8/PPPPPPPP/RNBQKBNR w KQkq - 0 3")
    play(game, "e2e4", "g8f6", "g1f3", "f6g8", "f3g1")
    assert game.repetitions() == 1
    play(game, "g8f6", "g1f3", "f6g8", "f3g1")
    assert game.repetitions() == 2


def test_pop_on_a_new_game_raises_and_changes_nothing():
    game = Game()
    try:
        game.pop()
        assert False, "pop on an empty game must raise"
    except IndexError:
        pass
    assert game.board.fen() == START_FEN
    assert game.uci_text() == ""
    assert game.repetitions() == 1


def test_long_game_fits_a_small_heap():
    # 300 plies of knight moves with no capture; MicroPython runs this with a 100 KB heap.
    game = Game()
    for i in range(300):
        play(game, ("g1f3", "g8f6", "f3g1", "f6g8")[i % 4])
    assert game.board.ply == 300
    assert game.repetitions() >= 3
