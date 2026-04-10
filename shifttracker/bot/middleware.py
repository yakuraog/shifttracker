from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from loguru import logger


class ErrorBoundaryMiddleware(BaseMiddleware):
    """Catches unhandled exceptions in handlers, logs via loguru, prevents bot crash."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            logger.exception(f"Unhandled exception in handler: {exc}")
            return None
