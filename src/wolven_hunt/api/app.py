from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from wolven_hunt.api.deps import get_settings
from wolven_hunt.api.routes_games import router as games_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Wolven Hunt API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.api_cors_origins),
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

    return app


app = create_app()
