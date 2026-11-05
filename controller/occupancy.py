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
    return bytes.fromhex(text)


def to_text(occ_map):
    return occ_map.hex()


def diff(a, b):
    """Return the squares where maps a and b differ."""
    squares = []
    for sq in range(64):
        if occupied(a, sq) != occupied(b, sq):
            squares.append(sq)
    return squares
