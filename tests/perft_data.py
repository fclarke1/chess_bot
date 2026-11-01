# Perft data and helper, shared by the pytest tests and the MicroPython runner.
# No pytest import here, so MicroPython can load this module.

from controller.board import START_FEN

# Values from https://www.chessprogramming.org/Perft_Results
KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
POSITION_3 = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
POSITION_4 = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"
POSITION_5 = "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"
POSITION_6 = "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10"


def perft(board, depth):
    moves = board.legal_moves()
    if depth == 1:
        return len(moves)
    total = 0
    for move in moves:
        board.push(move)
        total += perft(board, depth - 1)
        board.pop()
    return total


PERFT_CASES = [
    (START_FEN, 1, 20),
    (START_FEN, 2, 400),
    (START_FEN, 3, 8902),
    (START_FEN, 4, 197281),
    (KIWIPETE, 1, 48),
    (KIWIPETE, 2, 2039),
    (KIWIPETE, 3, 97862),
    (POSITION_3, 1, 14),
    (POSITION_3, 2, 191),
    (POSITION_3, 3, 2812),
    (POSITION_3, 4, 43238),
    (POSITION_4, 1, 6),
    (POSITION_4, 2, 264),
    (POSITION_4, 3, 9467),
    (POSITION_5, 1, 44),
    (POSITION_5, 2, 1486),
    (POSITION_5, 3, 62379),
    (POSITION_6, 1, 46),
    (POSITION_6, 2, 2079),
    (POSITION_6, 3, 89890),
]

SLOW_PERFT_CASES = [
    (KIWIPETE, 4, 4085603),
    (POSITION_3, 5, 674624),
    (POSITION_4, 4, 422333),
    (POSITION_5, 4, 2103487),
    (POSITION_6, 4, 3894594),
]
