"""
Test captured Avito session
"""
import asyncio
import aiohttp
import json

async def test_session():
    # Load session
    with open("avito_session.json", "r") as f:
        session = json.load(f)

    sessid = session["sessid"]
    device_id = session["device_id"]
    user_id = session["user_id"]

    print(f"Testing session for user: {user_id}")
    print(f"Device ID: {device_id}")
    print(f"Session expires at: {session['expires_at']}")
    print()

    headers = {
        "User-Agent": "AVITO 215.1 (OnePlus LE2115; Android 14; ru)",
        "X-App": "avito",
        "X-Platform": "android",
        "X-AppVersion": "215.1",
        "X-Session": sessid,
        "X-DeviceId": device_id,
        "Cookie": f"sessid={sessid}",
        "Accept": "application/json",
    }

    async with aiohttp.ClientSession() as http:
        # Test 1: Profile info
        print("=== Test 1: Profile Info ===")
        async with http.get(
            "https://app.avito.ru/api/1/profile/info",
            headers=headers
        ) as resp:
            print(f"Status: {resp.status}")
            data = await resp.json()
            print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
            print()

        # Test 2: Messenger channels
        print("=== Test 2: Messenger Channels ===")
        async with http.get(
            "https://api.avito.ru/messenger/v2/channels",
            headers=headers,
            params={"limit": 5}
        ) as resp:
            print(f"Status: {resp.status}")
            data = await resp.json()
            print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
            print()

        # Test 3: User info
        print("=== Test 3: User Info ===")
        async with http.get(
            f"https://api.avito.ru/users/{user_id}",
            headers=headers
        ) as resp:
            print(f"Status: {resp.status}")
            data = await resp.json()
            print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])

if __name__ == "__main__":
    asyncio.run(test_session())
