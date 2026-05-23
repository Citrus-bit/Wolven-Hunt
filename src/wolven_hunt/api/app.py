from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from wolven_hunt.api.deps import get_settings
from wolven_hunt.api.routes_games import router as games_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Wolven Hunt API")
    if settings.parsed_api_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.parsed_api_cors_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(games_router)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        del request
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            body = {
                "code": str(detail["code"]),
                "message": str(detail.get("message", detail["code"])),
            }
            if "details" in detail:
                body["details"] = detail["details"]
            return JSONResponse(status_code=exc.status_code, content=body)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": "http_error", "message": str(detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        first = exc.errors()[0] if exc.errors() else {}
        loc = first.get("loc", ())
        code = "invalid_agent_spec" if "agents" in loc else "validation_error"
        return JSONResponse(
            status_code=422,
            content={
                "code": code,
                "message": str(first.get("msg", code)),
                "details": {"errors": _validation_errors(exc)},
            },
        )

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    if settings.serve_static:
        dist_dir = Path(__file__).resolve().parents[3] / "dist"
        if dist_dir.exists():
            app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")

    return app


def _validation_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    errors: list[dict[str, object]] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        errors.append(
            {
                "loc": list(loc) if isinstance(loc, tuple) else loc,
                "msg": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return errors


app = create_app()
