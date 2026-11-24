from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        path = path.replace("\\", "/")
        # Nunca transformar erros da API ou de assets em um HTML bem-sucedido.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or Path(path).suffix or path.startswith("assets/"):
                raise
            return await super().get_response("index.html", scope)


def mount_frontend(app: FastAPI, directory: Path) -> None:
    if not (directory / "index.html").is_file():
        raise RuntimeError("Frontend não compilado. Execute o build antes de habilitar SERVE_FRONTEND.")
    app.mount("/", FrontendFiles(directory=str(directory), html=True), name="frontend")
