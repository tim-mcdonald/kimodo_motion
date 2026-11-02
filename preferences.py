import bpy
from bpy.types import AddonPreferences, PropertyGroup
from bpy.props import (
    StringProperty,
    IntProperty,
    BoolProperty,
    EnumProperty,
    FloatProperty,
    PointerProperty,
    CollectionProperty,
)
import os
import sys


# ── Translation API provider presets ──
# Tuple: (id, label, base_url, default_model)
TRANSLATE_PROVIDERS = [
    ("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    (
        "openrouter",
        "OpenRouter",
        "https://openrouter.ai/api/v1",
        "deepseek/deepseek-chat",
    ),
    ("moonshot", "Moonshot (Kimi)", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    (
        "qwen",
        "Qwen (DashScope)",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-turbo",
    ),
    ("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("custom", "Custom", "", ""),
]


def default_venv_path() -> str:
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "KimodoMotionRuntime", "venv")
    return os.path.join(os.path.expanduser("~"), ".kimodo_venv")


def _apply_provider_preset(prefs):
    """When user picks a provider from dropdown, auto-fill base_url + model."""
    for pid, _label, url, default_model in TRANSLATE_PROVIDERS:
        if prefs.translate_provider == pid:
            if pid != "custom" and url:
                prefs.translate_api_url = url
            if pid != "custom" and default_model and not prefs.translate_model.strip():
                prefs.translate_model = default_model
            # Auto-fill model even if blank; user can override
            if pid != "custom" and default_model:
                prefs.translate_model = default_model
            break


def _get_fetched_models_items(self, context):
    """EnumProperty items callback — parses cache string into dropdown items."""
    cache = self.translate_model_cache or ""
    if not cache:
        return ["", "(none fetched)", "Click Fetch to pull the model list"]
    items = []
    for i, m in enumerate(cache.split("|")):
        m = m.strip()
        if m:
            items.append((m, m, ""))
    return items or [("", "(empty)", "The API returned no models")]


def _on_model_pick(self, context):
    """When user picks from dropdown, copy into the editable model field."""
    if self.translate_model_pick:
        self.translate_model = self.translate_model_pick


# ── Duration ↔ Frames 双向同步（Kimodo 官方 fps=30, 公式 frames = secs * 30 - 1）──
# 用 _syncing 哨兵避免 callback 互相触发死循环
KIMODO_FPS = 30
_syncing = False


def secs_to_frames(s: float) -> int:
    return max(59, min(299, int(round(s * KIMODO_FPS - 1))))


def frames_to_secs(f: int) -> float:
    return round((f + 1) / KIMODO_FPS, 2)


def _sync_from_duration(self, context):
    global _syncing
    if _syncing:
        return
    _syncing = True
    try:
        self.kimodo_num_frames = secs_to_frames(self.kimodo_duration)
    finally:
        _syncing = False


def _sync_from_frames(self, context):
    global _syncing
    if _syncing:
        return
    _syncing = True
    try:
        self.kimodo_duration = frames_to_secs(self.kimodo_num_frames)
    finally:
        _syncing = False


class KimodoConstraintItem(PropertyGroup):
    label: StringProperty(name="Name", default="")
    constraint_type: EnumProperty(
        name="Type",
        items=[
            ("root2d", "Root XZ", "Root path or waypoints on the ground"),
            ("fullbody", "Full Body", "Full-body pose constraint via the SOMA proxy"),
            ("left_hand", "L Hand", "Left hand target"),
            ("right_hand", "R Hand", "Right hand target"),
            ("left_foot", "L Foot", "Left foot target"),
            ("right_foot", "R Foot", "Right foot target"),
        ],
        default="root2d",
    )
    frame: IntProperty(name="Frame", default=1, min=0)
    marker_object: PointerProperty(name="Object", type=bpy.types.Object)
    enabled: BoolProperty(name="Enabled", default=True)
    include_heading: BoolProperty(name="Heading", default=False)
    heading_angle: FloatProperty(name="Angle", default=0.0, subtype="ANGLE")


class KimodoMotionSegment(PropertyGroup):
    prompt: StringProperty(name="Prompt", default="A person walks forward.")
    start_frame: IntProperty(name="Start Frame", default=1, min=0)
    end_frame: IntProperty(name="End Frame", default=180, min=1)
    enabled: BoolProperty(name="Enabled", default=True)
    seed: IntProperty(name="Seed", default=-1, min=-1)


class KimodoPreferences(AddonPreferences):
    # Must equal the add-on's package name. As a submodule of the add-on root this
    # module's __package__ is exactly that — works whether loaded as a legacy add-on
    # ("kimodo_motion") or an extension ("bl_ext.<repo>.kimodo_motion").
    bl_idname = __package__

    server_host: StringProperty(
        name="Server Host",
        default="127.0.0.1",
        description="Kimodo server address (keep localhost for safety)",
    )
    server_port: IntProperty(
        name="Port",
        default=8790,
        min=1024,
        max=65535,
        description="Kimodo server port",
    )
    venv_path: StringProperty(
        name="Virtual Env Path",
        default=default_venv_path(),
        subtype="DIR_PATH",
        description="Path to the Kimodo Python virtual environment",
    )
    auto_start_server: BoolProperty(
        name="Auto-Start Server",
        default=True,
        description="Start the Kimodo server automatically when generating",
    )
    model_name: EnumProperty(
        name="Model",
        items=[
            (
                "Kimodo-SOMA-RP-v1.2",
                "SOMA RP v1.2 (default)",
                "Retrained after fixing the train/test split (v1.1 leaked BONES-SEED test data)",
            ),
            (
                "Kimodo-SOMA-RP-v1",
                "SOMA RP v1 (full 700h)",
                "Highest quality, full Rigplay dataset",
            ),
            ("Kimodo-SOMA-RP-v1.1", "SOMA RP v1.1", "Leaked BONES-SEED test data, not recommended"),
            ("Kimodo-SOMA-SEED-v1", "SOMA SEED (288h)", "Public dataset"),
        ],
        default="Kimodo-SOMA-RP-v1.2",
        description="Kimodo model variant",
    )
    fbx_retarget_timeout: IntProperty(
        name="Retarget Timeout (s)",
        default=60,
        min=10,
        max=600,
        description="FBX retarget subprocess timeout (per sample)",
    )
    keep_retarget_temp: BoolProperty(
        name="Keep Temp Files",
        default=False,
        description="Debug: keep the temporary FBX and mapping files (otherwise deleted after generation)",
    )

    # ── 中文翻译（生成时自动 zh→en）──
    translate_mode: EnumProperty(
        name="Chinese Translation",
        items=[
            ("OFF", "Off", "Submit the prompt as-is (Kimodo works best with English)"),
            (
                "DICT",
                "Dict Only (instant)",
                "Built-in dictionary of ~60 common actions; instant match, no API needed",
            ),
            (
                "API",
                "Dict + AI (recommended)",
                "Dict first; misses go to an OpenAI-compatible API (DeepSeek, etc.)",
            ),
        ],
        default="DICT",
        description="How Chinese prompts are handled",
    )
    translate_provider: EnumProperty(
        name="API Preset",
        items=[
            ("deepseek", "DeepSeek", "https://api.deepseek.com/v1"),
            ("openrouter", "OpenRouter", "https://openrouter.ai/api/v1"),
            ("moonshot", "Moonshot (Kimi)", "https://api.moonshot.cn/v1"),
            ("qwen", "Qwen (DashScope)", "https://dashscope.aliyuncs.com"),
            ("openai", "OpenAI", "https://api.openai.com/v1"),
            ("custom", "Custom", "Fill in the Base URL manually"),
        ],
        default="deepseek",
        description="Auto-fills the Base URL and a suggested model (Fetch pulls the full list)",
        update=lambda self, ctx: _apply_provider_preset(self),
    )
    translate_api_url: StringProperty(
        name="API Base URL",
        default="https://api.deepseek.com/v1",
        description="Base URL of an OpenAI-compatible API",
    )
    translate_api_key: StringProperty(
        name="API Key",
        default="",
        subtype="PASSWORD",
        description="Get it from the provider's console",
    )
    translate_model: StringProperty(
        name="Model",
        default="deepseek-chat",
        description="Model name; click Fetch to pull the available list from the API",
    )
    translate_model_cache: StringProperty(
        name="_cache",
        default="",
        options={"HIDDEN"},
        description="Fetched model list cache (| separated)",
    )
    translate_model_pick: EnumProperty(
        name="Pick Model",
        items=_get_fetched_models_items,
        description="Pick from the model list returned by the API",
        update=lambda self, ctx: _on_model_pick(self, ctx),
    )
    translate_timeout: IntProperty(
        name="API Timeout (s)",
        default=15,
        min=3,
        max=120,
    )
    translate_status: StringProperty(
        name="_status",
        default="",
        options={"HIDDEN"},
        description="Last test/fetch status (shown in draw)",
    )

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="Server", icon="WORLD")
        row = box.row()
        row.prop(self, "server_host")
        row.prop(self, "server_port")
        box.prop(self, "auto_start_server")
        box.prop(self, "venv_path")

        box = layout.box()
        box.label(text="Generation", icon="ARMATURE_DATA")
        box.prop(self, "model_name")

        box = layout.box()
        box.label(text="Retargeting", icon="CON_ARMATURE")
        box.prop(self, "fbx_retarget_timeout")
        box.prop(self, "keep_retarget_temp")

        box = layout.box()
        box.label(text="Chinese Translation", icon="OUTLINER_DATA_FONT")
        box.prop(self, "translate_mode")
        if self.translate_mode == "API":
            row = box.row()
            row.prop(self, "translate_provider")
            sub = box.column(align=True)
            sub.prop(self, "translate_api_url")
            sub.prop(self, "translate_api_key")
            row = sub.row(align=True)
            row.prop(self, "translate_model")
            row.operator(
                "kimodo.translate_fetch_models", text="Fetch", icon="FILE_REFRESH"
            )
            # Fetched-models picker (只在有缓存时显示)
            if self.translate_model_cache:
                sub.prop(self, "translate_model_pick", text="From List")
            row = box.row(align=True)
            row.operator("kimodo.translate_test", icon="CHECKMARK")
            row.prop(self, "translate_timeout")
            if self.translate_status:
                box.label(text=self.translate_status, icon="INFO")
            box.label(
                text="After filling in the API key, use the menu > Save Preferences (so it survives restarts)",
                icon="FILE_TICK",
            )

        box = layout.box()
        box.label(text="Status", icon="INFO")
        box.label(text=f"Server: http://{self.server_host}:{self.server_port}")


def get_prefs() -> KimodoPreferences:
    return bpy.context.preferences.addons[__package__].preferences


def get_server_url() -> str:
    prefs = get_prefs()
    return f"http://{prefs.server_host}:{prefs.server_port}"


# ── Scene properties for generation parameters ──


def register_props():
    bpy.types.Scene.kimodo_retarget_preset = EnumProperty(
        name="Bone Mapping",
        items=[
            ("AUTO", "Auto Match", "Match by bone name (case-insensitive)"),
            ("vroid", "VRoid", "VRoid Studio / VRM models"),
            ("mmd", "MMD", "MikuMikuDance models"),
            ("mixamo", "Mixamo", "Mixamo rig models"),
        ],
        default="AUTO",
        description="Retarget bone mapping preset",
    )
    bpy.types.Scene.kimodo_prompt = StringProperty(
        name="Prompt",
        default="A person walks forward.",
        description="Describe the motion to generate (English works best)",
    )
    # Kimodo 官方约束：fps=30 固定, duration ∈ [2.0, 10.0]s, 即 num_frames ∈ [59, 299]
    bpy.types.Scene.kimodo_length_mode = EnumProperty(
        name="Length Input",
        items=[
            ("DURATION", "Seconds", "Enter seconds (frames = seconds * 30 - 1)"),
            ("FRAMES", "Frames", "Enter frames directly (seconds = frames / 30)"),
        ],
        default="DURATION",
        description="Control the animation length in seconds or frames",
    )
    bpy.types.Scene.kimodo_duration = bpy.props.FloatProperty(
        name="Duration (s)",
        default=6.0,
        min=2.0,
        max=10.0,
        step=10,
        precision=2,
        description="Animation duration (Kimodo official range 2-10s, default 6s)",
        update=_sync_from_duration,
    )
    bpy.types.Scene.kimodo_num_frames = IntProperty(
        name="Frames",
        default=179,  # 6.0s × 30 − 1
        min=59,  # 2.0s × 30 − 1
        max=299,  # 10.0s × 30 − 1
        description="Total frames (Kimodo official 59-299, default 179 = ~6s @ 30fps)",
        update=_sync_from_frames,
    )
    bpy.types.Scene.kimodo_num_samples = IntProperty(
        name="Variants",
        default=1,
        min=1,
        max=8,
        description="Generate several different motion variants",
    )
    bpy.types.Scene.kimodo_seed = IntProperty(
        name="Seed",
        default=-1,
        min=-1,
        description="Random seed (-1 = random)",
    )
    bpy.types.Scene.kimodo_diffusion_steps = IntProperty(
        name="Diffusion Steps",
        default=100,
        min=10,
        max=200,
        description="Denoising steps (more = better quality, slower)",
    )
    bpy.types.Scene.kimodo_action_start_frame = IntProperty(
        name="Start Frame",
        default=0,
        min=0,
        description="Frame where the generated Action is written; constraints/curves use this as Kimodo frame 0",
    )
    bpy.types.Scene.kimodo_enable_constraints = BoolProperty(
        name="Enable Constraints",
        default=False,
        description="Send the path curve / markers as Kimodo official constraints",
    )
    bpy.types.Scene.kimodo_motion_constraints = CollectionProperty(
        type=KimodoConstraintItem
    )
    bpy.types.Scene.kimodo_constraint_index = IntProperty(
        name="Constraint Index",
        default=0,
        min=0,
    )
    bpy.types.Scene.kimodo_auto_canonicalize = BoolProperty(
        name="Auto Canonical Origin",
        default=True,
        description="Use the earliest root/fullbody constraint point as the Kimodo XZ origin",
    )
    bpy.types.Scene.kimodo_post_processing = BoolProperty(
        name="Official Post-Processing",
        default=False,
        description=(
            "Try to enable Kimodo motion_correction post-processing; the native extension is not installed by default on macOS/Apple Silicon, and the server skips it"
            if sys.platform == "darwin"
            else "Try to enable Kimodo motion_correction post-processing to reduce constraint drift / foot sliding"
        ),
    )
    bpy.types.Scene.kimodo_text_cfg = FloatProperty(
        name="Text CFG",
        default=2.0,
        min=0.0,
        max=20.0,
        description="Text prompt guidance strength",
    )
    bpy.types.Scene.kimodo_constraint_cfg = FloatProperty(
        name="Constraint CFG",
        default=2.0,
        min=0.0,
        max=20.0,
        description="Constraint guidance strength",
    )
    bpy.types.Scene.kimodo_root_margin = FloatProperty(
        name="Root Margin",
        default=0.04,
        min=0.0,
        max=1.0,
        precision=3,
        description="Root tolerance (meters) for motion_correction post-processing; no effect when post-processing is off or unavailable",
    )
    bpy.types.Scene.kimodo_num_transition_frames = IntProperty(
        name="Transition Frames",
        default=5,
        min=1,
        max=30,
        description="Transition frames between multi-prompt segments",
    )
    bpy.types.Scene.kimodo_path_curve = PointerProperty(
        name="Path Curve",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == "CURVE",
    )
    bpy.types.Scene.kimodo_path_waypoints = IntProperty(
        name="Waypoints",
        default=8,
        min=2,
        max=30,
        description="Arc-length samples along the curve, used as root2d constraints",
    )
    bpy.types.Scene.kimodo_path_start_frame = IntProperty(
        name="Path Start",
        default=0,
        min=0,
    )
    bpy.types.Scene.kimodo_path_end_frame = IntProperty(
        name="Path End",
        default=179,
        min=1,
    )
    bpy.types.Scene.kimodo_constraint_json_preview = StringProperty(
        name="Constraint JSON",
        default="",
        options={"HIDDEN"},
    )
    bpy.types.Scene.kimodo_motion_segments = CollectionProperty(
        type=KimodoMotionSegment
    )
    bpy.types.Scene.kimodo_segment_index = IntProperty(name="Segment Index", default=0, min=0)
    bpy.types.Scene.kimodo_translation_note = StringProperty(
        name="_translation_note",
        default="",
        description="Translation result/status from the last generation (read-only display)",
    )


def unregister_props():
    props = [
        "kimodo_retarget_preset",
        "kimodo_prompt",
        "kimodo_length_mode",
        "kimodo_duration",
        "kimodo_num_frames",
        "kimodo_num_samples",
        "kimodo_seed",
        "kimodo_diffusion_steps",
        "kimodo_action_start_frame",
        "kimodo_enable_constraints",
        "kimodo_motion_constraints",
        "kimodo_constraint_index",
        "kimodo_auto_canonicalize",
        "kimodo_post_processing",
        "kimodo_text_cfg",
        "kimodo_constraint_cfg",
        "kimodo_root_margin",
        "kimodo_num_transition_frames",
        "kimodo_path_curve",
        "kimodo_path_waypoints",
        "kimodo_path_start_frame",
        "kimodo_path_end_frame",
        "kimodo_constraint_json_preview",
        "kimodo_motion_segments",
        "kimodo_segment_index",
        "kimodo_translation_note",
    ]
    for p in props:
        if hasattr(bpy.types.Scene, p):
            delattr(bpy.types.Scene, p)


classes = [KimodoConstraintItem, KimodoMotionSegment, KimodoPreferences]
