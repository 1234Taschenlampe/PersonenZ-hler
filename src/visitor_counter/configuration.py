from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised on minimal systems
    yaml = None  # type: ignore[assignment]


@dataclass
class CameraConfig:
    camera_id: str
    device: str | None = None
    width: int = 1280
    height: int = 720
    fps: int = 30
    role: str = "entrance"
    display_name: str = "EINGANG - Kamera 1"
    line_start: tuple[int, int] = (160, 360)
    line_end: tuple[int, int] = (1120, 360)
    in_positive_side: bool = True
    entry_zone: str = "near"
    exit_zone: str = "far"
    masks: list[list[tuple[int, int]]] = field(default_factory=list)
    entry_direction: str = "A_to_B"  # "A_to_B", "B_to_A", or "none"
    exit_direction: str = "B_to_A"   # "A_to_B", "B_to_A", or "none"


@dataclass
class ModelConfig:
    hef_path: str = "models/yolo26m_detection_hailo10h_640.hef"
    model_name: str = "YOLO26m COCO Detection HAILO10H (person filter)"
    target_model_name: str = "YOLO26m COCO Detection HAILO10H (person filter)"
    target_hef_path: str = "models/yolo26m_detection_hailo10h_640.hef"
    custom_target_model_name: str = "YOLO26m COCO Detection HAILO10H (person filter)"
    custom_target_hef_path: str = "models/yolo26m_detection_hailo10h_640.hef"
    require_custom_yolo26m: bool = True
    detector_fallback_enabled: bool = False
    active_detector_policy: str = "Only the official YOLO26m COCO HAILO10H detection HEF may run; inference filters COCO class 0 person and missing or invalid HEF disables detection and counting."
    detector_candidates: list[dict[str, str]] = field(
        default_factory=lambda: [
            {"name": "YOLO26m COCO Detection HAILO10H (person filter)", "path": "models/yolo26m_detection_hailo10h_640.hef", "role": "required_runtime"},
        ]
    )
    reid_model_name: str = "OSNet x1.0 HAILO10H"
    reid_hef_path: str = "models/osnet_x1_0_hailo10h.hef"
    reid_required: bool = True
    postprocess_onnx_path: str = "models/yolo26m_postprocessing.onnx"
    postprocess_config_path: str = "models/config_onnx_yolo26m.json"
    output_format: str = "yolo26_detection"
    model_type: str = "Detection"
    input_size: int = 640
    confidence_threshold: float = 0.20
    iou_threshold: float = 0.60
    max_detections: int = 300
    allow_fallback: bool = False


@dataclass
class TrackingConfig:
    tracker: str = "bytetrack"
    max_lost_frames: int = 20
    min_hits_before_counting: int = 5
    min_confirmed_hits: int = 5
    iou_match_threshold: float = 0.20
    
    # Robust crossing parameters
    min_confirmed_track_hits: int = 5
    min_stable_zone_frames: int = 3
    count_cooldown_seconds: float = 2.0
    minimum_confidence: float = 0.35
    zone_hysteresis_pixels: float = 25.0
    maximum_track_age: int = 30
    minimum_bbox_area: float = 1000.0


@dataclass
class IdentityConfig:
    match_window_seconds: float = 6.0
    stale_seconds: float = 3.0
    reid_threshold: float = 0.62
    hysteresis_seconds: float = 1.5
    reid_update_interval_seconds: float = 2.0
    cache_ttl_seconds: float = 1800.0
    live_entry_min_frames: int = 3
    live_exit_grace_seconds: float = 2.0
    live_min_confidence: float = 0.35
    live_min_bbox_area: float = 2500.0
    live_min_aspect_ratio: float = 0.18
    live_max_aspect_ratio: float = 1.40


@dataclass
class ConsensusConfig:
    enabled: bool = True
    transition_window_seconds: float = 3.0
    uncertain_window_seconds: float = 6.0
    expected_travel_seconds: float = 1.5
    bbox_area_ratio_tolerance: float = 0.70
    event_lock_seconds: float = 8.0


@dataclass
class TimeoutConfig:
    presence_timeout_enabled: bool = True
    presence_timeout_minutes: int = 60


@dataclass
class DatabaseConfig:
    path: str = "data/person_counter.sqlite3"
    store_video_frames: bool = False
    store_events: bool = False
    retention_hours: int = 24
    encryption_required: bool = True
    encryption_key_env: str = "VISITOR_COUNTER_DATA_KEY"
    encryption_key_file: str = ""


@dataclass
class DisplayConfig:
    display_raw_frames_only: bool = False
    raw_frame_overlay: bool = True
    show_camera_preview: bool = False
    anonymization_mode: str = "full_frame"
    pixel_size: int = 24


@dataclass
class PrivacyConfig:
    enabled: bool = True
    local_processing_only: bool = True
    telemetry_enabled: bool = False
    video_stream_enabled: bool = False
    remove_stream_frames_on_shutdown: bool = True
    privacy_notice_acknowledged: bool = False
    privacy_notice_acknowledged_at: str = ""
    legal_basis: str = ""
    purpose: str = "anonymous occupancy counting"
    controller_name: str = ""
    controller_contact: str = ""
    consent_required: bool = False
    consent_recorded: bool = False


@dataclass
class ApiConfig:
    enabled: bool = True
    bind_host: str = "127.0.0.1"
    port: int = 8766
    require_auth: bool = True
    viewer_token_env: str = "VISITOR_COUNTER_VIEWER_TOKEN"
    operator_token_env: str = "VISITOR_COUNTER_OPERATOR_TOKEN"
    admin_token_env: str = "VISITOR_COUNTER_ADMIN_TOKEN"
    minimum_token_length: int = 32
    tls_certificate: str = ""
    tls_private_key: str = ""
    allowed_origins: list[str] = field(default_factory=list)
    max_requests_per_minute: int = 120
    audit_retention_days: int = 30


@dataclass
class AppConfig:
    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "camera_1": CameraConfig(
                camera_id="camera_1",
                role="entrance",
                display_name="EINGANG - Kamera 1",
            ),
            "camera_2": CameraConfig(
                camera_id="camera_2",
                role="exit",
                display_name="AUSGANG - Kamera 2",
            ),
        }
    )
    model: ModelConfig = field(default_factory=ModelConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    consensus: ConsensusConfig = field(default_factory=ConsensusConfig)
    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    api: ApiConfig = field(default_factory=ApiConfig)


def _camera_from_dict(camera_id: str, data: dict[str, Any]) -> CameraConfig:
    item = dict(data)
    item["camera_id"] = camera_id
    if "role" not in item:
        item["role"] = "entrance" if camera_id == "camera_1" else "exit"
    if "display_name" not in item:
        item["display_name"] = "EINGANG - Kamera 1" if camera_id == "camera_1" else "AUSGANG - Kamera 2"
    for key in ("line_start", "line_end"):
        if key in item and isinstance(item[key], list):
            item[key] = tuple(item[key])
    return CameraConfig(**item)


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path) -> AppConfig:
    default = asdict(AppConfig())
    if path.exists():
        if yaml is None:
            raise RuntimeError("PyYAML is required to read config/config.yaml")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        merged = _deep_update(default, raw)
    else:
        merged = default
    cameras = {
        camera_id: _camera_from_dict(camera_id, camera_data)
        for camera_id, camera_data in merged.get("cameras", {}).items()
    }
    model_data = dict(merged.get("model", {}))
    forbidden = {"models/yolo26m_pose_hailo10h_640.hef", "models/yolov8s_pose_h10.hef", "models/yolov8s_pose_h8.hef"}
    if model_data.get("hef_path") in forbidden:
        model_data.update(asdict(ModelConfig()))
    return AppConfig(
        cameras=cameras,
        model=ModelConfig(**model_data),
        tracking=TrackingConfig(**merged.get("tracking", {})),
        identity=IdentityConfig(**merged.get("identity", {})),
        consensus=ConsensusConfig(**merged.get("consensus", {})),
        timeout=TimeoutConfig(**merged.get("timeout", {})),
        database=DatabaseConfig(**merged.get("database", {})),
        display=DisplayConfig(**merged.get("display", {})),
        privacy=PrivacyConfig(**merged.get("privacy", {})),
        api=ApiConfig(**merged.get("api", {})),
    )


def save_config(config: AppConfig, path: Path) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to write config/config.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(asdict(config), sort_keys=False), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def validate_config(config: AppConfig) -> list[str]:
    errors: list[str] = []
    if len(config.cameras) != 2:
        errors.append("Exactly two camera configs are required.")
    roles = {camera.role for camera in config.cameras.values()}
    if roles != {"entrance", "exit"}:
        errors.append("Camera roles must contain exactly one entrance and one exit camera.")
    forbidden_paths = {"models/yolo26m_pose_hailo10h_640.hef", "models/yolov8s_pose_h10.hef", "models/yolov8s_pose_h8.hef"}
    if config.model.hef_path in forbidden_paths:
        errors.append("Pose HEFs must never be used as detection models.")
    if config.model.allow_fallback or config.model.detector_fallback_enabled:
        errors.append("Model fallback must be disabled for production YOLO26 operation.")
    if not config.model.require_custom_yolo26m:
        errors.append("Production runtime must require the approved YOLO26 HEF.")
    if config.model.hef_path != config.model.custom_target_hef_path:
        errors.append(f"Configured detector HEF must be {config.model.custom_target_hef_path}.")
    if config.model.target_hef_path != config.model.custom_target_hef_path:
        errors.append("Target detector HEF must be the approved YOLO26 COCO detection HEF with person filtering.")
    if config.model.model_name != config.model.custom_target_model_name:
        errors.append(f"Active detector name must be {config.model.custom_target_model_name}.")
    if config.model.output_format == "yolo26_detection" and (
        not config.model.postprocess_onnx_path or not config.model.postprocess_config_path
    ):
        errors.append("YOLO26 detection requires ONNX postprocess model and config paths.")
    if not 0.0 < config.model.confidence_threshold < 1.0:
        errors.append("Model confidence threshold must be between 0 and 1.")
    if config.model.input_size <= 0:
        errors.append("Model input size must be positive.")
    if config.model.max_detections <= 0:
        errors.append("Model max_detections must be positive.")
    if config.tracking.max_lost_frames < 0:
        errors.append("Tracking max_lost_frames must not be negative.")
    if config.identity.reid_threshold <= 0 or config.identity.reid_threshold > 1:
        errors.append("Identity threshold must be in (0, 1].")
    if config.consensus.transition_window_seconds <= 0:
        errors.append("Consensus transition window must be positive.")
    if config.timeout.presence_timeout_minutes <= 0:
        errors.append("Presence timeout minutes must be positive.")
    if config.database.store_video_frames:
        errors.append("Persisting video frames is prohibited; keep database.store_video_frames disabled.")
    if config.database.retention_hours <= 0 or config.database.retention_hours > 168:
        errors.append("Database retention_hours must be between 1 and 168 hours.")
    if config.database.store_events and config.database.encryption_required and not (
        config.database.encryption_key_env or config.database.encryption_key_file
    ):
        errors.append("Stored events require an encryption key environment variable or key file.")
    if config.display.anonymization_mode not in {"full_frame", "persons", "none"}:
        errors.append("Display anonymization_mode must be full_frame, persons, or none.")
    if config.privacy.enabled and config.display.show_camera_preview and config.display.anonymization_mode == "none":
        errors.append("Privacy mode forbids an unmasked camera preview.")
    if config.privacy.video_stream_enabled and config.display.anonymization_mode != "full_frame":
        errors.append("Remote video requires full-frame anonymization because license plates are not detected.")
    if not config.privacy.local_processing_only:
        errors.append("Local-only processing is a mandatory secure default.")
    if config.privacy.telemetry_enabled:
        errors.append("External telemetry must remain disabled.")
    if config.privacy.consent_required and not config.privacy.consent_recorded:
        errors.append("Consent is configured as the legal basis but has not been recorded.")
    if not 1 <= config.api.port <= 65_535:
        errors.append("API port must be between 1 and 65535.")
    if config.api.minimum_token_length < 32:
        errors.append("API tokens must be at least 32 characters long.")
    if config.api.bind_host not in {"127.0.0.1", "::1", "localhost"} and not (
        config.api.tls_certificate and config.api.tls_private_key and config.api.require_auth
    ):
        errors.append("Non-loopback API binding requires TLS and authentication.")
    return errors


def privacy_readiness_errors(config: AppConfig) -> list[str]:
    """Return operator actions required before camera processing may start."""
    errors = validate_config(config)
    if not config.privacy.enabled:
        errors.append("Privacy mode must be enabled for production camera processing.")
    if not config.privacy.privacy_notice_acknowledged:
        errors.append("Confirm that the required privacy notice is visibly installed.")
    if not config.privacy.privacy_notice_acknowledged_at.strip():
        errors.append("Record when the privacy notice was acknowledged.")
    if not config.privacy.legal_basis.strip():
        errors.append("Document the assessed legal basis before enabling cameras.")
    if not config.privacy.controller_name.strip() or not config.privacy.controller_contact.strip():
        errors.append("Document the controller name and privacy contact.")
    return errors
