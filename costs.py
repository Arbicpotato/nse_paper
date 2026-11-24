"""Zerodha-style intraday equity charges. Verify against the broker's calculator."""


def charges(buy, sell, qty):
    b, s = buy * qty, sell * qty
    brokerage = min(20, 0.0003 * b) + min(20, 0.0003 * s)
    stt = 0.00025 * s                      # sell side only
    exchange = 0.0000322 * (b + s)
    sebi = 1e-6 * (b + s)                  # Rs 10 per crore
    stamp = 0.00003 * b                    # buy side only
    gst = 0.18 * (brokerage + exchange + sebi)
    return brokerage + stt + exchange + sebi + stamp + gst


def round_trip(entry, exit_, qty, side):
    """side: +1 long (buy first), -1 short (sell first)."""
    buy, sell = (entry, exit_) if side > 0 else (exit_, entry)
    return round(charges(buy, sell, qty), 2)
