from fastapi.testclient import TestClient

from godot_forge.api import create_app
from godot_forge.runtime import GodotForgeRuntime


def test_http_build_and_approval_flow(runtime: GodotForgeRuntime) -> None:
    with TestClient(create_app(runtime)) as client:
        created = client.post(
            "/v1/builds",
            json={"request": "制作一个 2D 生存原型", "thread_id": "http-build"},
        )
        state = client.get("/v1/builds/http-build")
        resumed = client.post(
            "/v1/builds/http-build/resume",
            json={"approved": True, "note": "测试审批"},
        )
        health = client.get("/health")

    assert created.status_code == 200
    assert created.json()["status"] == "awaiting_approval"
    assert state.status_code == 200
    assert state.json()["next"] == ["approval"]
    assert resumed.status_code == 200
    assert resumed.json()["verification"]["status"] == "passed"
    assert health.status_code == 200
