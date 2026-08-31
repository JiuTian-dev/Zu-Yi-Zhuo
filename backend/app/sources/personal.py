"""Safe subprocess bridge for an authorized personal-context adapter."""

import asyncio
import json
from collections.abc import Sequence
from typing import Any

from app.domain import PersonalContextScope, PersonalContextSignal

from .base import PersonalContextSourceError


class CommandPersonalContextSource:
    """Call a server-side OAuth/CLI/MCP adapter over bounded JSON stdin/stdout."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = 5.0,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        if not command or any(not item.strip() for item in command):
            raise ValueError("personal context source command must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("personal context source timeout must be positive")
        if max_output_bytes <= 0:
            raise ValueError("personal context source max output must be positive")
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    async def _read_bounded(self, stream: asyncio.StreamReader | None) -> tuple[bytes, bool]:
        if stream is None:
            return b"", False
        chunks: list[bytes] = []
        total = 0
        while chunk := await stream.read(64 * 1024):
            remaining = self.max_output_bytes - total
            if remaining > 0:
                chunks.append(chunk[:remaining])
            total += len(chunk)
        return b"".join(chunks), total > self.max_output_bytes

    async def _drain(self, stream: asyncio.StreamReader | None) -> None:
        if stream is not None:
            while await stream.read(64 * 1024):
                pass

    async def search(
        self, *, viewer_id: str, scopes: Sequence[PersonalContextScope], query: str, limit: int
    ) -> Sequence[PersonalContextSignal]:
        if not viewer_id.strip() or not query.strip():
            raise PersonalContextSourceError("personal context viewer and query are required")
        if limit <= 0:
            raise PersonalContextSourceError("personal context limit must be positive")
        try:
            process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            if process.stdin is None:
                raise OSError("personal context source stdin unavailable")
            process.stdin.write(json.dumps(
                {"viewer_id": viewer_id, "scopes": list(scopes), "query": query, "limit": limit},
                ensure_ascii=False,
            ).encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
            stdout_task = asyncio.create_task(self._read_bounded(process.stdout))
            stderr_task = asyncio.create_task(self._drain(process.stderr))
            await asyncio.wait_for(
                asyncio.gather(process.wait(), stdout_task, stderr_task),
                timeout=self.timeout_seconds,
            )
            stdout, oversized = stdout_task.result()
        except asyncio.TimeoutError as error:
            if "process" in locals() and process.returncode is None:
                process.kill()
                await process.wait()
            for task_name in ("stdout_task", "stderr_task"):
                task = locals().get(task_name)
                if task is not None and not task.done():
                    task.cancel()
            raise PersonalContextSourceError("personal context source timed out") from error
        except (BrokenPipeError, ConnectionResetError, OSError, ValueError) as error:
            raise PersonalContextSourceError("personal context source could not start") from error

        if process.returncode != 0:
            raise PersonalContextSourceError("personal context source exited unsuccessfully")
        if oversized:
            raise PersonalContextSourceError("personal context source output is too large")
        try:
            payload: Any = json.loads(stdout.decode("utf-8"))
            rows = payload.get("signals") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                raise ValueError("personal signals must be an array")
            return [
                PersonalContextSignal.model_validate(item)
                for item in rows[:limit]
            ]
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise PersonalContextSourceError(
                "personal context source returned invalid JSON signals"
            ) from error


__all__ = ("CommandPersonalContextSource",)
