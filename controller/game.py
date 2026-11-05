# The game: the committed position, the move list, and the position keys
# for threefold repetition. Undo is pop(); the controller decides how many
# plies to pop.

from controller.board import Board


def position_key(board):
    """67 bytes that identify a position for repetition: squares, turn, castling, en passant."""
    return bytes(board.squares) + bytes((board.turn, board.castling, board.ep_square & 0xFF))


class Game:
    def __init__(self):
        self.board = Board()
        self.moves = []
        self.keys = [position_key(self.board)]

    def push(self, move):
        self.board.push(move)
        self.moves.append(move)
        self.keys.append(position_key(self.board))

    def pop(self):
        """Undo one ply and return the move."""
        self.keys.pop()
        self.board.pop()
        return self.moves.pop()

    def uci_moves(self):
        """The move list in UCI text, for the engine request and the saved game."""
        board = Board()
        texts = []
        for move in self.moves:
            texts.append(board.uci(move))
            board.push(move)
        return texts

    def repetitions(self):
        """How many times the current position has occurred, including now."""
        return self.keys.count(self.keys[-1])
