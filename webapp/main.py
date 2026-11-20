"""CodeTime web application (FastAPI)."""

import asyncio
from contextlib import asynccontextmanager, closing
import threading
from pathlib import Path

import account_login
import codetime
import tracker_auth
import tracker_engine
import tracker_events
import tracker_service
from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlsplit


ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class LoginRequest(BaseModel):
    email: str
    password: str


_SCHEMA_READY = set()


def _ensure_schema_once(connection):
    """Create the account tables once per data folder, not on every request."""
    key = str(codetime.app_dir())
    if key not in _SCHEMA_READY:
        account_login.ensure_schema(connection)
        _SCHEMA_READY.add(key)


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""

    engine = tracker_engine.Engine()
    engine_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(tracker_service.startup, engine, engine_lock)
        task = asyncio.create_task(
            tracker_service.tick_forever(engine, engine_lock)
        )
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(
        lifespan=lifespan,
        title="CodeTime",
        version="0.1.0",
        description="Track your coding time from the browser.",
    )

    # Only this computer may talk to the server (stops DNS rebinding).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

    @app.middleware("http")
    async def refuse_cross_origin_writes(request, call_next):
        """Refuse browser requests that another website started."""
        if (
            request.method in UNSAFE_METHODS
            and request.url.path.startswith("/api/")
        ):
            origin = request.headers.get("origin")
            if origin is not None:
                host = request.headers.get("host", "")
                if urlsplit(origin).netloc != host:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Cross-origin request refused."},
                    )
        return await call_next(request)

    # Serve CSS and other static files.
    static_directory = Path(__file__).parent / "static"

    app.mount(
        "/static",
        StaticFiles(directory=static_directory),
        name="static",
    )

    @app.get("/", response_class=HTMLResponse, tags=["pages"])
    def home() -> HTMLResponse:
        """Serve the CodeTime dashboard homepage."""

        html_file = Path(__file__).parent / "templates" / "index.html"

        return HTMLResponse(
            content=html_file.read_text(encoding="utf-8")
        )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Tell monitors that the application is running."""

        return {"status": "ok"}

    def require_account(
        x_codetime_account_token: str | None = Header(default=None),
    ) -> int:
        """Require a valid CodeTime account login token."""
        with closing(codetime.connect()) as connection:
            _ensure_schema_once(connection)
            user_id = account_login.user_for_token(
                connection,
                x_codetime_account_token,
            )

        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid account login token.",
            )

        return user_id

    @app.post("/api/login", tags=["accounts"])
    def login(data: LoginRequest) -> dict:
        """Check the password and return a login token."""
        with closing(codetime.connect()) as connection:
            _ensure_schema_once(connection)
            try:
                token = account_login.login(
                    connection, data.email, data.password
                )
            except codetime.CodeTimeError as error:
                locked = str(error) == account_login.LOCKED_ERROR
                raise HTTPException(
                    status_code=429 if locked else 401,
                    detail=str(error),
                ) from None
        return {"token": token}

    @app.post("/api/logout", tags=["accounts"])
    def logout(
        x_codetime_account_token: str | None = Header(default=None),
    ) -> dict:
        """Revoke the login token. Safe to call with a bad or missing token."""
        with closing(codetime.connect()) as connection:
            _ensure_schema_once(connection)
            account_login.logout(connection, x_codetime_account_token)
        return {"status": "logged out"}

    @app.get("/api/status", tags=["sessions"])
    def session_status(
        user_id: int = Depends(require_account),
    ) -> dict:
        """Return the current session and today's coding time."""

        with closing(codetime.connect()) as connection:
            current = codetime.now()
            running = codetime.active_session(
                connection, user_id=user_id
            )

            start, end, _ = codetime.period_range("today", current)

            today_seconds = codetime.total_seconds(
                codetime.collect_segments(
                    connection,
                    start,
                    end,
                    current,
                    user_id=user_id,
                )
            )

        session = None

        if running is not None:
            session_id, project, started = running

            session = {
                "id": session_id,
                "project": project,
                "started_at": started.isoformat(),
                "elapsed_seconds": int(
                    (current - started).total_seconds()
                ),
            }

        return {
            "active_session": session,
            "today_seconds": int(today_seconds),
        }

    @app.post("/api/start", tags=["sessions"])
    def start_web_session(
        request: "StartSessionRequest",
        user_id: int = Depends(require_account),
    ) -> dict:
        """Start a manual session and pause automatic tracking."""

        project = request.project.strip()

        if not project:
            raise HTTPException(
                status_code=400,
                detail="Project name cannot be empty.",
            )

        try:
            with engine_lock:
                with closing(codetime.connect()) as connection:
                    engine.pause(connection, codetime.now())

                    try:
                        started = codetime.start_session(
                            connection,
                            project,
                            user_id=user_id,
                        )
                    except codetime.CodeTimeError:
                        engine.resume(codetime.now())
                        raise

        except codetime.CodeTimeError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error

        return {
            "message": f"Started tracking {project}.",
            "project": project,
            "started_at": started.isoformat(),
        }

    @app.post("/api/stop", tags=["sessions"])
    def stop_web_session(
        user_id: int = Depends(require_account),
    ) -> dict:
        """Stop a manual session and allow automatic tracking to resume."""

        try:
            with engine_lock:
                with closing(codetime.connect()) as connection:
                    project, started, ended = codetime.stop_session(
                        connection,
                        user_id=user_id,
                    )

                engine.resume(codetime.now())

        except codetime.CodeTimeError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error

        duration_seconds = int(
            (ended - started).total_seconds()
        )

        return {
            "message": f"Stopped tracking {project}.",
            "project": project,
            "started_at": started.isoformat(),
            "ended_at": ended.isoformat(),
            "duration_seconds": duration_seconds,
        }

    @app.get("/api/sessions", tags=["sessions"])
    def recent_sessions(
        user_id: int = Depends(require_account),
    ) -> dict:
        """Return the ten most recent coding sessions."""

        with closing(codetime.connect()) as connection:
            sessions = codetime.list_sessions(
                connection, 10, user_id=user_id
            )

        results = []

        for session_id, project, started, ended in reversed(sessions):
            duration = None

            if ended is not None:
                duration = int((ended - started).total_seconds())

            results.append({
                "id": session_id,
                "project": project,
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat() if ended else None,
                "duration_seconds": duration,
                "active": ended is None,
            })

        return {"sessions": results}


    def require_token(x_codetime_token: str | None = Header(default=None)):
        """Reject any request that lacks the correct secret token."""
        if not tracker_auth.is_valid(x_codetime_token):
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid token.",
            )

    @app.get(
        "/tracker/state",
        tags=["tracker"],
        dependencies=[Depends(require_token)],
    )
    def tracker_status() -> dict:
        """Return the tracker's current state and project."""
        with engine_lock:
            return {
                "state": engine.tracker.state.value,
                "project": engine.tracker.project,
            }

    @app.post(
        "/tracker/event",
        tags=["tracker"],
        dependencies=[Depends(require_token)],
    )
    def tracker_event(data: dict = Body(...)) -> dict:
        """Record that coding activity happened in a project."""
        current = codetime.now()

        try:
            project, moment = tracker_events.parse_event(data, current)
        except codetime.CodeTimeError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error

        with engine_lock:
            with closing(codetime.connect()) as connection:
                engine.activity(connection, project, moment)
            return {
                "state": engine.tracker.state.value,
                "project": engine.tracker.project,
            }

    @app.post(
        "/tracker/pause",
        tags=["tracker"],
        dependencies=[Depends(require_token)],
    )
    def tracker_pause() -> dict:
        """Pause tracking. Activity is ignored until resume."""
        with engine_lock:
            with closing(codetime.connect()) as connection:
                engine.pause(connection, codetime.now())
            return {
                "state": engine.tracker.state.value,
                "project": engine.tracker.project,
            }

    @app.post(
        "/tracker/resume",
        tags=["tracker"],
        dependencies=[Depends(require_token)],
    )
    def tracker_resume() -> dict:
        """Leave the paused state. The next event starts a new row."""
        with engine_lock:
            engine.resume(codetime.now())
            return {
                "state": engine.tracker.state.value,
                "project": engine.tracker.project,
            }

    @app.post(
        "/tracker/stop",
        tags=["tracker"],
        dependencies=[Depends(require_token)],
    )
    def tracker_stop() -> dict:
        """Close the open row and return to the stopped state."""
        with engine_lock:
            with closing(codetime.connect()) as connection:
                engine.stop(connection, codetime.now())
            return {
                "state": engine.tracker.state.value,
                "project": engine.tracker.project,
            }

    return app


class StartSessionRequest(BaseModel):
    """Data the browser sends when starting a session."""

    project: str = "coding"


app = create_app()