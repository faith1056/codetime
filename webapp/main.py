"""CodeTime web application (FastAPI)."""

from contextlib import closing
from pathlib import Path

import codetime
from fastapi import FastAPI, HTTPException
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


    return app


class StartSessionRequest(BaseModel):
    """Data the browser sends when starting a session."""

    project: str = "coding"


app = create_app()