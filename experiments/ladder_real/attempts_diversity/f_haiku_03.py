def total_cents(prices):
    total = 0
    for p in prices:
        total += to_cents(p)
    return total
