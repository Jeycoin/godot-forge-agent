import json

import typer

from godot_forge.config import Settings
from godot_forge.evaluation import evaluate as run_evaluation
from godot_forge.runtime import GodotForgeRuntime
from godot_forge.schemas import RunResponse

app = typer.Typer(
    name="godot-forge",
    help="Godot AI 游戏原型开发 Agent：设计、生成、审批、验证与修复。",
    no_args_is_help=True,
)


def print_response(response: RunResponse) -> None:
    typer.echo(response.model_dump_json(indent=2))
    if response.status == "awaiting_approval":
        typer.echo(
            f"\n等待确认工程变更。执行：godot-forge resume {response.thread_id} --approve",
            err=True,
        )


@app.command()
def run(
    request: str = typer.Argument(..., help="自然语言游戏需求"),
    thread_id: str | None = typer.Option(None, help="指定构建 ID，便于复现"),
) -> None:
    """生成游戏开发方案，并在写入文件前暂停等待确认。"""
    with GodotForgeRuntime() as runtime:
        print_response(runtime.run(request, thread_id))


@app.command()
def resume(
    thread_id: str = typer.Argument(..., help="等待审批的构建 ID"),
    approved: bool = typer.Option(..., "--approve/--reject", help="批准或拒绝工程变更"),
    note: str = typer.Option("", help="审批意见"),
) -> None:
    """批准变更，恢复工作流并执行 Godot Headless 验证。"""
    with GodotForgeRuntime() as runtime:
        print_response(runtime.resume(thread_id, approved, note))


@app.command()
def state(thread_id: str = typer.Argument(..., help="构建 ID")) -> None:
    """查看需求、计划、验证结果与执行轨迹。"""
    with GodotForgeRuntime() as runtime:
        typer.echo(json.dumps(runtime.get_state(thread_id), ensure_ascii=False, indent=2))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8001) -> None:
    """启动 FastAPI 服务。"""
    import uvicorn

    uvicorn.run("godot_forge.api:app", host=host, port=port)


@app.command()
def evaluate() -> None:
    """在隔离目录中运行真实构建评估。"""
    typer.echo(json.dumps(run_evaluation(Settings()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
