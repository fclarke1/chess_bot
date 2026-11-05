# Occupancy map: 8 bytes, one per rank, rank 1 first. Bit 0 of a byte is
# file a. A map is a `bytes` value, so two maps compare with ==.

from controller.board import EMPTY

START_MAP = bytes((0xFF, 0xFF, 0, 0, 0, 0, 0xFF, 0xFF))


def occupied(occ_map, sq):
    return (occ_map[sq >> 3] >> (sq & 7)) & 1


def from_board(board):
    occ_map = bytearray(8)
    squares = board.squares
    for sq in range(64):
        if squares[sq] != EMPTY:
            occ_map[sq >> 3] |= 1 << (sq & 7)
    return bytes(occ_map)


def from_text(text):
    """Parse 16 hex characters, as written in the event log."""
    if len(text) != 16:
        raise ValueError("occupancy text must have 16 hex characters: " + text)
    return bytes(int(text[i:i + 2], 16) for i in range(0, 16, 2))


def to_text(occ_map):
    return "".join("%02x" % b for b in occ_map)


def diff(a, b):
    """Return the squares where maps a and b differ."""
    squares = []
    for sq in range(64):
        if occupied(a, sq) != occupied(b, sq):
            squares.append(sq)
    return squares
