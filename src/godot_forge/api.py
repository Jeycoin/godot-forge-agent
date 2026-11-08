import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from godot_forge.runtime import GodotForgeRuntime
from godot_forge.schemas import ApprovalRequest, BuildRequest, RunResponse


def create_app(runtime: GodotForgeRuntime | None = None) -> FastAPI:
    owns_runtime = runtime is None

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.runtime = runtime or GodotForgeRuntime()
        yield
        if owns_runtime:
            application.state.runtime.close()

    application = FastAPI(
        title="GodotForge API",
        version="1.0.0",
        description="Verifiable Godot game-prototyping agent",
        lifespan=lifespan,
    )

    def get_runtime(request: Request) -> GodotForgeRuntime:
        return request.app.state.runtime

    @application.get("/health")
    async def health(request: Request) -> dict[str, str]:
        current = get_runtime(request)
        return {"status": "ok", "model_provider": current.settings.model_provider}

    @application.post("/v1/builds", response_model=RunResponse)
    async def create_build(build: BuildRequest, request: Request) -> RunResponse:
        current = get_runtime(request)
        return await asyncio.to_thread(current.run, build.request, build.thread_id)

    @application.post("/v1/builds/{thread_id}/resume", response_model=RunResponse)
    async def resume_build(
        thread_id: str,
        approval: ApprovalRequest,
        request: Request,
    ) -> RunResponse:
        current = get_runtime(request)
        try:
            return await asyncio.to_thread(
                current.resume,
                thread_id,
                approval.approved,
                approval.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/v1/builds/{thread_id}")
    async def get_build(thread_id: str, request: Request) -> dict:
        state = get_runtime(request).get_state(thread_id)
        if state["spec"] is None:
            raise HTTPException(status_code=404, detail="Build not found")
        return state

    return application


app = create_app()
