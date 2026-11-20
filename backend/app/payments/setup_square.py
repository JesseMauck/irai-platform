"""One-time Square setup.  python -m app.payments.setup_square [--locations]

Creates the subscription plan + variations from seed_data/plans.json prices and prints the environment
variables to set on the API service. Run with SQUARE_ACCESS_TOKEN and SQUARE_ENVIRONMENT set.
"""
from __future__ import annotations

import sys

from ..security import plans
from .square import SquareClient, SquareConfig


def main(argv: list[str]) -> None:
    cfg = SquareConfig.from_env()
    if not cfg.access_token:
        sys.exit("Set SQUARE_ACCESS_TOKEN (and SQUARE_ENVIRONMENT=sandbox|production) first")
    client = SquareClient(cfg)
    if "--locations" in argv or not cfg.location_id:
        for loc in client.list_locations():
            print(f"SQUARE_LOCATION_ID={loc['id']}   # {loc.get('name')} ({loc.get('status')})")
        if not cfg.location_id:
            return
    p = plans()
    prices = {f"{k}_monthly": int(p[k]["monthly"] * 100) for k in ("essential", "pro")}
    prices.update({f"{k}_annual": int(p[k]["annual"] * 100) for k in ("essential", "pro")})
    for key, vid in client.create_plans(prices).items():
        print(f"SQUARE_PLAN_{key.upper()}={vid}")


if __name__ == "__main__":
    main(sys.argv[1:])
