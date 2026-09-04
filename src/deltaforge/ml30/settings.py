# Vendored from ml30-sp500-strategy @ c7ad990 (2026-09-02) — see deltaforge/ml30/__init__.py.
# Only the import paths and PROJECT_ROOT were changed.
"""Runtime configuration for ML30-SP500-v2.

All environment-driven knobs live here. Modules MUST import `settings` from
this package instead of calling `os.getenv` directly. Pydantic validates
values at import time, so invalid configuration fails fast at startup.

Reference: TSD-MomentumLong-v2.0 §6 (sizing), §8 (architecture), §9 (data).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]  # the DeltaForge repo root
ENV_FILE: Path = PROJECT_ROOT / ".env"
ENV_FILE_PAPER: Path = PROJECT_ROOT / ".env.paper"

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["json", "console"]

ALPACA_DATA_URL: str = "https://data.alpaca.markets/v2"


class _BaseConfig(BaseSettings):
    """Shared Pydantic settings config — loads `.env`, ignores unknown vars."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class AlpacaSettings(_BaseConfig):
    """Alpaca Markets API credentials and endpoints."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="ALPACA_",
        case_sensitive=False,
        extra="ignore",
    )

    api_key: SecretStr = Field(default=SecretStr(""), description="Alpaca API key (paper or live)")
    secret_key: SecretStr = Field(default=SecretStr(""), description="Alpaca API secret")
    base_url: str = Field(
        default="https://paper-api.alpaca.markets/v2",
        description="Trading API base URL — paper by default",
    )

    @property
    def has_credentials(self) -> bool:
        """True when both API key and secret are set to non-empty values."""
        return bool(self.api_key.get_secret_value()) and bool(self.secret_key.get_secret_value())

    @property
    def data_url(self) -> str:
        """Market-data endpoint (separate from trading endpoint)."""
        return ALPACA_DATA_URL

    @property
    def is_paper(self) -> bool:
        """True when configured against the Alpaca paper-trading endpoint."""
        return "paper" in self.base_url


class PostgresSettings(_BaseConfig):
    """PostgreSQL connection parameters."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="POSTGRES_",
        case_sensitive=False,
        extra="ignore",
    )

    host: str = "localhost"
    port: int = 5432
    db: str = "ml30_strategy"
    user: str = "ml30_user"
    password: SecretStr = SecretStr("change_me_in_production")

    @property
    def dsn(self) -> str:
        """SQLAlchemy DSN for psycopg3 driver."""
        pw = self.password.get_secret_value()
        return f"postgresql+psycopg://{self.user}:{pw}@{self.host}:{self.port}/{self.db}"


class BacktestSettings(_BaseConfig):
    """Strategy and backtest parameters — defaults match TSD-v2.1 single-phase bracket."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="BACKTEST_",
        case_sensitive=False,
        extra="ignore",
    )

    initial_equity: Decimal = Decimal("10000.00")
    risk_pct: float = 0.01
    max_position_pct: float = 0.05
    stop_lookback: int = 8
    r_target: float = 3.0
    exit_sma_period: int | None = None  # None = no exit-SMA; 8/13/21 to enable
    exit_sma_profit_only: bool = True
    max_concurrent_positions: int = 10

    @field_validator("risk_pct")
    @classmethod
    def _risk_pct_in_range(cls, v: float) -> float:
        if not (0.0 < v <= 0.05):
            raise ValueError(f"risk_pct must be in (0, 0.05], got {v}")
        return v

    @field_validator("max_position_pct")
    @classmethod
    def _max_position_pct_in_range(cls, v: float) -> float:
        if not (0.0 < v <= 1.0):
            raise ValueError(f"max_position_pct must be in (0, 1], got {v}")
        return v

    @field_validator("stop_lookback")
    @classmethod
    def _stop_lookback_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"stop_lookback must be >= 1, got {v}")
        return v

    @field_validator("r_target")
    @classmethod
    def _r_target_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"r_target must be > 0, got {v}")
        return v

    @field_validator("initial_equity")
    @classmethod
    def _equity_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError(f"initial_equity must be > 0, got {v}")
        return v

    @field_validator("max_concurrent_positions")
    @classmethod
    def _max_positions_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"max_concurrent_positions must be >= 1, got {v}")
        return v


class PaperBotSettings(_BaseConfig):
    """Paper-trading bot credentials and runtime knobs.

    Loaded from a separate `.env.paper` file (with prefix `ALPACA_PAPER_`)
    so that the live executor's TrioAlgo credentials remain isolated from
    any other Alpaca credentials in the project's main `.env`.

    **The env file outranks the process environment** — see
    `settings_customise_sources`. This is the opposite of pydantic-settings'
    default, and deliberately so.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PAPER,
        env_file_encoding="utf-8",
        env_prefix="ALPACA_PAPER_",
        case_sensitive=False,
        extra="ignore",
    )

    api_key: SecretStr = Field(default=SecretStr(""))
    secret: SecretStr = Field(default=SecretStr(""))
    endpoint: str = Field(default="https://paper-api.alpaca.markets")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Rank the dotenv file ABOVE the process environment.

        Each bot instance is pointed at its own account with
        ``--env-file .env.paper.<variant>``. Under pydantic-settings' default
        ordering a plain ``ALPACA_PAPER_API_KEY`` in ``os.environ`` silently
        outranks that file — so anything that leaks credentials into the
        environment makes ``--env-file`` a no-op and the bot trades **a
        different brokerage account than the one it was told to**, with no
        error anywhere.

        That is not hypothetical. `scripts/screener_walkforward` used to inject
        `.env.paper` into `os.environ` at import time; the metrics exporter,
        which serves several accounts in one process, reported identical
        equity, positions and P&L for both bots because the first env file
        loaded won for all of them. Plausible-looking numbers, wrong account.

        An explicit env file is an explicit instruction. It wins.
        """
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key.get_secret_value()) and bool(self.secret.get_secret_value())


class PathsSettings:
    """Filesystem layout — derived from PROJECT_ROOT, not env-driven directly.

    `reports_dir` honours the `REPORTS_OUTPUT_DIR` env var when set.
    """

    def __init__(self, reports_output_dir: str | None = None) -> None:
        self.project_root: Path = PROJECT_ROOT
        self.data_cache_dir: Path = PROJECT_ROOT / "data" / "cache"
        self.reports_dir: Path = (
            Path(reports_output_dir).expanduser().resolve()
            if reports_output_dir
            else PROJECT_ROOT / "reports"
        )

    def ensure(self) -> None:
        """Create cache and reports directories if missing."""
        self.data_cache_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


class LogSettings(_BaseConfig):
    """Logging configuration."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="LOG_",
        case_sensitive=False,
        extra="ignore",
    )

    level: LogLevel = "INFO"
    format: LogFormat = "json"


class Settings:
    """Top-level settings aggregator — instantiate once at startup."""

    def __init__(self) -> None:
        self.alpaca: AlpacaSettings = AlpacaSettings()  # type: ignore[call-arg]
        self.paper_bot: PaperBotSettings = PaperBotSettings()  # type: ignore[call-arg]
        self.postgres: PostgresSettings = PostgresSettings()
        self.backtest: BacktestSettings = BacktestSettings()
        self.log: LogSettings = LogSettings()

        import os

        self.paths: PathsSettings = PathsSettings(
            reports_output_dir=os.getenv("REPORTS_OUTPUT_DIR")
        )

    def __repr__(self) -> str:
        return (
            f"Settings(r_target={self.backtest.r_target}, "
            f"exit_sma={self.backtest.exit_sma_period}, "
            f"risk_pct={self.backtest.risk_pct}, "
            f"alpaca_paper={self.alpaca.is_paper}, "
            f"postgres={self.postgres.host}:{self.postgres.port}/{self.postgres.db})"
        )


settings: Settings = Settings()
