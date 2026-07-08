from typing import Any

from pydantic import BaseModel


class Budgets(BaseModel):
    max_iterations: int
    max_attempts_per_group: int
    max_errors_parsed: int


class Counters(BaseModel):
    errors_initial: int = 0
    errors_current: int = 0
    fixes_local: int = 0
    fixes_remote: int = 0
    fixes_deterministic: int = 0
    tokens_local: int = 0
    tokens_remote: int = 0
    iterations: int = 0


class Run(BaseModel):
    id: str
    repo_url: str
    state: str
    budgets: Budgets
    counters: Counters


class Wave64Finding(BaseModel):
    file: str
    line: int
    pattern_id: str
    snippet: str
    severity: str
    explanation: str


class ScanResult(BaseModel):
    files_cuda: list[str]
    loc_kernels: int
    api_calls: dict[str, int]
    libs: list[str]
    build_system: str
    wave64_findings: list[Wave64Finding]
    difficulty: str


class BuildError(BaseModel):
    file: str
    line: int
    col: int
    message: str
    signature: str


class ErrorGroup(BaseModel):
    signature: str
    errors: list[BuildError]
    klass: str | None = None
    attempts: int = 0
    status: str = "open"


class FixAttempt(BaseModel):
    group_signature: str
    tier: str
    patch: str
    applied: bool
    build_delta: int
    commit_sha: str | None = None
    tokens: int = 0


class VerifyResult(BaseModel):
    ran: bool
    exit_code: int
    verdict: str
    parity_details: str
    timing: dict[str, Any] | None = None


class BuildResult(BaseModel):
    ok: bool
    count: int
    raw_output: str
    returncode: int


class RunResult(BaseModel):
    ran: bool
    exit_code: int
    stdout: str
    timing: dict[str, Any] | None = None


class RunState:
    QUEUED = "QUEUED"
    CLONING = "CLONING"
    SCANNING = "SCANNING"
    PORTING = "PORTING"
    BUILD_LOOP = "BUILD_LOOP"
    RUNNING = "RUNNING"
    PARITY = "PARITY"
    REPORTING = "REPORTING"
    DONE = "DONE"
    DONE_PARTIAL = "DONE_PARTIAL"
    FAILED = "FAILED"
    ALL = [
        QUEUED,
        CLONING,
        SCANNING,
        PORTING,
        BUILD_LOOP,
        RUNNING,
        PARITY,
        REPORTING,
        DONE,
        DONE_PARTIAL,
        FAILED,
    ]
