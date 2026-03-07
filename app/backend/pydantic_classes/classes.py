from pydantic_settings import BaseSettings, SettingsConfigDict 


class Settings(BaseSettings):
    provider: str
    model: str

    model_config = SettingsConfigDict(
        env_file=".env"
    )


settings = Settings()


