"""Validated deployment settings, read from environment variables only."""
from typing import Literal

from pydantic import AnyHttpUrl, TypeAdapter, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PEM_", extra="ignore")
    mode: Literal["local", "base"] = "local"
    origin: str = ""

    @model_validator(mode="after")
    def secure_base_origin(self):
        if self.mode != "base":
            return self
        message = "PEM_ORIGIN must be an HTTPS origin such as https://base.example.com, without credentials, a path, query or fragment"
        if not self.origin or self.origin != self.origin.strip() or any(ord(c) < 33 for c in self.origin):
            raise ValueError(message)
        try:
            url = TypeAdapter(AnyHttpUrl).validate_python(self.origin)
        except ValueError:
            raise ValueError(message) from None
        if (url.scheme != "https" or url.username is not None or url.password is not None
                or url.path not in (None, "/") or url.query is not None or url.fragment is not None
                or not url.port or "\\" in self.origin):
            raise ValueError(message)
        # Match the browser's Origin format.
        self.origin = str(url).rstrip("/")
        return self


def get_settings():
    # Read environment variables only.
    return Settings(_env_file=None)
