"""CodeTime web application (FastAPI)."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build and return the FastAPI application.

    Using a function (instead of creating the app at import time) lets the
    tests build a fresh app whenever they need one.
    """
    app = FastAPI(
        title="CodeTime",
        version="0.1.0",
        description="Track your coding time from the browser.",
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Tell load balancers and monitors that the app is running."""
        return {"status": "ok"}

    return app


app = create_app()
