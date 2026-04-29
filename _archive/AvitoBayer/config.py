from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # avito-xapi backend
    xapi_base_url: str = "https://avito.newlcd.ru/api/v1"
    xapi_api_key: str = ""

    # Supabase (for leads table — same DB as avito-xapi)
    supabase_url: str = "https://bkxpajeqrkutktmtmwui.supabase.co"
    supabase_key: str = ""

    # Telegram notifications (Avito-бот)
    tg_notify_bot_token: str = "8703595821:AAGt0Xi3tNBscmyfa_-9yUy9PMQ8KcrsXNA"
    tg_notify_chat_id: str = "6416413182"
    tg_notify_proxy: str = "socks5://127.0.0.1:1080"
    tg_notify_enabled: bool = True

    # Scheduler
    scheduler_autostart: bool = True

    # LLM eval (optional — requires anthropic API key)
    llm_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
