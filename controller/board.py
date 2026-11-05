# Position, legal move generator, FEN, UCI move text and SAN move text.
#
# Pure Python for CPython and MicroPython: no dataclasses, typing, enum or
# recursion. Squares are 0..63, a1 = 0, h1 = 7, a8 = 56.

from array import array

EMPTY = 0
PAWN = 1
KNIGHT = 2
BISHOP = 3
ROOK = 4
QUEEN = 5
KING = 6

WHITE = 0
BLACK = 8  # colour bit of a piece code

# Move = from | to << 6 | promotion piece type << 12 | flag << 15
FLAG_NORMAL = 0
FLAG_DOUBLE_PUSH = 1
FLAG_EN_PASSANT = 2
FLAG_CASTLE = 3

CASTLE_WK = 1
CASTLE_WQ = 2
CASTLE_BK = 4
CASTLE_BQ = 8

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

PIECE_LETTERS = " pnbrqk"
FILES = "abcdefgh"
RANKS = "12345678"
PROMOTION_TYPES = (QUEEN, ROOK, BISHOP, KNIGHT)


def move_from(move):
    return move & 63


def move_to(move):
    return (move >> 6) & 63


def move_promotion(move):
    return (move >> 12) & 7


def move_flag(move):
    return move >> 15


def make_move(frm, to, promotion=0, flag=FLAG_NORMAL):
    return frm | (to << 6) | (promotion << 12) | (flag << 15)


def square_name(sq):
    return FILES[sq & 7] + RANKS[sq >> 3]


def parse_square(text):
    if len(text) != 2 or text[0] not in FILES or text[1] not in RANKS:
        raise ValueError("bad square: " + text)
    return FILES.index(text[0]) + 8 * RANKS.index(text[1])


# Each table is one flat bytearray of target squares and one array of start
# offsets. Entry n covers squares[start[n]:start[n + 1]]. A tuple per square
# costs about 40 KB of heap in MicroPython; this layout costs about 3.5 KB.


def _step_targets(steps):
    squares = bytearray()
    start = array("H", [0])
    for sq in range(64):
        f, r = sq & 7, sq >> 3
        for df, dr in steps:
            if 0 <= f + df < 8 and 0 <= r + dr < 8:
                squares.append(sq + df + 8 * dr)
        start.append(len(squares))
    return squares, start


# Directions 0-3 are rook directions, 4-7 are bishop directions.
_DIRECTIONS = ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1))


def _rays():
    """Entry sq * 8 + d is the ray from square sq in direction d, nearest square first."""
    squares = bytearray()
    start = array("H", [0])
    for sq in range(64):
        for df, dr in _DIRECTIONS:
            f, r = (sq & 7) + df, (sq >> 3) + dr
            while 0 <= f < 8 and 0 <= r < 8:
                squares.append(f + 8 * r)
                f += df
                r += dr
            start.append(len(squares))
    return squares, start


KNIGHT_SQUARES, KNIGHT_START = _step_targets(((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)))
KING_SQUARES, KING_START = _step_targets(_DIRECTIONS)
RAY_SQUARES, RAY_START = _rays()

# Castling rights that stay after a move from or to each square.
CASTLE_KEEP = bytearray([15] * 64)
CASTLE_KEEP[0] = 15 & ~CASTLE_WQ
CASTLE_KEEP[4] = 15 & ~(CASTLE_WK | CASTLE_WQ)
CASTLE_KEEP[7] = 15 & ~CASTLE_WK
CASTLE_KEEP[56] = 15 & ~CASTLE_BQ
CASTLE_KEEP[60] = 15 & ~(CASTLE_BK | CASTLE_BQ)
CASTLE_KEEP[63] = 15 & ~CASTLE_BK


class Board:
    def __init__(self, fen=START_FEN, reserve_plies=0):
        """`reserve_plies` sizes the history array once, so a long game does not
        grow it in a fragmented MicroPython heap."""
        self.squares = bytearray(64)
        self.turn = WHITE
        self.castling = 0
        self.ep_square = -1
        self.halfmove_clock = 0
        self.fullmove_number = 1
        self.king_squares = [-1, -1]  # index 0 white, 1 black
        # Five ints per ply: move, captured piece, castling, ep_square,
        # halfmove_clock. One flat array, so a long game leaves no small
        # objects scattered through the MicroPython heap. pop() only
        # lowers ply; push() overwrites the slot.
        self.history = array("i", bytes(4 * 5 * reserve_plies))
        self.reserved = reserve_plies
        self.ply = 0
        self.set_fen(fen)

    # FEN

    def set_fen(self, fen):
        fields = fen.split()
        if len(fields) != 6:
            raise ValueError("FEN must have 6 fields: " + fen)
        rows = fields[0].split("/")
        if len(rows) != 8:
            raise ValueError("FEN must have 8 ranks: " + fen)
        squares = bytearray(64)
        kings = [-1, -1]
        for i in range(8):
            rank = 7 - i
            f = 0
            for ch in rows[i]:
                if ch in "12345678":
                    f += int(ch)
                    continue
                kind = PIECE_LETTERS.find(ch.lower())
                if kind < 1 or f > 7:
                    raise ValueError("bad FEN rank: " + rows[i])
                colour = WHITE if ch.isupper() else BLACK
                sq = f + 8 * rank
                squares[sq] = kind | colour
                if kind == KING:
                    kings[colour >> 3] = sq
                f += 1
            if f != 8:
                raise ValueError("bad FEN rank: " + rows[i])
        if kings[0] < 0 or kings[1] < 0:
            raise ValueError("FEN needs both kings: " + fen)
        if fields[1] not in ("w", "b"):
            raise ValueError("bad side to move: " + fields[1])
        castling = 0
        if fields[2] != "-":
            for ch in fields[2]:
                bit = "KQkq".find(ch)
                if bit < 0:
                    raise ValueError("bad castling field: " + fields[2])
                castling |= 1 << bit
        self.squares = squares
        self.king_squares = kings
        self.turn = WHITE if fields[1] == "w" else BLACK
        self.castling = castling
        self.ep_square = -1 if fields[3] == "-" else parse_square(fields[3])
        self.halfmove_clock = int(fields[4])
        self.fullmove_number = int(fields[5])
        self.ply = 0

    def fen(self):
        rows = []
        for rank in range(7, -1, -1):
            row = ""
            gap = 0
            for f in range(8):
                p = self.squares[f + 8 * rank]
                if p == EMPTY:
                    gap += 1
                    continue
                if gap:
                    row += str(gap)
                    gap = 0
                letter = PIECE_LETTERS[p & 7]
                row += letter if p & BLACK else letter.upper()
            if gap:
                row += str(gap)
            rows.append(row)
        castling = ""
        for bit in range(4):
            if self.castling & (1 << bit):
                castling += "KQkq"[bit]
        return " ".join((
            "/".join(rows),
            "w" if self.turn == WHITE else "b",
            castling or "-",
            "-" if self.ep_square < 0 else square_name(self.ep_square),
            str(self.halfmove_clock),
            str(self.fullmove_number),
        ))

    # Attacks and check

    def is_attacked(self, sq, by):
        """Return True if any piece of colour `by` attacks square `sq`."""
        b = self.squares
        knight = KNIGHT | by
        for i in range(KNIGHT_START[sq], KNIGHT_START[sq + 1]):
            if b[KNIGHT_SQUARES[i]] == knight:
                return True
        king = KING | by
        for i in range(KING_START[sq], KING_START[sq + 1]):
            if b[KING_SQUARES[i]] == king:
                return True
        pawn = PAWN | by
        f = sq & 7
        if by == WHITE:
            if f > 0 and sq >= 9 and b[sq - 9] == pawn:
                return True
            if f < 7 and sq >= 7 and b[sq - 7] == pawn:
                return True
        else:
            if f > 0 and sq <= 56 and b[sq + 7] == pawn:
                return True
            if f < 7 and sq <= 54 and b[sq + 9] == pawn:
                return True
        base = sq * 8
        queen = QUEEN | by
        for d in range(8):
            straight = ROOK | by if d < 4 else BISHOP | by
            for i in range(RAY_START[base + d], RAY_START[base + d + 1]):
                p = b[RAY_SQUARES[i]]
                if p:
                    if p == straight or p == queen:
                        return True
                    break
        return False

    def is_check(self):
        return self.is_attacked(self.king_squares[self.turn >> 3], self.turn ^ BLACK)

    # Move generation

    def pseudo_legal_moves(self):
        b = self.squares
        us = self.turn
        them = us ^ BLACK
        moves = []
        add = moves.append
        for sq in range(64):
            p = b[sq]
            if p == EMPTY or (p & BLACK) != us:
                continue
            kind = p & 7
            if kind == PAWN:
                self._pawn_moves(sq, moves)
            elif kind == KNIGHT or kind == KING:
                if kind == KNIGHT:
                    squares, start = KNIGHT_SQUARES, KNIGHT_START
                else:
                    squares, start = KING_SQUARES, KING_START
                for i in range(start[sq], start[sq + 1]):
                    t = squares[i]
                    q = b[t]
                    if q == EMPTY or (q & BLACK) == them:
                        add(sq | (t << 6))
            else:
                base = sq * 8
                first = 4 if kind == BISHOP else 0
                last = 4 if kind == ROOK else 8
                for d in range(first, last):
                    for i in range(RAY_START[base + d], RAY_START[base + d + 1]):
                        t = RAY_SQUARES[i]
                        q = b[t]
                        if q == EMPTY:
                            add(sq | (t << 6))
                            continue
                        if (q & BLACK) == them:
                            add(sq | (t << 6))
                        break
        self._castling_moves(moves)
        return moves

    def _pawn_moves(self, sq, moves):
        b = self.squares
        us = self.turn
        step = 8 if us == WHITE else -8
        start_rank = 1 if us == WHITE else 6
        last_rank = 7 if us == WHITE else 0
        rank = sq >> 3
        f = sq & 7
        to = sq + step
        if b[to] == EMPTY:
            if to >> 3 == last_rank:
                for kind in PROMOTION_TYPES:
                    moves.append(sq | (to << 6) | (kind << 12))
            else:
                moves.append(sq | (to << 6))
                if rank == start_rank and b[to + step] == EMPTY:
                    moves.append(sq | ((to + step) << 6) | (FLAG_DOUBLE_PUSH << 15))
        for df in (-1, 1):
            if not 0 <= f + df < 8:
                continue
            t = to + df
            q = b[t]
            if q != EMPTY and (q & BLACK) != us:
                if t >> 3 == last_rank:
                    for kind in PROMOTION_TYPES:
                        moves.append(sq | (t << 6) | (kind << 12))
                else:
                    moves.append(sq | (t << 6))
            elif t == self.ep_square:
                moves.append(sq | (t << 6) | (FLAG_EN_PASSANT << 15))

    def _castling_moves(self, moves):
        b = self.squares
        us = self.turn
        them = us ^ BLACK
        if us == WHITE:
            king_bit, queen_bit, e = CASTLE_WK, CASTLE_WQ, 4
        else:
            king_bit, queen_bit, e = CASTLE_BK, CASTLE_BQ, 60
        if not self.castling & (king_bit | queen_bit) or b[e] != KING | us:
            return
        if self.is_attacked(e, them):
            return
        rook = ROOK | us
        if (self.castling & king_bit and b[e + 3] == rook
                and b[e + 1] == EMPTY and b[e + 2] == EMPTY
                and not self.is_attacked(e + 1, them)
                and not self.is_attacked(e + 2, them)):
            moves.append(e | ((e + 2) << 6) | (FLAG_CASTLE << 15))
        if (self.castling & queen_bit and b[e - 4] == rook
                and b[e - 1] == EMPTY and b[e - 2] == EMPTY and b[e - 3] == EMPTY
                and not self.is_attacked(e - 1, them)
                and not self.is_attacked(e - 2, them)):
            moves.append(e | ((e - 2) << 6) | (FLAG_CASTLE << 15))

    def legal_moves(self):
        us = self.turn
        them = us ^ BLACK
        legal = []
        for move in self.pseudo_legal_moves():
            self.push(move)
            if not self.is_attacked(self.king_squares[us >> 3], them):
                legal.append(move)
            self.pop()
        return legal

    # Make and unmake

    def push(self, move):
        """Make `move`. The caller must give a move from legal_moves()."""
        b = self.squares
        frm = move & 63
        to = (move >> 6) & 63
        promotion = (move >> 12) & 7
        flag = move >> 15
        us = self.turn
        piece = b[frm]
        captured = b[to]
        if flag == FLAG_EN_PASSANT:
            cap_sq = to - 8 if us == WHITE else to + 8
            captured = b[cap_sq]
            b[cap_sq] = EMPTY
        i = self.ply * 5
        if self.ply >= self.reserved:
            self.reserved += 1
            self.history.extend((move, captured, self.castling, self.ep_square, self.halfmove_clock))
        else:
            self.history[i] = move
            self.history[i + 1] = captured
            self.history[i + 2] = self.castling
            self.history[i + 3] = self.ep_square
            self.history[i + 4] = self.halfmove_clock
        self.ply += 1
        b[to] = (promotion | us) if promotion else piece
        b[frm] = EMPTY
        if flag == FLAG_CASTLE:
            if to > frm:
                b[frm + 1] = b[frm + 3]
                b[frm + 3] = EMPTY
            else:
                b[frm - 1] = b[frm - 4]
                b[frm - 4] = EMPTY
        if piece & 7 == KING:
            self.king_squares[us >> 3] = to
        self.ep_square = (frm + to) >> 1 if flag == FLAG_DOUBLE_PUSH else -1
        self.castling &= CASTLE_KEEP[frm] & CASTLE_KEEP[to]
        if piece & 7 == PAWN or captured:
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1
        if us == BLACK:
            self.fullmove_number += 1
        self.turn = us ^ BLACK

    def pop(self):
        """Unmake the last move and return it. Raises IndexError with no move to unmake."""
        if self.ply == 0:
            raise IndexError("pop from a board with no moves")
        self.ply -= 1
        i = self.ply * 5
        move = self.history[i]
        captured = self.history[i + 1]
        castling = self.history[i + 2]
        ep_square = self.history[i + 3]
        halfmove_clock = self.history[i + 4]
        b = self.squares
        frm = move & 63
        to = (move >> 6) & 63
        promotion = (move >> 12) & 7
        flag = move >> 15
        us = self.turn ^ BLACK
        self.turn = us
        piece = (PAWN | us) if promotion else b[to]
        b[frm] = piece
        if flag == FLAG_EN_PASSANT:
            b[to] = EMPTY
            b[to - 8 if us == WHITE else to + 8] = captured
        else:
            b[to] = captured
        if flag == FLAG_CASTLE:
            if to > frm:
                b[frm + 3] = b[frm + 1]
                b[frm + 1] = EMPTY
            else:
                b[frm - 4] = b[frm - 1]
                b[frm - 1] = EMPTY
        if piece & 7 == KING:
            self.king_squares[us >> 3] = frm
        self.castling = castling
        self.ep_square = ep_square
        self.halfmove_clock = halfmove_clock
        if us == BLACK:
            self.fullmove_number -= 1
        return move

    # Move text

    def uci(self, move):
        text = square_name(move & 63) + square_name((move >> 6) & 63)
        promotion = (move >> 12) & 7
        if promotion:
            text += PIECE_LETTERS[promotion]
        return text

    def parse_uci(self, text):
        """Return the legal move for UCI text such as 'e2e4' or 'b7b8q', or None."""
        for move in self.legal_moves():
            if self.uci(move) == text:
                return move
        return None

    def san(self, move):
        """Return the SAN text of a legal move, for example 'Nbd2', 'exd5' or 'O-O+'."""
        frm = move & 63
        to = (move >> 6) & 63
        promotion = (move >> 12) & 7
        flag = move >> 15
        kind = self.squares[frm] & 7
        if flag == FLAG_CASTLE:
            text = "O-O" if to > frm else "O-O-O"
        else:
            capture = self.squares[to] != EMPTY or flag == FLAG_EN_PASSANT
            if kind == PAWN:
                text = FILES[frm & 7] + "x" if capture else ""
            else:
                text = PIECE_LETTERS[kind].upper() + self._disambiguation(move, kind)
                if capture:
                    text += "x"
            text += square_name(to)
            if promotion:
                text += "=" + PIECE_LETTERS[promotion].upper()
        self.push(move)
        if self.is_check():
            text += "#" if not self.legal_moves() else "+"
        self.pop()
        return text

    def _disambiguation(self, move, kind):
        frm = move & 63
        to = (move >> 6) & 63
        others = []
        for other in self.legal_moves():
            o_frm = other & 63
            if o_frm != frm and (other >> 6) & 63 == to and self.squares[o_frm] & 7 == kind:
                others.append(o_frm)
        if not others:
            return ""
        same_file = False
        same_rank = False
        for o_frm in others:
            if o_frm & 7 == frm & 7:
                same_file = True
            if o_frm >> 3 == frm >> 3:
                same_rank = True
        if not same_file:
            return FILES[frm & 7]
        if not same_rank:
            return RANKS[frm >> 3]
        return square_name(frm)
