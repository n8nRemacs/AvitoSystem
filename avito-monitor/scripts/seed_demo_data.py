"""Seed a demo SearchProfile for the first owner. Idempotent."""
import asyncio

from sqlalchemy import select

from app.db.base import dispose_engine, get_sessionmaker
from app.db.models import SearchProfile, User
from app.schemas.search_profile import SearchProfileCreate
from app.services.search_profiles import create_profile

DEMO_PROFILES = [
    SearchProfileCreate(
        name="iPhone 12 Pro Max до 13.5K",
        avito_search_url=(
            "https://www.avito.ru/moskva/telefony/mobilnye_telefony/"
            "apple-ASgBAgICAUSwwQ2OWg?pmin=11000&pmax=13500&s=104"
        ),
        custom_criteria=(
            "Аккумулятор не ниже 85%, без серьёзных царапин, не реплика. "
            "Принимаются мелкие потёртости и сколы краски."
        ),
        allowed_conditions=["working"],
        analyze_photos=True,
        poll_interval_minutes=5,
        notification_channels=["telegram"],
    ),
    SearchProfileCreate(
        name="MacBook Air M2 до 75K",
        avito_search_url=(
            "https://www.avito.ru/moskva/noutbuki/"
            "apple_macbook-ABCDEFGH12345xyz?pmin=60000&pmax=75000"
        ),
        allowed_conditions=["working"],
        poll_interval_minutes=15,
    ),
    SearchProfileCreate(
        name="AirPods Pro 2 до 12K",
        avito_search_url=(
            "https://www.avito.ru/moskva/audio_i_video/"
            "apple_airpods_pro_2-AAAAAAAAAAA12345?pmin=8000&pmax=12000"
        ),
        is_active=False,
        allowed_conditions=["working"],
        poll_interval_minutes=30,
    ),
]


async def main() -> None:
    sessionmaker = get_sessionmaker()
    try:
        async with sessionmaker() as session:
            user = (await session.execute(
                select(User).order_by(User.created_at).limit(1)
            )).scalar_one_or_none()
            if user is None:
                print("Нет ни одного юзера — создай админа: python -m scripts.create_admin owner <pass>")
                return
            existing = (await session.execute(
                select(SearchProfile).where(SearchProfile.user_id == user.id)
            )).scalars().all()
            existing_names = {p.name for p in existing}
            created = 0
            for data in DEMO_PROFILES:
                if data.name in existing_names:
                    print(f"= '{data.name}' уже существует, skip")
                    continue
                p = await create_profile(session, user.id, data)
                created += 1
                print(f"+ '{p.name}' создан, brand={p.parsed_brand}, "
                      f"alert={p.alert_min_price}–{p.alert_max_price}, "
                      f"search={p.search_min_price}–{p.search_max_price}")
            await session.commit()
            print(f"\nИтого создано: {created}")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
