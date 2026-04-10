import asyncio

from shifttracker.pipeline.models import ProcessingContext

message_queue: asyncio.Queue[ProcessingContext] = asyncio.Queue(maxsize=500)


async def enqueue_message(ctx: ProcessingContext) -> None:
    await message_queue.put(ctx)
