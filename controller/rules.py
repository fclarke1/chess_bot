# Game end checks. The controller ends a draw at once, with no claim.

from controller.board import BISHOP, BLACK, EMPTY, KING, KNIGHT, WHITE

MATE_WHITE_WINS = "mate_white_wins"
MATE_BLACK_WINS = "mate_black_wins"
STALEMATE = "stalemate"
MATERIAL = "insufficient_material"
REPETITION = "threefold_repetition"
FIFTY_MOVES = "fifty_moves"


def game_end(game):
    """Return the game end code for the committed position, or None if the game continues."""
    board = game.board
    if not board.legal_moves():
        if not board.is_check():
            return STALEMATE
        return MATE_BLACK_WINS if board.turn == WHITE else MATE_WHITE_WINS
    if insufficient_material(board):
        return MATERIAL
    if game.repetitions() >= 3:
        return REPETITION
    if board.halfmove_clock >= 100:
        return FIFTY_MOVES
    return None


def insufficient_material(board):
    """K v K, K+N v K, K+B v K, or only bishops that all stand on one square colour."""
    knights = 0
    bishops = 0
    bishop_colours = set()
    for sq in range(64):
        piece = board.squares[sq]
        kind = piece & 7
        if kind == EMPTY or kind == KING:
            continue
        if kind == KNIGHT:
            knights += 1
        elif kind == BISHOP:
            bishops += 1
            bishop_colours.add((sq + (sq >> 3)) & 1)
        else:
            return False
    if knights + bishops <= 1:
        return True
    return knights == 0 and len(bishop_colours) == 1
