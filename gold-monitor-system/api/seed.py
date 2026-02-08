"""Seed script to create initial admin user, example sources, and default settings."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://goldmon:goldmon_secret@localhost:5432/goldmonitor"
)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@goldmonitor.ir")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


async def seed():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Create admin user
        result = await session.execute(
            text("SELECT id FROM admin_users WHERE email = :email"),
            {"email": ADMIN_EMAIL}
        )
        if result.scalar() is None:
            admin_id = str(uuid.uuid4())
            password_hash = pwd_context.hash(ADMIN_PASSWORD)
            await session.execute(
                text("""
                    INSERT INTO admin_users (id, email, password_hash, role, created_at)
                    VALUES (:id, :email, :pw, 'admin', NOW())
                """),
                {"id": admin_id, "email": ADMIN_EMAIL, "pw": password_hash}
            )
            print(f"[SEED] Admin user created: {ADMIN_EMAIL}")
        else:
            print(f"[SEED] Admin user already exists: {ADMIN_EMAIL}")

        # 2. Seed default settings
        default_settings = {
            "openrouter_model": "anthropic/claude-sonnet-4",
            "temperature": 0.3,
            "max_tokens": 1000,
            "enable_llm": False,
            "dedupe_window_hours": 6,
        }
        for key, value in default_settings.items():
            result = await session.execute(
                text("SELECT key FROM settings WHERE key = :key"),
                {"key": key}
            )
            if result.scalar() is None:
                import json
                await session.execute(
                    text("INSERT INTO settings (key, value, updated_at) VALUES (:key, :value, NOW())"),
                    {"key": key, "value": json.dumps(value)}
                )
                print(f"[SEED] Setting created: {key} = {value}")

        # 3. Create example sources
        example_sources = [
            {
                "id": str(uuid.uuid4()),
                "name": "Reuters Gold News (RSS)",
                "type": "rss",
                "base_url": "https://www.reuters.com",
                "endpoints": ["/markets/commodities/gold"],
                "method": "GET",
                "headers": {},
                "auth_config": {},
                "parser": "rss_parser",
                "enabled": True,
                "poll_interval_seconds": 120,
                "categories": ["global_gold"],
                "rule_bindings": ["GLOB_RATE_DECISION", "GLOB_GEOPOL_RISK", "GLOB_US_MACRO_DATA", "GLOB_DOLLAR_DXY"],
                "reliability_score": 0.9,
                "notes": "Reuters gold market news feed",
            },
            {
                "id": str(uuid.uuid4()),
                "name": "تجارت‌نیوز (HTML)",
                "type": "html",
                "base_url": "https://tejaratnews.com",
                "endpoints": ["/gold", "/currency"],
                "method": "GET",
                "headers": {},
                "auth_config": {},
                "parser": "html_parser",
                "enabled": True,
                "poll_interval_seconds": 180,
                "categories": ["iran_gold", "coin"],
                "rule_bindings": ["IR_FX_USD", "IR_GOV_FX_POLICY", "COIN_PREMIUM_BUBBLE"],
                "reliability_score": 0.7,
                "notes": "اخبار طلا و ارز ایران",
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Kitco Gold News (RSS)",
                "type": "rss",
                "base_url": "https://www.kitco.com",
                "endpoints": ["/feed/rss/news/gold"],
                "method": "GET",
                "headers": {},
                "auth_config": {},
                "parser": "rss_parser",
                "enabled": True,
                "poll_interval_seconds": 120,
                "categories": ["global_gold"],
                "rule_bindings": ["GLOB_CB_GOLD_RESERVES", "GLOB_MINING_SUPPLY", "GLOB_ASIA_PHYSICAL_DEMAND"],
                "reliability_score": 0.85,
                "notes": "Kitco gold market news and analysis",
            },
            {
                "id": str(uuid.uuid4()),
                "name": "TSETMC / کدال (JSON API)",
                "type": "json_api",
                "base_url": "https://cdn.tsetmc.com",
                "endpoints": ["/api/MarketData/GetGoldFunds"],
                "method": "GET",
                "headers": {},
                "auth_config": {},
                "parser": "json_parser",
                "enabled": False,
                "poll_interval_seconds": 300,
                "categories": ["gold_funds"],
                "rule_bindings": ["FUNDS_NAV_PREMIUM", "FUNDS_FLOW_VOLUME", "FUNDS_CODAL_NOTICES"],
                "reliability_score": 0.8,
                "notes": "بورس تهران — صندوق‌های طلا (غیرفعال تا تنظیم endpoint)",
            },
        ]

        for src in example_sources:
            result = await session.execute(
                text("SELECT id FROM sources WHERE name = :name"),
                {"name": src["name"]}
            )
            if result.scalar() is None:
                import json
                await session.execute(
                    text("""
                        INSERT INTO sources (id, name, type, base_url, endpoints, method, headers,
                            auth_config, parser, enabled, poll_interval_seconds, categories,
                            rule_bindings, reliability_score, notes, created_at, updated_at)
                        VALUES (:id, :name, :type, :base_url, :endpoints, :method, :headers,
                            :auth_config, :parser, :enabled, :poll_interval_seconds, :categories,
                            :rule_bindings, :reliability_score, :notes, NOW(), NOW())
                    """),
                    {
                        **{k: v for k, v in src.items() if k not in ("endpoints", "headers", "auth_config", "categories", "rule_bindings")},
                        "endpoints": json.dumps(src["endpoints"]),
                        "headers": json.dumps(src["headers"]),
                        "auth_config": json.dumps(src["auth_config"]),
                        "categories": json.dumps(src["categories"]),
                        "rule_bindings": json.dumps(src["rule_bindings"]),
                    }
                )
                print(f"[SEED] Source created: {src['name']}")
            else:
                print(f"[SEED] Source already exists: {src['name']}")

        await session.commit()
        print("[SEED] Done!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
