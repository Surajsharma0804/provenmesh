"""Dead Letter Queue — failed messages after max retries (v2 §12).

A message enters DLQ after max_attempts exceeded, with full context:
message_id, stage, error_type, attempts, last_error, correlation_id.

Essential for unattended operation — without DLQ, failed messages
either block the queue or disappear silently.
"""

from __future__ import annotations

from provenmesh.observability.logging import get_logger
from provenmesh.queue.messages import DLQMessage, QueueMessage
from provenmesh.queue.streams import add_to_stream

logger = get_logger(__name__)


async def route_to_dlq(
    dlq_stream: str,
    message: QueueMessage,
    stage: str,
    error: Exception,
) -> str:
    """Route a failed message to the dead letter queue.

    Returns the DLQ message ID.
    """
    dlq_message = DLQMessage.from_failed_message(
        original=message,
        stage=stage,
        error=error,
        original_stream=dlq_stream.replace(":dlq:", ":"),
    )

    msg_id = await add_to_stream(dlq_stream, dlq_message.to_stream_data())

    logger.error(
        "message_routed_to_dlq",
        dlq_stream=dlq_stream,
        stage=stage,
        error_type=type(error).__name__,
        error_message=str(error)[:500],
        correlation_id=message.correlation_id,
        attempts=message.attempt,
    )

    return msg_id
