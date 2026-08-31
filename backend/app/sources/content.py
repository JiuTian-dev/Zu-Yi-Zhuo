"""Safe subprocess bridge for an authorized public-content adapter."""

import asyncio
import json
from collections.abc import Sequence
from typing import Any

from app.domain import ContentSignal

from .base import ContentSignalSourceError


class CommandContentSignalSource:
    """Call a content adapter over bounded JSON stdin/stdout."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = 5.0,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        if not command or any(not item.strip() for item in command):
            raise ValueError("content source command must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("content source timeout must be positive")
        if max_output_bytes <= 0:
            raise ValueError("content source max output must be positive")
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

    async def search(self, *, query: str, limit: int) -> Sequence[ContentSignal]:
        if not query.strip():
            raise ContentSignalSourceError("content source query must be non-empty")
        if limit <= 0:
            raise ContentSignalSourceError("content source limit must be positive")
        process_state: dict[str, Any] = {}

        async def run() -> tuple[bytes, bool, int]:
            process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            process_state["process"] = process
            if process.stdin is None:
                raise OSError("content source stdin unavailable")
            process.stdin.write(
                json.dumps({"query": query, "limit": limit}, ensure_ascii=False).encode("utf-8")
            )
            await process.stdin.drain()
            process.stdin.close()
            stdout_task = asyncio.create_task(self._read_bounded(process.stdout))
            stderr_task = asyncio.create_task(self._drain(process.stderr))
            process_state["stdout_task"] = stdout_task
            process_state["stderr_task"] = stderr_task
            await asyncio.gather(process.wait(), stdout_task, stderr_task)
            stdout, oversized = stdout_task.result()
            return stdout, oversized, process.returncode

        try:
            stdout, oversized, returncode = await asyncio.wait_for(
                run(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError as error:
            process = process_state.get("process")
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            for task_name in ("stdout_task", "stderr_task"):
                task = process_state.get(task_name)
                if task is not None and not task.done():
                    task.cancel()
            raise ContentSignalSourceError("content source timed out") from error
        except (BrokenPipeError, ConnectionResetError, OSError, ValueError) as error:
            raise ContentSignalSourceError("content source could not start") from error

        if returncode != 0:
            raise ContentSignalSourceError("content source exited unsuccessfully")
        if oversized:
            raise ContentSignalSourceError("content source output is too large")
        try:
            payload: Any = json.loads(stdout.decode("utf-8"))
            rows = payload.get("signals") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                raise ValueError("signals must be an array")
            return [ContentSignal.model_validate(item) for item in rows[:limit]]
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ContentSignalSourceError("content source returned invalid JSON signals") from error


__all__ = ("CommandContentSignalSource",)
