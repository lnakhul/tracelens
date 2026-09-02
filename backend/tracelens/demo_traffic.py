"""Generate deterministic traffic for the TraceLens demo environment."""

from __future__ import annotations

import asyncio

import httpx


async def seed_traffic() -> None:
    """Wait for TraceLens, then create representative successful and failed traces."""

    async with httpx.AsyncClient(base_url="http://tracelens:9000", timeout=5) as client:
        for _ in range(40):
            try:
                response = await client.get("/api/health")
                response.raise_for_status()
                break
            except httpx.HTTPError:
                await asyncio.sleep(0.25)
        else:
            raise RuntimeError("TraceLens did not become available")

        await client.get("/users/42")
        for _ in range(5):
            await client.get("/reports/daily")
        await client.get("/reports/daily?slow=true")
        await client.post(
            "/orders",
            json={"customer_id": "cus_demo_001", "product_id": "prod_keyboard"},
        )
        await client.post("/orders", json={"product_id": "prod_keyboard"})


def main() -> None:
    """Run the demo traffic seeder."""

    asyncio.run(seed_traffic())


if __name__ == "__main__":
    main()