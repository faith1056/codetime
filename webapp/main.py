"""CodeTime web application (FastAPI)."""

from contextlib import closing
import threading
from pathlib import Path

import codetime
import tracker_auth
import tracker_engine
import tracker_events
from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""

    app = FastAPI(
        title="CodeTime",
        version="0.1.0",
        description="Track your coding time from the browser.",
    )

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

    @app.get("/api/status", tags=["sessions"])
    def session_status() -> dict:
        """Return the current session and today's coding time."""

        with closing(codetime.connect()) as connection:
            current = codetime.now()
            running = codetime.active_session(connection)

            start, end, _ = codetime.period_range("today", current)

            today_seconds = codetime.total_seconds(
                codetime.collect_segments(
                    connection,
                    start,
                    end,
                    current,
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
    def start_web_session(request: "StartSessionRequest") -> dict:
        """Start a session using CodeTime's existing session logic."""

        project = request.project.strip()

        if not project:
            raise HTTPException(
                status_code=400,
                detail="Project name cannot be empty.",
            )

        try:
            with closing(codetime.connect()) as connection:
                started = codetime.start_session(
                    connection,
                    project,
                )

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
    def stop_web_session() -> dict:
        """Stop the active session using CodeTime's existing logic."""

        try:
            with closing(codetime.connect()) as connection:
                project, started, ended = codetime.stop_session(
                    connection
                )

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
    def recent_sessions() -> dict:
        """Return the ten most recent coding sessions."""

        with closing(codetime.connect()) as connection:
            sessions = codetime.list_sessions(connection, 10)

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


    engine = tracker_engine.Engine()
    engine_lock = threading.Lock()

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