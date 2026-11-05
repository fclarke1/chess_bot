# Finds the legal moves that fit the occupancy maps seen since the last commit.
#
# The detector is built once per commit from the committed position. It
# stores the result map of every legal move, so each new occupancy map
# needs only byte compares. See ARCHITECTURE.md, "Move detection".

from controller import occupancy
from controller.board import BLACK, EMPTY, FLAG_EN_PASSANT, WHITE, move_flag, move_from, move_promotion, move_to


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
        self.current = self.committed
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
        """Record a new occupancy map and return the candidate moves."""
        self.current = occ_map
        if occ_map == self.committed:
            self.emptied.clear()
        else:
            for sq in occupancy.diff(occ_map, self.committed):
                if not occupancy.occupied(occ_map, sq):
                    self.emptied.add(sq)
        return self.candidates()

    def candidates(self):
        """Legal moves whose result map is the current map.

        A capture counts only when its capture square has read empty, so
        a lifted piece alone never matches a capture (capture order).
        """
        found = []
        for move, result, cap in self.moves:
            if result == self.current and (cap < 0 or cap in self.emptied):
                found.append(move)
        return found


def is_promotion_set(moves):
    """True when all moves are promotions of one pawn to one square."""
    if not moves or not move_promotion(moves[0]):
        return False
    frm, to = move_from(moves[0]), move_to(moves[0])
    for move in moves:
        if not move_promotion(move) or move_from(move) != frm or move_to(move) != to:
            return False
    return True
