"""Browser automation boundary for future engine adapters.

This module deliberately does not use the HTTP client as a fake browser. A
conforming adapter must drive a real browser engine and expose JavaScript/DOM
state through a separate value type.
"""

from dataclasses import dataclass
from typing import Protocol


SUPPORTED_ENGINES = frozenset({"chromium", "firefox", "webkit"})


class BrowserAutomationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserProfile:
    engine: str = "chromium"
    screen_width: int = 1280
    screen_height: int = 720
    language: str = "en-US"
    headless: bool = True

    def __post_init__(self):
        if self.engine not in SUPPORTED_ENGINES:
            raise ValueError(f"Unsupported browser engine '{self.engine}'.")
        if isinstance(self.screen_width, bool) or not isinstance(self.screen_width, int) or self.screen_width <= 0:
            raise ValueError("screen_width must be a positive integer.")
        if isinstance(self.screen_height, bool) or not isinstance(self.screen_height, int) or self.screen_height <= 0:
            raise ValueError("screen_height must be a positive integer.")
        if not isinstance(self.language, str) or not self.language.strip():
            raise ValueError("language must be a non-empty string.")


class BrowserPage(Protocol):
    @property
    def url(self) -> str: ...
    def text(self, selector: str) -> str: ...
    def close(self) -> None: ...


class BrowserAdapter(Protocol):
    def open(self, url: str, profile: BrowserProfile) -> BrowserPage: ...


def browser_open(url: str, *, profile: BrowserProfile | None = None,
                 adapter: BrowserAdapter | None = None) -> BrowserPage:
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError("browser_open requires an absolute HTTP or HTTPS URL.")
    if adapter is None:
        raise BrowserAutomationUnavailable(
            "No browser engine adapter is installed. HTTP retrieval remains available through http_get()."
        )
    return adapter.open(url, profile or BrowserProfile())
