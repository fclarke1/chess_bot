# Finds the legal moves that fit the occupancy maps seen since the last commit.
#
# The detector is built once per commit from the committed position. It
# stores the result map of every legal move, so each new occupancy map
# needs only byte compares. See ARCHITECTURE.md, "Move detection".

from controller import occupancy
from controller.board import EMPTY, FLAG_EN_PASSANT, WHITE, move_flag, move_promotion, move_to


def capture_square(board, move):
    """Return the square of the captured piece, or -1 when the move captures nothing."""
    to = move_to(move)
    if move_flag(move) == FLAG_EN_PASSANT:
        return to - 8 if board.turn == WHITE else to + 8
    if board.squares[to] != EMPTY:
        return to
    return -1


class Detector:
    def __init__(self, board):
        """`board` is the committed position. The detector does not keep it."""
        self.committed = occupancy.from_board(board)
        # Squares that were occupied in the committed map and have read
        # empty since the last time the map equalled the committed map.
        self.emptied = set()
        # (move, result map, capture square) for each legal move.
        self.moves = []
        for move in board.legal_moves():
            cap = capture_square(board, move)
            board.push(move)
            self.moves.append((move, occupancy.from_board(board), cap))
            board.pop()

    def update(self, occ_map):
        """Record a new map and return the legal moves whose result map equals it.

        A capture counts only when its capture square has read empty, so a
        lifted piece alone never matches a capture (capture order).
        """
        if occ_map == self.committed:
            self.emptied.clear()
        else:
            for sq in range(64):
                if occupancy.occupied(self.committed, sq) and not occupancy.occupied(occ_map, sq):
                    self.emptied.add(sq)
        found = []
        for move, result, cap in self.moves:
            if result == occ_map and (cap < 0 or cap in self.emptied):
                found.append(move)
        return found


def is_promotion_set(moves):
    """True when the candidates are promotions.

    Candidates share one result map, so they move one pawn to one square.
    """
    return bool(moves) and move_promotion(moves[0]) != 0
