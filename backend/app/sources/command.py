"""Safe subprocess bridge for an authorized external candidate adapter."""

import asyncio
import json
from collections.abc import Sequence
from typing import Any

from app.domain import ParticipantSeed

from .base import CandidateSourceError


class CommandCandidateSource:
    """Call a preconfigured CLI/MCP wrapper over a bounded JSON stdin/stdout contract.

    The command receives ``{"query": str, "limit": int}`` on stdin and must
    return either a JSON array of ``ParticipantSeed`` objects or an object with
    a ``candidates`` array.  Authorization stays inside the external adapter.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = 5.0,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        if not command or any(not item.strip() for item in command):
            raise ValueError("candidate source command must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("candidate source timeout must be positive")
        if max_output_bytes <= 0:
            raise ValueError("candidate source max output must be positive")
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

    async def search(self, *, query: str, limit: int) -> Sequence[ParticipantSeed]:
        if not query.strip():
            raise CandidateSourceError("candidate source query must be non-empty")
        if limit <= 0:
            raise CandidateSourceError("candidate source limit must be positive")
        try:
            process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            if process.stdin is None:
                raise OSError("candidate source stdin unavailable")
            process.stdin.write(
                json.dumps({"query": query, "limit": limit}, ensure_ascii=False).encode("utf-8")
            )
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
            raise CandidateSourceError("candidate source timed out") from error
        except (BrokenPipeError, ConnectionResetError, OSError, ValueError) as error:
            raise CandidateSourceError("candidate source could not start") from error

        if process.returncode != 0:
            raise CandidateSourceError("candidate source exited unsuccessfully")
        if oversized:
            raise CandidateSourceError("candidate source output is too large")
        try:
            payload: Any = json.loads(stdout.decode("utf-8"))
            rows = payload.get("candidates") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                raise ValueError("candidates must be an array")
            return [ParticipantSeed.model_validate(item) for item in rows[:limit]]
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise CandidateSourceError("candidate source returned invalid JSON candidates") from error


__all__ = ("CommandCandidateSource",)
