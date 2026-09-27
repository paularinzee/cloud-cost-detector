"""
AI Cloud Cost Detective — FastAPI Backend
-----------------------------------------
Endpoints:
  GET   /api/health                    (DB-aware)
  POST  /api/auth/signup               { email, password }
  POST  /api/auth/login                { email, password } -> { access_token }
  GET   /api/resource-groups           (auth)
  POST  /api/analyze                   (auth) -> 202 { analysis_id }
  GET   /api/history                   (auth)
  GET   /api/analyses/{id}             (auth)
  WS    /ws/progress/{analysis_id}?token=<jwt>

End-to-end flow:
  ① User (React) triggers analyze.
  ② POST /api/analyze (JWT) → creates pending `analyses` row → 202.
  ③ Background task scans resources via Azure CLI.
  ④ Row updated with results.
  ⑤ OpenAI gpt-4o produces the cost analysis.
  ⑥ Progress pushed over WebSocket at each stage.
  ⑦ React reads final report from Postgres via /api/analyses/{id}.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

import jwt as pyjwt
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from ai_analyzer import AIAnalyzerError, analyze_costs
from auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from azure_scanner import (
    AzureCLIError,
    list_resource_groups,
    list_resources,
)
from db import (
    Analysis,
    SessionLocal,
    create_analysis,
    create_user,
    dispose_db,
    fail_analysis,
    finalize_analysis,
    get_analysis_for_user,
    get_user_by_email,
    init_db,
    list_analyses_for_user,
)

load_dotenv()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

ALLOWED_ORIGINS = {"http://localhost:5173"}


# ---------- Lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield
    await dispose_db()


app = FastAPI(
    title="AI Cloud Cost Detective API",
    version="1.0.0",
    description="Azure cost analysis with AI, persisted history, and live progress.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Progress hub ----------
class ProgressHub:
    def __init__(self) -> None:
        self._subs: Dict[int, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, analysis_id: int) -> asyncio.Queue:
        async with self._lock:
            q: asyncio.Queue = asyncio.Queue()
            self._subs.setdefault(analysis_id, []).append(q)
            return q

    async def unsubscribe(self, analysis_id: int, q: asyncio.Queue) -> None:
        async with self._lock:
            if analysis_id in self._subs and q in self._subs[analysis_id]:
                self._subs[analysis_id].remove(q)
                if not self._subs[analysis_id]:
                    del self._subs[analysis_id]

    async def publish(self, analysis_id: int, message: Dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._subs.get(analysis_id, []))
        for q in queues:
            await q.put(message)


hub = ProgressHub()


async def emit(analysis_id: int, stage: str, message: str, **extra: Any) -> None:
    await hub.publish(
        analysis_id,
        {
            "stage": stage,
            "message": message,
            "ts": datetime.now(timezone.utc).isoformat(),
            **extra,
        },
    )


# ---------- Schemas ----------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AnalyzeRequest(BaseModel):
    resource_group: str = Field(..., min_length=1)


class AnalyzeAccepted(BaseModel):
    analysis_id: int
    status: str = "accepted"
    resource_group: str


class ResourceGroupInfo(BaseModel):
    name: Optional[str]
    location: Optional[str] = None
    id: Optional[str] = None
    tags: Dict[str, str] = {}
    provisioning_state: Optional[str] = None


class HistoryItem(BaseModel):
    id: int
    resource_group: str
    resources_scanned: int
    issues_found: int
    estimated_savings: str
    status: str
    created_at: datetime
    analysis_result: Dict[str, Any]


# ---------- Auth dependency ----------
async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Dict[str, Any]:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exc
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
        email = payload.get("email")
        if not email:
            raise credentials_exc
    except (pyjwt.PyJWTError, ValueError, TypeError):
        raise credentials_exc

    user = await get_user_by_email(email)
    if user is None or user.id != user_id:
        raise credentials_exc
    return {"id": user.id, "email": user.email}


def _handle_azure_error(exc: AzureCLIError) -> HTTPException:
    if exc.kind == "not_installed":
        return HTTPException(status_code=503, detail=str(exc))
    if exc.kind == "not_logged_in":
        return HTTPException(status_code=401, detail=str(exc))
    if exc.kind == "not_found":
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


# ---------- Routes ----------
@app.get("/api/health")
async def health() -> Dict[str, str]:
    """DB-aware health check — fails if Postgres is unreachable."""
    async with SessionLocal() as session:
        await session.execute(select(1))
    return {"status": "ok"}


@app.post("/api/auth/signup", response_model=TokenResponse, status_code=201)
async def signup(payload: SignupRequest) -> TokenResponse:
    if await get_user_by_email(payload.email):
        raise HTTPException(status_code=409, detail="Email already registered.")
    user = await create_user(payload.email, hash_password(payload.password))
    return TokenResponse(access_token=create_access_token(user.id, user.email))


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    user = await get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return TokenResponse(access_token=create_access_token(user.id, user.email))


@app.get("/api/resource-groups", response_model=List[ResourceGroupInfo])
def get_resource_groups(
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        return list_resource_groups()
    except AzureCLIError as exc:
        raise _handle_azure_error(exc)


@app.post("/api/analyze", response_model=AnalyzeAccepted, status_code=202)
async def analyze(
    payload: AnalyzeRequest,
    bg: BackgroundTasks,
    user: Dict[str, Any] = Depends(get_current_user),
) -> AnalyzeAccepted:
    rg = payload.resource_group.strip()
    row = await create_analysis(user["id"], rg, status="pending")
    bg.add_task(_run_pipeline, row.id, rg)
    return AnalyzeAccepted(analysis_id=row.id, resource_group=rg)


async def _run_pipeline(analysis_id: int, rg: str) -> None:
    try:
        # Step ③ — Azure scan
        await emit(analysis_id, "scanning", "Fetching resource groups...")
        try:
            resources = list_resources(rg)
        except AzureCLIError as exc:
            await emit(analysis_id, "error", str(exc))
            await fail_analysis(analysis_id, str(exc))
            return

        await emit(
            analysis_id,
            "scanning",
            f"Scanning resources in {rg}...",
            resource_count=len(resources),
        )

        summary: Dict[str, int] = {}
        for r in resources:
            t = r.get("type") or "unknown"
            summary[t] = summary.get(t, 0) + 1

        # Step ⑤ — AI cost analysis
        await emit(analysis_id, "analyzing", "Analyzing costs with AI...")
        try:
            analysis = analyze_costs(rg, resources)
        except AIAnalyzerError as exc:
            await emit(analysis_id, "error", str(exc))
            await fail_analysis(analysis_id, str(exc))
            return

        # Step ④ — persist
        await emit(analysis_id, "storing", "Storing results...")
        await finalize_analysis(
            analysis_id,
            resources_scanned=len(resources),
            issues_found=len(analysis["issues"]),
            estimated_savings=f"${analysis['estimated_monthly_savings_usd']:.2f}",
            analysis_result={
                "resource_group": rg,
                "resource_count": len(resources),
                "resources": resources,
                "summary_by_type": summary,
                "summary": analysis["summary"],
                "estimated_monthly_savings_usd": analysis["estimated_monthly_savings_usd"],
                "issues": analysis["issues"],
                "quick_wins": analysis["quick_wins"],
            },
            status="complete",
        )

        # Step ⑥ — final progress
        await emit(
            analysis_id,
            "complete",
            "Analysis complete",
            issues_found=len(analysis["issues"]),
            estimated_savings_usd=analysis["estimated_monthly_savings_usd"],
        )
    except Exception as exc:  # noqa: BLE001
        await emit(analysis_id, "error", f"Unexpected error: {exc}")
        await fail_analysis(analysis_id, str(exc))


@app.get("/api/history", response_model=List[HistoryItem])
async def get_history(
    limit: int = 50,
    offset: int = 0,
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[HistoryItem]:
    rows: List[Analysis] = await list_analyses_for_user(
        user["id"], limit=limit, offset=offset
    )
    return [
        HistoryItem(
            id=r.id,
            resource_group=r.resource_group,
            resources_scanned=r.resources_scanned,
            issues_found=r.issues_found,
            estimated_savings=r.estimated_savings,
            status=r.status,
            created_at=r.created_at,
            analysis_result=r.analysis_result or {},
        )
        for r in rows
    ]


@app.get("/api/analyses/{analysis_id}", response_model=HistoryItem)
async def get_analysis(
    analysis_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HistoryItem:
    row = await get_analysis_for_user(analysis_id, user["id"])
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return HistoryItem(
        id=row.id,
        resource_group=row.resource_group,
        resources_scanned=row.resources_scanned,
        issues_found=row.issues_found,
        estimated_savings=row.estimated_savings,
        status=row.status,
        created_at=row.created_at,
        analysis_result=row.analysis_result or {},
    )


# ---------- WebSocket ----------
@app.websocket("/ws/progress/{analysis_id}")
async def ws_progress(
    websocket: WebSocket,
    analysis_id: int,
    token: str = Query(...),
) -> None:
    """
    Live progress channel.

    Requires `?token=<jwt>` and verifies that the JWT's owner owns the
    analysis row. Also rejects connections whose Origin isn't in
    ALLOWED_ORIGINS (FastAPI's CORSMiddleware does not cover WS).
    """
    # #3 — Origin check
    origin = websocket.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return

    # #15 — JWT verification
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
        email = payload.get("email")
        if not email:
            raise ValueError("missing email")
    except (pyjwt.PyJWTError, ValueError, TypeError):
        await websocket.close(code=1008)
        return

    user = await get_user_by_email(email)
    if user is None or user.id != user_id:
        await websocket.close(code=1008)
        return

    # Ownership of the analysis row
    row = await get_analysis_for_user(analysis_id, user_id)
    if row is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    queue = await hub.subscribe(analysis_id)
    try:
        await websocket.send_json({
            "stage": "connected",
            "message": f"Subscribed to analysis {analysis_id}",
            "ts": datetime.now(timezone.utc).isoformat(),
        })

        # If the pipeline already finished, replay final state.
        if row.status in ("complete", "failed"):
            await websocket.send_json({
                "stage": row.status,
                "message": "Analysis complete" if row.status == "complete"
                           else "Analysis failed",
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            return

        while True:
            message = await queue.get()
            await websocket.send_json(message)
            if message.get("stage") in ("complete", "error"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(analysis_id, queue)
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)