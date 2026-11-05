# Scenario tests for the detector. Plain functions with plain asserts, so
# tests/micropython_run.py can run them in MicroPython as well as pytest.

from controller import occupancy
from controller.board import Board, parse_square
from controller.detector import Detector, capture_square, is_promotion_set
from controller.occupancy import START_MAP, diff, from_board, from_text, occupied, to_text


def lift(occ_map, *names):
    occ_map = bytearray(occ_map)
    for name in names:
        sq = parse_square(name)
        occ_map[sq >> 3] &= ~(1 << (sq & 7))
    return bytes(occ_map)


def place(occ_map, *names):
    occ_map = bytearray(occ_map)
    for name in names:
        sq = parse_square(name)
        occ_map[sq >> 3] |= 1 << (sq & 7)
    return bytes(occ_map)


def ucis(board, moves):
    return sorted(board.uci(m) for m in moves)


def run(board, steps):
    """Feed each step (a list of lifts or places) and return the final candidates.

    A step is ("lift", "e2") or ("place", "e4").
    """
    det = Detector(board)
    occ_map = det.committed
    result = []
    for action, name in steps:
        occ_map = lift(occ_map, name) if action == "lift" else place(occ_map, name)
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
    after = place(lift(START_MAP, "e2"), "e4")
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
    assert det.update(lift(START_MAP, "e2")) == []
    assert ucis(board, det.update(place(lift(START_MAP, "e2"), "e4"))) == ["e2e4"]


def test_capture_with_capture_order():
    # White pawn e4, black pawns d5 and f5. The human plays exf5.
    board = Board("4k3/8/8/3p1p2/4P3/8/8/4K3 w - - 0 1")
    assert run(board, [("lift", "f5"), ("lift", "e4"), ("place", "f5")]) == ["e4f5"]


def test_capture_without_removal_is_not_a_candidate():
    # The human lifts e4 and never lifts f5 (two pieces on f5, or placed at once).
    board = Board("4k3/8/8/3p1p2/4P3/8/8/4K3 w - - 0 1")
    assert run(board, [("lift", "e4")]) == []


def test_lifted_piece_alone_never_matches_a_capture():
    # Only one legal capture, Nxe5. A lift of f3 must not count as Nxe5.
    board = Board("4k3/8/8/4p3/8/5N2/8/4K3 w - - 0 1")
    det = Detector(board)
    assert det.update(lift(det.committed, "f3")) == []


def test_en_passant():
    board = Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    steps = [("lift", "e5"), ("lift", "d5"), ("place", "d6")]
    assert run(board, steps) == ["e5d6"]
    # Without the pawn removal, the map matches no move.
    assert run(board, [("lift", "e5"), ("place", "d6")]) == []


def test_castling_king_first():
    board = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    steps = [("lift", "e1"), ("place", "g1"), ("lift", "h1"), ("place", "f1")]
    det = Detector(board)
    occ_map = det.committed
    seen = []
    for action, name in steps:
        occ_map = lift(occ_map, name) if action == "lift" else place(occ_map, name)
        seen.append(ucis(board, det.update(occ_map)))
    assert seen == [[], [], [], ["e1g1"]]


def test_castling_rook_first_matches_a_rook_move():
    # Documented limit: the human must move the king first.
    board = Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert run(board, [("lift", "h1"), ("place", "f1")]) == ["h1f1"]


def test_promotion_gives_four_candidates():
    board = Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    det = Detector(board)
    occ_map = place(lift(det.committed, "a7"), "a8")
    moves = det.update(occ_map)
    assert ucis(board, moves) == ["a7a8b", "a7a8n", "a7a8q", "a7a8r"]
    assert is_promotion_set(moves)


def test_capture_promotion():
    board = Board("1n2k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    steps = [("lift", "b8"), ("lift", "a7"), ("place", "b8")]
    assert run(board, steps) == ["a7b8b", "a7b8n", "a7b8q", "a7b8r"]


def test_is_promotion_set_rejects_mixed_moves():
    board = Board("1n2k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert not is_promotion_set([])
    assert not is_promotion_set([board.parse_uci("e1e2")])
    assert not is_promotion_set([board.parse_uci("a7a8q"), board.parse_uci("a7b8q")])


def test_accidental_lift_then_put_back_clears_the_record():
    board = Board("4k3/8/8/3p1p2/4P3/8/8/4K3 w - - 0 1")
    det = Detector(board)
    start = det.committed
    det.update(lift(start, "d5"))
    assert det.emptied == {parse_square("d5")}
    det.update(start)
    assert det.emptied == set()
    # A clean exf5 after that is the only candidate.
    det.update(lift(start, "f5"))
    det.update(lift(start, "f5", "e4"))
    assert ucis(board, det.update(place(lift(start, "e4"), "f5"))) == ["e4f5"]


def test_slide_over_an_empty_square_is_a_transient_candidate():
    # Ra1-a4 dragged over a2: the a2 map matches Ra2. The settle time in the
    # controller filters it. The transient must not enter the emptied record.
    board = Board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    det = Detector(board)
    start = det.committed
    assert ucis(board, det.update(place(lift(start, "a1"), "a2"))) == ["a1a2"]
    assert ucis(board, det.update(place(lift(start, "a1"), "a4"))) == ["a1a4"]
    assert det.emptied == {parse_square("a1")}


def test_two_captures_that_fit_give_two_candidates():
    # Bishop c4 can take a6 or f7. After Bxf7 the human lifts a6 to straighten it.
    board = Board("4k3/5p2/p7/8/2B5/8/8/4K3 w - - 0 1")
    steps = [("lift", "f7"), ("lift", "c4"), ("place", "f7"), ("lift", "a6"), ("place", "a6")]
    assert run(board, steps) == ["c4a6", "c4f7"]


def test_put_back_and_redo_after_unclear():
    board = Board("4k3/5p2/p7/8/2B5/8/8/4K3 w - - 0 1")
    det = Detector(board)
    start = det.committed
    for occ_map in (lift(start, "f7"), lift(start, "f7", "c4"), lift(start, "c4"),
                    lift(start, "c4", "a6"), lift(start, "c4")):
        det.update(occ_map)
    assert len(det.candidates()) == 2
    # Put everything back: f7 gets the black pawn again, c4 the bishop.
    assert det.update(start) == []
    assert det.emptied == set()
    det.update(lift(start, "f7"))
    det.update(lift(start, "f7", "c4"))
    assert ucis(board, det.update(lift(start, "c4"))) == ["c4f7"]


def test_detector_leaves_the_board_unchanged():
    fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
    board = Board(fen)
    Detector(board)
    assert board.fen() == fen
