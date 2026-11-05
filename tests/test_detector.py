# Scenario tests for the detector. Plain functions with plain asserts, so
# tests/micropython_run.py can run them in MicroPython as well as pytest.

from controller.board import Board, parse_square
from controller.detector import Detector, capture_square, is_promotion_set
from controller.occupancy import START_MAP, diff, from_board, from_text, occupied, to_text


def flip(occ_map, *names):
    """Lift a piece from an occupied square, or place one on an empty square."""
    occ_map = bytearray(occ_map)
    for name in names:
        sq = parse_square(name)
        occ_map[sq >> 3] ^= 1 << (sq & 7)
    return bytes(occ_map)


def ucis(board, moves):
    return sorted(board.uci(m) for m in moves)


def run(board, names):
    """Flip each square in turn and return the final candidates."""
    det = Detector(board)
    occ_map = det.committed
    result = []
    for name in names:
        occ_map = flip(occ_map, name)
        result = det.update(occ_map)
    return ucis(board, result)


# occupancy.py


def test_start_map_matches_start_board():
    assert from_board(Board()) == START_MAP
    assert occupied(START_MAP, parse_square("e2"))
    assert not occupied(START_MAP, parse_square("e4"))


def test_text_round_trip():
    text = to_text(START_MAP)
    assert text == "ffff00000000ffff"
    assert from_text(text) == START_MAP
    try:
        from_text("ffff")
        assert False, "short text must raise"
    except ValueError:
        pass


def test_diff_lists_changed_squares():
    after = flip(START_MAP, "e2", "e4")
    assert diff(START_MAP, after) == [parse_square("e2"), parse_square("e4")]
    assert diff(START_MAP, START_MAP) == []


# capture_square


def test_capture_square():
    board = Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    ep = board.parse_uci("e5d6")
    assert capture_square(board, ep) == parse_square("d5")
    board = Board("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1")
    assert capture_square(board, board.parse_uci("e4d5")) == parse_square("d5")
    assert capture_square(board, board.parse_uci("e4e5")) == -1


# Detector scenarios


def test_normal_move():
    board = Board()
    det = Detector(board)
    assert det.update(flip(START_MAP, "e2")) == []
    assert ucis(board, det.update(flip(START_MAP, "e2", "e4"))) == ["e2e4"]


def test_capture_with_capture_order():
    # White pawn e4, black pawns d5 and f5. The human plays exf5.
    board = Board("4k3/8/8/3p1p2/4P3/8/8/4K3 w - - 0 1")
    assert run(board, ["f5", "e4", "f5"]) == ["e4f5"]


def test_capture_without_removal_is_not_a_candidate():
    # The human lifts e4 and never lifts f5 (two pieces on f5, or placed at once).
    board = Board("4k3/8/8/3p1p2/4P3/8/8/4K3 w - - 0 1")
    assert run(board, ["e4"]) == []


def test_lifted_piece_alone_never_matches_a_capture():
    # Only one legal capture, Nxe5. A lift of f3 must not count as Nxe5.
    board = Board("4k3/8/8/4p3/8/5N2/8/4K3 w - - 0 1")
    det = Detector(board)
    assert det.update(flip(det.committed, "f3")) == []


def test_en_passant():
    board = Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    steps = ["e5", "d5", "d6"]
    assert run(board, steps) == ["e5d6"]
    # Without the pawn removal, the map matches no move.
    assert run(board, ["e5", "d6"]) == []


def test_castling_king_first():
    board = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    det = Detector(board)
    occ_map = det.committed
    seen = []
    for name in ("e1", "g1", "h1", "f1"):
        occ_map = flip(occ_map, name)
        seen.append(ucis(board, det.update(occ_map)))
    assert seen == [[], [], [], ["e1g1"]]


def test_castling_rook_first_matches_a_rook_move():
    # Documented limit: the human must move the king first.
    board = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert run(board, ["h1", "f1"]) == ["h1f1"]


def test_promotion_gives_four_candidates():
    board = Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    det = Detector(board)
    occ_map = flip(det.committed, "a7", "a8")
    moves = det.update(occ_map)
    assert ucis(board, moves) == ["a7a8b", "a7a8n", "a7a8q", "a7a8r"]
    assert is_promotion_set(moves)


def test_capture_promotion():
    board = Board("1n2k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    steps = ["b8", "a7", "b8"]
    assert run(board, steps) == ["a7b8b", "a7b8n", "a7b8q", "a7b8r"]


def test_is_promotion_set_rejects_empty_and_plain_moves():
    board = Board("1n2k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert not is_promotion_set([])
    assert not is_promotion_set([board.parse_uci("e1e2")])


def test_accidental_lift_then_put_back_clears_the_record():
    board = Board("4k3/8/8/3p1p2/4P3/8/8/4K3 w - - 0 1")
    det = Detector(board)
    start = det.committed
    det.update(flip(start, "d5"))
    assert det.emptied == {parse_square("d5")}
    det.update(start)
    assert det.emptied == set()
    # A clean exf5 after that is the only candidate.
    det.update(flip(start, "f5"))
    det.update(flip(start, "f5", "e4"))
    assert ucis(board, det.update(flip(start, "e4"))) == ["e4f5"]


def test_slide_over_an_empty_square_is_a_transient_candidate():
    # Ra1-a4 dragged over a2: the a2 map matches Ra2. The settle time in the
    # controller filters it. The transient must not enter the emptied record.
    board = Board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    det = Detector(board)
    start = det.committed
    assert ucis(board, det.update(flip(start, "a1", "a2"))) == ["a1a2"]
    assert ucis(board, det.update(flip(start, "a1", "a4"))) == ["a1a4"]
    assert det.emptied == {parse_square("a1")}


def test_two_captures_that_fit_give_two_candidates():
    # Bishop c4 can take a6 or f7. After Bxf7 the human lifts a6 to straighten it.
    board = Board("4k3/5p2/p7/8/2B5/8/8/4K3 w - - 0 1")
    steps = ["f7", "c4", "f7", "a6", "a6"]
    assert run(board, steps) == ["c4a6", "c4f7"]


def test_put_back_and_redo_after_unclear():
    board = Board("4k3/5p2/p7/8/2B5/8/8/4K3 w - - 0 1")
    det = Detector(board)
    start = det.committed
    for occ_map in (flip(start, "f7"), flip(start, "f7", "c4"), flip(start, "c4"),
                    flip(start, "c4", "a6"), flip(start, "c4")):
        found = det.update(occ_map)
    assert len(found) == 2
    # Put everything back: f7 gets the black pawn again, c4 the bishop.
    assert det.update(start) == []
    assert det.emptied == set()
    det.update(flip(start, "f7"))
    det.update(flip(start, "f7", "c4"))
    assert ucis(board, det.update(flip(start, "c4"))) == ["c4f7"]


def test_detector_leaves_the_board_unchanged():
    fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
    board = Board(fen)
    Detector(board)
    assert board.fen() == fen
