# The game: the committed position and the move list. Undo is pop(); the
# controller decides how many plies to pop. Every game starts from the
# standard position; a resume replays the saved move list with push().

from controller.board import PAWN, WHITE, Board


def position_key(board):
    """67 bytes that identify a position for repetition: squares, turn, castling, en passant.

    The en passant square counts only when a pawn stands ready to capture
    on it (FIDE 9.2.2). A pin can still make that capture illegal; the key
    ignores that rare case.
    """
    ep = board.ep_square
    if ep >= 0:
        pawn = PAWN | board.turn
        row = ep - 8 if board.turn == WHITE else ep + 8
        left = ep & 7 > 0 and board.squares[row - 1] == pawn
        right = ep & 7 < 7 and board.squares[row + 1] == pawn
        if not (left or right):
            ep = -1
    return bytes(board.squares) + bytes((board.turn, board.castling, ep & 0xFF))


class Game:
    def __init__(self):
        self.board = Board()

    def push(self, move):
        self.board.push(move)

    def pop(self):
        """Undo one ply and return the move. Raises IndexError on a new game."""
        return self.board.pop()

    def uci_moves(self):
        """The move list in UCI text, for the engine request and the saved game."""
        board = self.board
        return [board.uci(board.history[5 * i]) for i in range(board.ply)]

    def repetitions(self):
        """How many times the current position has occurred, including now.

        Walks back through the plies since the last capture or pawn move,
        because no earlier position can equal the current one. This keeps
        no list of keys, so a long game does not grow the heap.
        """
        board = self.board
        key = position_key(board)
        count = 1
        popped = []
        for _ in range(min(board.halfmove_clock, board.ply)):
            popped.append(board.pop())
            if position_key(board) == key:
                count += 1
        while popped:
            board.push(popped.pop())
        return count
