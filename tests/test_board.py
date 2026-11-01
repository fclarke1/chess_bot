import pytest

from controller.board import START_FEN, Board
from tests.perft_data import (
    KIWIPETE,
    PERFT_CASES,
    POSITION_3,
    POSITION_4,
    POSITION_5,
    POSITION_6,
    SLOW_PERFT_CASES,
    perft,
)


@pytest.mark.parametrize("fen,depth,expected", PERFT_CASES)
def test_perft(fen, depth, expected):
    board = Board(fen)
    assert perft(board, depth) == expected
    assert board.fen() == fen


@pytest.mark.slow
@pytest.mark.parametrize("fen,depth,expected", SLOW_PERFT_CASES)
def test_perft_slow(fen, depth, expected):
    assert perft(Board(fen), depth) == expected


@pytest.mark.parametrize("fen", [START_FEN, KIWIPETE, POSITION_3, POSITION_4, POSITION_5, POSITION_6])
def test_fen_round_trip(fen):
    assert Board(fen).fen() == fen


@pytest.mark.parametrize("fen", [
    "",
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0",
    "rnbqkbnr/pppppppp/9/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQ1BNR w KQkq - 0 1",
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR x KQkq - 0 1",
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkx - 0 1",
])
def test_bad_fen_raises(fen):
    with pytest.raises(ValueError):
        Board(fen)


def play(board, *uci_moves):
    for text in uci_moves:
        move = board.parse_uci(text)
        assert move is not None, text
        board.push(move)


def test_push_pop_restores_position():
    board = Board(KIWIPETE)
    for move in board.legal_moves():
        board.push(move)
        board.pop()
        assert board.fen() == KIWIPETE


def test_move_updates_clocks_castling_and_en_passant():
    board = Board()
    play(board, "e2e4")
    assert board.fen() == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    play(board, "g8f6", "e1e2")
    assert board.fen() == "rnbqkb1r/pppppppp/5n2/8/4P3/8/PPPPKPPP/RNBQ1BNR b kq - 2 2"


def test_parse_uci_rejects_illegal_moves():
    board = Board()
    assert board.parse_uci("e2e5") is None
    assert board.parse_uci("e7e5") is None
    assert board.parse_uci("junk") is None
    assert board.parse_uci("e2e4") is not None


@pytest.mark.parametrize("fen,uci,san", [
    (START_FEN, "g1f3", "Nf3"),
    (START_FEN, "e2e4", "e4"),
    # Two knights reach d2: file disambiguation.
    ("4k3/8/8/8/8/5N2/8/1N2K3 w - - 0 1", "b1d2", "Nbd2"),
    # Two rooks on the a-file reach a4: rank disambiguation.
    ("4k3/R7/8/8/8/8/R7/4K3 w - - 0 1", "a2a4", "R2a4"),
    # Queens on g5 (same rank) and c3 (same file) also reach e5: square disambiguation.
    ("4k3/8/8/2Q3Q1/8/2Q5/8/4K3 w - - 0 1", "c5e5", "Qc5e5+"),
    ("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1", "e4d5", "exd5"),
    ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "e5d6", "exd6"),
    ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1", "O-O"),
    ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1c1", "O-O-O"),
    ("1n2k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7b8q", "axb8=Q+"),
    ("1n2k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7a8n", "a8=N"),
    # Back-rank mate.
    ("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", "a1a8", "Ra8#"),
])
def test_san(fen, uci, san):
    board = Board(fen)
    move = board.parse_uci(uci)
    assert move is not None
    assert board.san(move) == san
    assert board.fen() == fen


def test_checkmate_and_stalemate_have_no_legal_moves():
    mate = Board("R5k1/5ppp/8/8/8/8/8/6K1 b - - 1 1")
    assert mate.is_check() and mate.legal_moves() == []
    stalemate = Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert not stalemate.is_check() and stalemate.legal_moves() == []


def test_castling_blocked_through_attacked_square():
    # The black rook on f8 attacks f1, so white cannot castle king side.
    board = Board("4kr2/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    texts = [board.uci(m) for m in board.legal_moves()]
    assert "e1g1" not in texts
    assert "e1c1" in texts
