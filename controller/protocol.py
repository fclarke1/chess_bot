# The engine request and the engine reply. See ARCHITECTURE.md, "Engine server".


def build_request(request_id, game, settings):
    return {
        "request_id": request_id,
        "start": "startpos",
        "moves": game.uci_text(),
        "personality": settings["personality"],
        "strength": settings["strength"],
        "movetime_ms": settings["think_s"] * 1000,
    }


def parse_reply(board, text):
    """Return the legal move for the reply text, or None when the reply is not a legal move."""
    if not isinstance(text, str):
        return None
    return board.parse_uci(text)
