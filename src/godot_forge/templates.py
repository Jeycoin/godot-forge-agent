import json

from godot_forge.schemas import FileChange


def file_change(path: str, content: str, purpose: str) -> FileChange:
    return FileChange(path=path, content=content.strip() + "\n", purpose=purpose)


def project_file(title: str) -> FileChange:
    content = f"""
config_version=5

[application]
config/name={json.dumps(title, ensure_ascii=False)}
run/main_scene="res://scenes/main.tscn"
config/features=PackedStringArray("4.3", "GL Compatibility")

[display]
window/size/viewport_width=960
window/size/viewport_height=540
window/size/window_width_override=960
window/size/window_height_override=540

[rendering]
renderer/rendering_method="gl_compatibility"
"""
    return file_change("project.godot", content, "Godot 4 工程配置与主场景入口")


def main_scene_file() -> FileChange:
    return file_change(
        "scenes/main.tscn",
        """
[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scripts/main.gd" id="1_main"]

[node name="Main" type="Node2D"]
script = ExtResource("1_main")
""",
        "可运行的主场景",
    )


def player_file() -> FileChange:
    return file_change(
        "scripts/player.gd",
        """
class_name SurvivorPlayer
extends CharacterBody2D

signal died

const SPEED := 260.0
const MAX_HEALTH := 100

var health := MAX_HEALTH

func _ready() -> void:
    var collision := CollisionShape2D.new()
    var circle := CircleShape2D.new()
    circle.radius = 16.0
    collision.shape = circle
    add_child(collision)

func _physics_process(_delta: float) -> void:
    var direction := Vector2.ZERO
    direction.x = Input.get_axis("ui_left", "ui_right")
    direction.y = Input.get_axis("ui_up", "ui_down")
    if Input.is_key_pressed(KEY_A):
        direction.x -= 1.0
    if Input.is_key_pressed(KEY_D):
        direction.x += 1.0
    if Input.is_key_pressed(KEY_W):
        direction.y -= 1.0
    if Input.is_key_pressed(KEY_S):
        direction.y += 1.0
    velocity = direction.normalized() * SPEED
    move_and_slide()
    position = position.clamp(Vector2(16.0, 16.0), Vector2(944.0, 524.0))

func take_damage(amount: int) -> void:
    health = maxi(0, health - amount)
    if health == 0:
        died.emit()

func _draw() -> void:
    draw_circle(Vector2.ZERO, 16.0, Color("64d8ff"))
    draw_arc(Vector2.ZERO, 20.0, 0.0, TAU, 32, Color("d5f6ff"), 2.0)
    draw_line(Vector2.ZERO, Vector2(24.0, 0.0), Color("ffffff"), 3.0)
""",
        "玩家移动、生命值和受伤逻辑",
    )


def enemy_file() -> FileChange:
    return file_change(
        "scripts/enemy.gd",
        """
class_name ChaserEnemy
extends CharacterBody2D

var target: Node2D
var speed := 110.0
var damage := 10
var _cooldown := 0.0

func _ready() -> void:
    add_to_group("enemies")
    var collision := CollisionShape2D.new()
    var circle := CircleShape2D.new()
    circle.radius = 14.0
    collision.shape = circle
    add_child(collision)

func _physics_process(delta: float) -> void:
    if not is_instance_valid(target):
        return
    var direction := (target.global_position - global_position).normalized()
    velocity = direction * speed
    move_and_slide()
    _cooldown = maxf(0.0, _cooldown - delta)
    if global_position.distance_to(target.global_position) < 32.0 and _cooldown <= 0.0:
        if target.has_method("take_damage"):
            target.take_damage(damage)
        _cooldown = 1.0

func _draw() -> void:
    draw_circle(Vector2.ZERO, 14.0, Color("ff5d73"))
    draw_circle(Vector2.ZERO, 6.0, Color("5c1f32"))
""",
        "敌人生成后的追踪与接触伤害",
    )


def hud_file() -> FileChange:
    return file_change(
        "scripts/hud.gd",
        """
class_name SurvivalHUD
extends CanvasLayer

var stats_label: Label
var message_label: Label

func _ready() -> void:
    stats_label = Label.new()
    stats_label.position = Vector2(20.0, 16.0)
    stats_label.add_theme_font_size_override("font_size", 22)
    add_child(stats_label)
    message_label = Label.new()
    message_label.position = Vector2(300.0, 220.0)
    message_label.add_theme_font_size_override("font_size", 32)
    add_child(message_label)

func update_stats(health: int, score: int, enemies: int) -> void:
    stats_label.text = "HP: %d   SCORE: %d   ENEMIES: %d" % [health, score, enemies]

func show_game_over(final_score: int) -> void:
    message_label.text = "GAME OVER\\nScore: %d\\nPress Enter to restart" % final_score
""",
        "生命值、分数与游戏结束界面",
    )


def main_script_file() -> FileChange:
    return file_change(
        "scripts/main.gd",
        """
extends Node2D

const PlayerScript = preload("res://scripts/player.gd")
const EnemyScript = preload("res://scripts/enemy.gd")
const HUDScript = preload("res://scripts/hud.gd")

var player
var hud
var score := 0.0
var game_over := false
var rng := RandomNumberGenerator.new()
var spawn_timer: Timer

func _ready() -> void:
    rng.randomize()
    _create_background()
    player = PlayerScript.new()
    player.position = Vector2(480.0, 270.0)
    add_child(player)
    player.died.connect(_on_player_died)
    hud = HUDScript.new()
    add_child(hud)
    spawn_timer = Timer.new()
    spawn_timer.wait_time = 1.2
    spawn_timer.timeout.connect(_spawn_enemy)
    add_child(spawn_timer)
    spawn_timer.start()
    for index in 3:
        _spawn_enemy()
    if "--smoke-test" in OS.get_cmdline_user_args():
        _run_smoke_test.call_deferred()

func _process(delta: float) -> void:
    if not game_over:
        score += delta
    var enemies := get_tree().get_nodes_in_group("enemies").size()
    hud.update_stats(player.health, int(score), enemies)

func _create_background() -> void:
    var background := ColorRect.new()
    background.color = Color("101828")
    background.size = Vector2(960.0, 540.0)
    add_child(background)

func _spawn_enemy() -> void:
    if game_over or not is_instance_valid(player):
        return
    var enemy := EnemyScript.new()
    var side := rng.randi_range(0, 3)
    match side:
        0:
            enemy.position = Vector2(rng.randf_range(0.0, 960.0), -20.0)
        1:
            enemy.position = Vector2(980.0, rng.randf_range(0.0, 540.0))
        2:
            enemy.position = Vector2(rng.randf_range(0.0, 960.0), 560.0)
        _:
            enemy.position = Vector2(-20.0, rng.randf_range(0.0, 540.0))
    enemy.target = player
    add_child(enemy)

func _on_player_died() -> void:
    game_over = true
    spawn_timer.stop()
    hud.show_game_over(int(score))
    for enemy in get_tree().get_nodes_in_group("enemies"):
        enemy.set_physics_process(false)

func _unhandled_input(event: InputEvent) -> void:
    if game_over and event is InputEventKey and event.pressed and event.keycode == KEY_ENTER:
        get_tree().reload_current_scene()

func _run_smoke_test() -> void:
    await get_tree().physics_frame
    await get_tree().process_frame
    await get_tree().process_frame
    var enemy_count := get_tree().get_nodes_in_group("enemies").size()
    var player_ready: bool = player != null
    var hud_ready: bool = not hud.stats_label.text.is_empty()
    if not player_ready or enemy_count < 3 or not hud_ready:
        push_error(
            "SMOKE_TEST_FAILED: player=%s enemies=%d hud_ready=%s"
            % [player_ready, enemy_count, hud_ready]
        )
        get_tree().quit(1)
        return
    print("SMOKE_TEST_OK: player, enemies, HUD, physics and game loop initialized")
    get_tree().quit(0)
""",
        "游戏主循环、敌人生成、状态管理和自动冒烟测试",
    )


def readme_file(title: str) -> FileChange:
    return file_change(
        "README.md",
        f"""
# {title}

由 GodotForge 生成的 Godot 4 俯视角生存原型。

## 运行

使用 Godot 4.3 或更高版本导入 `project.godot`，按 F6/F5 运行主场景。

- WASD 或方向键：移动
- 避开追踪敌人，生存时间越长分数越高
- 游戏结束后按 Enter 重开

## 自动验证

```bash
godot --headless --path . -- --smoke-test
```

成功时输出 `SMOKE_TEST_OK` 并以退出码 0 结束。
""",
        "生成游戏的操作和验证说明",
    )


def changes_for(specialist: str, title: str) -> list[FileChange]:
    if specialist == "gameplay":
        return [player_file(), enemy_file()]
    if specialist == "scene":
        return [project_file(title), main_scene_file(), main_script_file()]
    if specialist == "interface":
        return [hud_file(), readme_file(title)]
    raise ValueError(f"Unknown specialist: {specialist}")


def all_changes(title: str) -> list[FileChange]:
    return [
        change
        for specialist in ("gameplay", "scene", "interface")
        for change in changes_for(specialist, title)
    ]
