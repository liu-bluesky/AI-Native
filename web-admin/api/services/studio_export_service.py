"""后台短片正式导出执行器。"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import mimetypes
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes, urlparse
from urllib.request import urlopen

from stores.json.project_material_store import ProjectMaterialAsset
from stores.json.project_studio_export_store import ProjectStudioExportJob
from stores.json.project_store import _now_iso

logger = logging.getLogger(__name__)

_PROJECT_MATERIAL_UPLOAD_ROOT = "project-material-files"
_PROJECT_STUDIO_EXPORT_RENDER_ROOT = "project-studio-export-renders"
_REMOTE_RESOURCE_DOWNLOAD_MAX_BYTES = 100 * 1024 * 1024
_EXPORT_VIDEO_COLOR_SEQUENCE = (
    "#0F4C81",
    "#A23B72",
    "#2A9D8F",
    "#E76F51",
    "#6D597A",
    "#264653",
)
_RESOLUTION_LONG_EDGE = {
    "720p": 1280,
    "1080p": 1920,
    "4K": 3840,
}


class StudioExportError(RuntimeError):
    """正式导出失败。"""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details if isinstance(details, dict) else {}


class StudioExportCanceled(RuntimeError):
    """正式导出被取消。"""


def _normalize_text(value: Any, *, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _normalize_clip_duration_seconds(clip: dict[str, Any]) -> int:
    for key in ("durationSeconds", "duration_seconds"):
        try:
            duration = int(round(float(clip.get(key) or 0)))
        except (TypeError, ValueError):
            duration = 0
        if duration > 0:
            return max(1, duration)
    try:
        end_seconds = float(clip.get("endSeconds") or clip.get("end_seconds") or 0)
        start_seconds = float(clip.get("startSeconds") or clip.get("start_seconds") or 0)
        duration = int(round(end_seconds - start_seconds))
    except (TypeError, ValueError):
        duration = 0
    return max(1, duration) if duration > 0 else 1


def _normalize_timeline_clips(job: ProjectStudioExportJob) -> list[dict[str, Any]]:
    clips = job.timeline_payload.get("clips")
    if not isinstance(clips, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(clips, start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": _normalize_text(item.get("id"), limit=120) or f"clip-{index}",
                "title": _normalize_text(item.get("title"), limit=120) or f"片段 {index}",
                "duration_seconds": _normalize_clip_duration_seconds(item),
                "type": _normalize_text(item.get("type"), limit=20).lower() or "video",
                "source_type": _normalize_text(
                    item.get("sourceType") or item.get("source_type"),
                    limit=40,
                )
                or "storyboard",
                "asset_id": _normalize_text(
                    item.get("asset_id") or item.get("assetId"),
                    limit=120,
                ),
                "source_id": _normalize_text(
                    item.get("sourceId")
                    or item.get("source_id")
                    or item.get("asset_id")
                    or item.get("assetId"),
                    limit=120,
                ),
                "source_url": _normalize_text(
                    item.get("source_url")
                    or item.get("sourceUrl")
                    or item.get("contentUrl")
                    or item.get("content_url")
                    or item.get("previewUrl")
                    or item.get("preview_url"),
                    limit=2000,
                ),
                "content_url": _normalize_text(
                    item.get("contentUrl") or item.get("content_url"),
                    limit=2000,
                ),
                "preview_url": _normalize_text(
                    item.get("previewUrl") or item.get("preview_url"),
                    limit=2000,
                ),
                "storage_path": _normalize_text(
                    item.get("storagePath") or item.get("storage_path"),
                    limit=500,
                ),
                "mime_type": _normalize_text(
                    item.get("mimeType") or item.get("mime_type"),
                    limit=120,
                ),
                "original_filename": _normalize_text(
                    item.get("originalFilename") or item.get("original_filename"),
                    limit=240,
                ),
            }
        )
    return normalized


def _resolve_render_duration_seconds(job: ProjectStudioExportJob, clips: list[dict[str, Any]]) -> int:
    if clips:
        return max(1, sum(int(item.get("duration_seconds") or 0) for item in clips))
    try:
        duration = int(round(float(job.timeline_duration_seconds or 0)))
    except (TypeError, ValueError):
        duration = 0
    return max(1, duration or 1)


def _normalize_audio_volume_override(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        normalized_volume = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.5, normalized_volume))


def _normalize_audio_mixer(job: ProjectStudioExportJob) -> dict[str, float]:
    payload = job.audio_payload if isinstance(job.audio_payload, dict) else {}
    raw_mixer = payload.get("mixer")
    mixer = raw_mixer if isinstance(raw_mixer, dict) else {}
    normalized_mixer: dict[str, float] = {}
    for key in ("video_volume", "voice_volume", "bgm_volume"):
        normalized_value = _normalize_audio_volume_override(mixer.get(key))
        if normalized_value is not None:
            normalized_mixer[key] = normalized_value
    return normalized_mixer


def _resolve_video_audio_volume(job: ProjectStudioExportJob) -> float:
    return _normalize_audio_mixer(job).get("video_volume", 1.0)


def _normalize_audio_tracks(job: ProjectStudioExportJob) -> list[dict[str, Any]]:
    tracks = job.audio_payload.get("tracks")
    if not isinstance(tracks, list):
        return []
    bgm_payload = _normalize_bgm_payload(job)
    mixer_payload = _normalize_audio_mixer(job)
    normalized_tracks: list[dict[str, Any]] = []
    for track_index, track in enumerate(tracks, start=1):
        if not isinstance(track, dict):
            continue
        kind = _normalize_text(track.get("kind"), limit=40).lower() or "bgm"
        if kind not in {"voice", "bgm", "sfx"}:
            continue
        label = _normalize_text(track.get("label") or track.get("title"), limit=120) or f"音轨 {track_index}"
        track_volume = _normalize_audio_volume_override(track.get("volume"))
        if track_volume is None:
            track_volume = mixer_payload.get(f"{kind}_volume")
        raw_segments = track.get("segments")
        segments: list[dict[str, Any]] = []
        if isinstance(raw_segments, list):
            iterable_segments = raw_segments
        else:
            iterable_segments = [track]
        for segment_index, segment in enumerate(iterable_segments, start=1):
            if not isinstance(segment, dict):
                continue
            try:
                start_seconds = max(0.0, float(segment.get("startSeconds") or segment.get("start_seconds") or 0))
            except (TypeError, ValueError):
                start_seconds = 0.0
            try:
                duration_seconds = max(
                    0.0,
                    float(segment.get("durationSeconds") or segment.get("duration_seconds") or 0),
                )
            except (TypeError, ValueError):
                duration_seconds = 0.0
            if duration_seconds <= 0:
                continue
            volume = _normalize_audio_volume_override(segment.get("volume"))
            if volume is None:
                volume = track_volume
            segments.append(
                {
                    "id": _normalize_text(segment.get("id"), limit=120) or f"{kind}-{segment_index}",
                    "label": _normalize_text(segment.get("label") or segment.get("title"), limit=120) or f"{label} 片段 {segment_index}",
                    "start_seconds": start_seconds,
                    "duration_seconds": duration_seconds,
                    "source_url": _normalize_text(
                        segment.get("source_url")
                        or segment.get("sourceUrl")
                        or segment.get("content_url")
                        or segment.get("contentUrl"),
                        limit=2000,
                    ),
                    "storage_path": _normalize_text(
                        segment.get("storage_path") or segment.get("storagePath"),
                        limit=500,
                    ),
                    "mime_type": _normalize_text(
                        segment.get("mime_type") or segment.get("mimeType"),
                        limit=120,
                    ),
                    "original_filename": _normalize_text(
                        segment.get("original_filename")
                        or segment.get("originalFilename"),
                        limit=240,
                    ),
                    "volume": volume,
                    "bind_clip_id": _normalize_text(
                        segment.get("bind_clip_id") or segment.get("bindClipId") or track.get("bind_clip_id") or track.get("bindClipId"),
                        limit=120,
                    ),
                    "required": bool(segment.get("required", track.get("required"))),
                }
            )
        if segments:
            normalized_tracks.append(
                {
                    "id": _normalize_text(track.get("id"), limit=120) or f"audio-track-{track_index}",
                    "kind": kind,
                    "label": label,
                    "source_url": _normalize_text(
                        track.get("source_url")
                        or track.get("sourceUrl")
                        or (bgm_payload.get("content_url") if kind == "bgm" else ""),
                        limit=2000,
                    ),
                    "storage_path": _normalize_text(
                        track.get("storage_path")
                        or track.get("storagePath")
                        or (bgm_payload.get("storage_path") if kind == "bgm" else ""),
                        limit=500,
                    ),
                    "mime_type": _normalize_text(
                        track.get("mime_type")
                        or track.get("mimeType")
                        or (bgm_payload.get("mime_type") if kind == "bgm" else ""),
                        limit=120,
                    ),
                    "original_filename": _normalize_text(
                        track.get("original_filename")
                        or track.get("originalFilename")
                        or (bgm_payload.get("original_filename") if kind == "bgm" else ""),
                        limit=240,
                    ),
                    "volume": next((item.get("volume") for item in segments if item.get("volume") is not None), track_volume),
                    "segments": segments,
                }
            )
    return normalized_tracks


def _resolve_render_size(aspect_ratio: str, export_resolution: str) -> tuple[int, int]:
    normalized_ratio = _normalize_text(aspect_ratio, limit=20) or "16:9"
    raw_width, _, raw_height = normalized_ratio.partition(":")
    try:
        ratio_width = max(1, int(raw_width))
    except ValueError:
        ratio_width = 16
    try:
        ratio_height = max(1, int(raw_height))
    except ValueError:
        ratio_height = 9
    long_edge = _RESOLUTION_LONG_EDGE.get(_normalize_text(export_resolution, limit=20) or "1080p", 1920)
    if ratio_width >= ratio_height:
        width = long_edge
        height = max(1, round((long_edge * ratio_height) / ratio_width))
    else:
        width = max(1, round((long_edge * ratio_width) / ratio_height))
        height = long_edge
    if width % 2:
        width += 1
    if height % 2:
        height += 1
    return width, height


def _material_file_root(api_data_dir: Path) -> Path:
    root = api_data_dir / _PROJECT_MATERIAL_UPLOAD_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _render_work_root(api_data_dir: Path) -> Path:
    root = api_data_dir / _PROJECT_STUDIO_EXPORT_RENDER_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sanitize_filename(filename: str, fallback_name: str) -> str:
    candidate = "".join(char if char.isalnum() or char in "._-" else "-" for char in Path(filename).name)
    normalized = candidate.strip(".-") or fallback_name
    return normalized[:180]


def _build_material_file_url(project_id: str, asset_id: str) -> str:
    return f"/api/projects/{_normalize_text(project_id, limit=120)}/materials/{_normalize_text(asset_id, limit=120)}/file"


def _build_material_cover_url(project_id: str, asset_id: str) -> str:
    return f"/api/projects/{_normalize_text(project_id, limit=120)}/materials/{_normalize_text(asset_id, limit=120)}/cover"


def _resolve_material_storage_path(api_data_dir: Path, storage_path: str) -> Path | None:
    normalized = _normalize_text(storage_path, limit=500)
    if not normalized:
        return None
    relative_path = Path(normalized)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    return (_material_file_root(api_data_dir) / relative_path).resolve()


def _resolve_material_file_path(api_data_dir: Path, asset: ProjectMaterialAsset) -> Path | None:
    return _resolve_material_storage_path(
        api_data_dir,
        str((asset.metadata or {}).get("storage_path") or "").strip(),
    )


def _resolve_material_cover_path(api_data_dir: Path, asset: ProjectMaterialAsset) -> Path | None:
    return _resolve_material_storage_path(
        api_data_dir,
        str((asset.metadata or {}).get("cover_storage_path") or "").strip(),
    )


def _pick_material_render_url(asset: ProjectMaterialAsset) -> str:
    for candidate in (asset.content_url, asset.preview_url):
        normalized = _normalize_text(candidate, limit=2000)
        if normalized.startswith(("http://", "https://", "data:")):
            return normalized
    return ""


def _resolve_internal_api_resource_file_path(
    api_data_dir: Path,
    project_material_store: Any,
    url: str,
) -> Path | None:
    normalized = _normalize_text(url, limit=2000)
    if not normalized or normalized.startswith("data:"):
        return None
    parsed = urlparse(normalized)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    path = parsed.path or (normalized if normalized.startswith("/") else "")
    if not path.startswith("/api/"):
        return None
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 6 and parts[:2] == ["api", "projects"] and parts[3] == "materials":
        project_id = _normalize_text(parts[2], limit=120)
        asset_id = _normalize_text(parts[4], limit=120)
        resource_kind = parts[5]
        if not project_id or not asset_id:
            return None
        asset = project_material_store.get(project_id, asset_id)
        if asset is None:
            return None
        if resource_kind == "file":
            return _resolve_material_file_path(api_data_dir, asset)
        if resource_kind == "cover":
            return _resolve_material_cover_path(api_data_dir, asset)
        return None
    if (
        len(parts) >= 7
        and parts[:2] == ["api", "projects"]
        and parts[3] == "studio"
        and parts[4] == "audio"
        and parts[6] == "file"
    ):
        project_id = _normalize_text(parts[2], limit=120)
        audio_id = _normalize_text(parts[5], limit=120)
        if not project_id or not audio_id:
            return None
        audio_root = _material_file_root(api_data_dir) / project_id / "studio-audio" / audio_id
        if not audio_root.exists() or not audio_root.is_dir():
            return None
        candidates = sorted(path for path in audio_root.iterdir() if path.is_file())
        if not candidates:
            return None
        return candidates[0].resolve()
    return None


def _classify_visual_source_mode(*, mime_type: str, file_name: str, url: str) -> str:
    normalized_mime = _normalize_text(mime_type, limit=120).lower()
    if normalized_mime.startswith("video/"):
        return "video"
    if normalized_mime.startswith("image/"):
        return "image"
    candidates = [
        _normalize_text(file_name, limit=240).lower(),
        _normalize_text(url, limit=2000).lower(),
    ]
    video_suffixes = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
    image_suffixes = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
    if any(candidate.endswith(video_suffixes) or any(suffix in candidate for suffix in video_suffixes) for candidate in candidates if candidate):
        return "video"
    if any(candidate.endswith(image_suffixes) or any(suffix in candidate for suffix in image_suffixes) for candidate in candidates if candidate):
        return "image"
    return ""


def _expected_visual_mode(clip: dict[str, Any]) -> str:
    normalized_type = _normalize_text(clip.get("type"), limit=20).lower()
    if normalized_type in {"image", "video"}:
        return normalized_type
    return ""


def _is_compatible_visual_mode(expected_mode: str, candidate_mode: str) -> bool:
    if not candidate_mode:
        return False
    if not expected_mode:
        return True
    return expected_mode == candidate_mode


def _resolve_direct_visual_mode(
    clip: dict[str, Any],
    *,
    file_name: str,
    url: str,
) -> str:
    expected_mode = _expected_visual_mode(clip)
    candidate_mode = _classify_visual_source_mode(
        mime_type=_normalize_text(clip.get("mime_type"), limit=120),
        file_name=file_name,
        url=url,
    )
    if _is_compatible_visual_mode(expected_mode, candidate_mode):
        return candidate_mode
    return ""


def _requires_resolved_visual_source(clip: dict[str, Any]) -> bool:
    source_type = _normalize_text(clip.get("source_type"), limit=40).lower()
    return source_type in {
        "material",
        "project_material",
        "external_url",
        "ai_generated",
        "studio_draft",
    }


def _describe_clip_source_target(clip: dict[str, Any]) -> str:
    clip_id = _normalize_text(clip.get("id"), limit=120) or "unknown"
    clip_title = _normalize_text(clip.get("title"), limit=120)
    if clip_title:
        return f"{clip_title}({clip_id})"
    return clip_id


def _guess_resource_extension(*, url: str, mime_type: str, asset_type: str) -> str:
    parsed_path = urlparse(url).path
    suffix = Path(parsed_path).suffix.lower()
    if suffix:
        return suffix
    normalized_mime = _normalize_text(mime_type, limit=120).lower()
    if normalized_mime:
        guessed = mimetypes.guess_extension(normalized_mime)
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed
    normalized_asset_type = _normalize_text(asset_type, limit=40).lower()
    if normalized_mime.startswith("audio/"):
        guessed = mimetypes.guess_extension(normalized_mime)
        if guessed:
            return guessed
    if normalized_asset_type == "audio":
        return ".mp3"
    if normalized_asset_type == "video":
        return ".mp4"
    if normalized_asset_type == "image":
        return ".png"
    return ".bin"


def _read_remote_resource_bytes(url: str) -> bytes:
    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        if not payload:
            raise StudioExportError("data URL 素材内容为空")
        try:
            if ";base64" in header.lower():
                return base64.b64decode(payload, validate=False)
            return unquote_to_bytes(payload)
        except (ValueError, binascii.Error) as exc:
            raise StudioExportError("data URL 素材解析失败") from exc
    try:
        with urlopen(url, timeout=15) as response:
            chunks: list[bytes] = []
            total_size = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > _REMOTE_RESOURCE_DOWNLOAD_MAX_BYTES:
                    raise StudioExportError("远端素材文件过大，当前下载上限为 100MB")
                chunks.append(chunk)
            if total_size <= 0:
                raise StudioExportError("远端素材内容为空")
            return b"".join(chunks)
    except StudioExportError:
        raise
    except Exception as exc:
        raise StudioExportError(
            _normalize_text(str(exc), limit=500) or "远端素材读取失败",
        ) from exc


def _resolve_studio_audio_storage_path(api_data_dir: Path, storage_path: str) -> Path | None:
    normalized = _normalize_text(storage_path, limit=500)
    if not normalized:
        return None
    relative_path = Path(normalized)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    return (_material_file_root(api_data_dir) / relative_path).resolve()


def _normalize_bgm_payload(job: ProjectStudioExportJob) -> dict[str, Any]:
    payload = job.audio_payload if isinstance(job.audio_payload, dict) else {}
    bgm = payload.get("bgm")
    return bgm if isinstance(bgm, dict) else {}


class StudioExportBackgroundService:
    def __init__(
        self,
        *,
        project_store: Any,
        project_studio_export_store: Any,
        project_material_store: Any,
        api_data_dir: Path,
        poll_interval_seconds: int = 5,
    ) -> None:
        self._project_store = project_store
        self._project_studio_export_store = project_studio_export_store
        self._project_material_store = project_material_store
        self._api_data_dir = Path(api_data_dir)
        self._poll_interval_seconds = max(2, int(poll_interval_seconds or 5))
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._run_lock = asyncio.Lock()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="studio-export-worker")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_pending_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("studio export worker loop failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def run_pending_once(self) -> None:
        if self._run_lock.locked():
            return
        async with self._run_lock:
            for project in self._project_store.list_all():
                project_id = _normalize_text(getattr(project, "id", ""), limit=120)
                if not project_id:
                    continue
                queued_jobs = self._project_studio_export_store.list_by_project(project_id, status="queued", limit=20)
                for queued_job in queued_jobs:
                    await self._process_job(project_id, queued_job.id)

    async def _process_job(self, project_id: str, job_id: str) -> None:
        current = self._project_studio_export_store.get(project_id, job_id)
        if current is None or current.status != "queued":
            return
        now = _now_iso()
        processing_job = replace(
            current,
            status="processing",
            progress=12,
            started_at=now,
            updated_at=now,
            error_code="",
            error_message="",
            error_details={},
            finished_at="",
            attempt_count=max(1, int(current.attempt_count or 0)),
        )
        self._project_studio_export_store.save(processing_job)
        try:
            asset = await self._render_and_persist_asset(processing_job)
        except StudioExportCanceled:
            canceled_job = self._project_studio_export_store.get(project_id, job_id)
            if canceled_job is None:
                return
            self._project_studio_export_store.save(
                replace(
                    canceled_job,
                    status="canceled",
                    finished_at=_now_iso(),
                    updated_at=_now_iso(),
                )
            )
            return
        except Exception as exc:
            failed_job = self._project_studio_export_store.get(project_id, job_id)
            if failed_job is None:
                return
            error_details = exc.details if isinstance(exc, StudioExportError) else {}
            self._project_studio_export_store.save(
                replace(
                    failed_job,
                    status="failed",
                    progress=100,
                    error_code=type(exc).__name__,
                    error_message=_normalize_text(str(exc), limit=2000) or "正式导出失败",
                    error_details=error_details,
                    finished_at=_now_iso(),
                    updated_at=_now_iso(),
                )
            )
            return
        updated_job = self._project_studio_export_store.get(project_id, job_id)
        if updated_job is None:
            return
        self._project_studio_export_store.save(
            replace(
                updated_job,
                status="succeeded",
                progress=100,
                result_asset_id=asset.id,
                error_code="",
                error_message="",
                error_details={},
                finished_at=_now_iso(),
                updated_at=_now_iso(),
            )
        )

    async def _render_and_persist_asset(self, job: ProjectStudioExportJob) -> ProjectMaterialAsset:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise StudioExportError(
                "正式导出依赖 FFmpeg，当前服务器未安装或不在 PATH 中",
                details={
                    "kind": "ffmpeg_missing",
                    "reason": "正式导出依赖 FFmpeg，当前服务器未安装或不在 PATH 中",
                },
            )
        temp_dir = _render_work_root(self._api_data_dir) / job.project_id / job.id
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        video_path = temp_dir / "render.mp4"
        cover_path = temp_dir / "cover.png"
        try:
            clips = _normalize_timeline_clips(job)
            audio_tracks = _normalize_audio_tracks(job)
            duration_seconds = _resolve_render_duration_seconds(job, clips)
            width, height = _resolve_render_size(job.aspect_ratio, job.export_resolution)
            await self._render_job_video(ffmpeg_bin, job, clips, duration_seconds, width, height, video_path)
            self._update_job_progress(job.project_id, job.id, 72)
            final_video_path = video_path
            if audio_tracks:
                mixed_video_path = temp_dir / "render-with-audio.mp4"
                await self._render_job_audio(
                    ffmpeg_bin=ffmpeg_bin,
                    job=job,
                    audio_tracks=audio_tracks,
                    duration_seconds=duration_seconds,
                    input_video_path=video_path,
                    output_video_path=mixed_video_path,
                )
                final_video_path = mixed_video_path
                self._update_job_progress(job.project_id, job.id, 80)
            await self._render_job_cover(ffmpeg_bin, job, final_video_path, cover_path)
            self._update_job_progress(job.project_id, job.id, 86)
            return self._save_rendered_asset(
                job=job,
                clips=clips,
                audio_tracks=audio_tracks,
                duration_seconds=duration_seconds,
                width=width,
                height=height,
                temp_video_path=final_video_path,
                temp_cover_path=cover_path,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _update_job_progress(self, project_id: str, job_id: str, progress: int) -> None:
        current = self._project_studio_export_store.get(project_id, job_id)
        if current is None or current.status == "canceled":
            return
        self._project_studio_export_store.save(
            replace(
                current,
                progress=max(0, min(100, int(progress))),
                updated_at=_now_iso(),
            )
        )

    async def _render_job_video(
        self,
        ffmpeg_bin: str,
        job: ProjectStudioExportJob,
        clips: list[dict[str, Any]],
        duration_seconds: int,
        width: int,
        height: int,
        video_path: Path,
    ) -> None:
        normalized_clips = clips or [{"id": "clip-1", "title": "片段 1", "duration_seconds": duration_seconds}]
        segment_paths: list[Path] = []
        clip_sources: list[dict[str, Any]] = []
        for index, clip in enumerate(normalized_clips, start=1):
            current = self._project_studio_export_store.get(job.project_id, job.id)
            if current is not None and current.status == "canceled":
                raise StudioExportCanceled("正式导出任务已取消")
            source = await self._resolve_clip_render_source(
                job.project_id,
                clip,
                index - 1,
                video_path.parent,
            )
            if bool(source.get("unresolved_source")) and _requires_resolved_visual_source(clip):
                raise StudioExportError(
                    f"片段 {_describe_clip_source_target(clip)} 缺少可渲染素材："
                    f"{_normalize_text(source.get('reason'), limit=500) or '未找到可用文件'}",
                    details={
                        "kind": "unresolved_visual_source",
                        "clip_id": _normalize_text(clip.get("id"), limit=120),
                        "clip_title": _normalize_text(clip.get("title"), limit=120),
                        "source_type": _normalize_text(clip.get("source_type"), limit=40),
                        "asset_id": _normalize_text(
                            clip.get("asset_id") or clip.get("source_id"),
                            limit=120,
                        ),
                        "storage_path": _normalize_text(clip.get("storage_path"), limit=500),
                        "content_url": _normalize_text(
                            clip.get("content_url") or clip.get("source_url"),
                            limit=500,
                        ),
                        "preview_url": _normalize_text(clip.get("preview_url"), limit=500),
                        "reason": _normalize_text(source.get("reason"), limit=500),
                    },
                )
            clip_sources.append(source)
            segment_path = video_path.parent / f"segment-{index:03d}.mp4"
            await self._render_clip_segment(
                ffmpeg_bin=ffmpeg_bin,
                job=job,
                clip=clip,
                source=source,
                width=width,
                height=height,
                segment_path=segment_path,
            )
            segment_paths.append(segment_path)
            progress_base = 18
            progress_range = 44
            self._update_job_progress(
                job.project_id,
                job.id,
                progress_base + round(progress_range * (index / max(1, len(normalized_clips)))),
            )
        concat_list_path = video_path.parent / "segments.txt"
        concat_list_path.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in segment_paths),
            encoding="utf-8",
        )
        await self._concat_render_segments(ffmpeg_bin, job, concat_list_path, video_path)
        for clip, source in zip(normalized_clips, clip_sources):
            clip["render_source_mode"] = source.get("mode", "color")
            clip["render_source_asset_id"] = _normalize_text(source.get("asset_id"), limit=120)
            clip["render_source_path"] = _normalize_text(source.get("path"), limit=500)
            clip["render_source_url"] = _normalize_text(source.get("url"), limit=500)
            clip["render_fallback"] = bool(source.get("fallback"))
            clip["render_unresolved_source"] = bool(source.get("unresolved_source"))
            clip["render_source_reason"] = _normalize_text(source.get("reason"), limit=500)

    async def _resolve_clip_render_source(
        self,
        project_id: str,
        clip: dict[str, Any],
        color_index: int,
        temp_dir: Path,
    ) -> dict[str, Any]:
        direct_storage_path = _normalize_text(clip.get("storage_path"), limit=500)
        direct_content_url = _normalize_text(
            clip.get("content_url") or clip.get("source_url"),
            limit=2000,
        )
        direct_preview_url = _normalize_text(clip.get("preview_url"), limit=2000)
        direct_file_name = _normalize_text(clip.get("original_filename"), limit=240) or Path(direct_storage_path).name
        source_type = _normalize_text(clip.get("source_type"), limit=40).lower()
        source_id = _normalize_text(clip.get("asset_id") or clip.get("source_id"), limit=120)
        unresolved_reason = ""
        if source_type in {"material", "project_material"} and source_id:
            asset = self._project_material_store.get(project_id, source_id)
            if asset is not None:
                file_path = _resolve_material_file_path(self._api_data_dir, asset)
                if file_path is not None and file_path.exists():
                    asset_type = _normalize_text(asset.asset_type, limit=40).lower()
                    mime_type = _normalize_text(asset.mime_type, limit=120).lower()
                    if asset_type == "video" or mime_type.startswith("video/"):
                        return {
                            "mode": "video",
                            "path": str(file_path),
                            "asset_id": asset.id,
                            "fallback": False,
                        }
                    if asset_type in {"image", "storyboard"} or mime_type.startswith("image/"):
                        return {
                            "mode": "image",
                            "path": str(file_path),
                            "asset_id": asset.id,
                            "fallback": False,
                        }
                try:
                    remote_source = await self._resolve_remote_material_source(asset, clip, temp_dir)
                except StudioExportError as exc:
                    unresolved_reason = _normalize_text(str(exc), limit=500) or "远端素材读取失败"
                else:
                    if remote_source is not None:
                        return remote_source
                    unresolved_reason = f"素材 {source_id} 未找到本地文件，且远端地址不可用"
            else:
                unresolved_reason = f"素材 {source_id} 不存在"

        direct_mode = _resolve_direct_visual_mode(
            clip,
            file_name=direct_file_name or direct_storage_path,
            url=direct_content_url or direct_preview_url,
        )
        if direct_storage_path and direct_mode:
            local_path = _resolve_material_storage_path(self._api_data_dir, direct_storage_path)
            if local_path is not None and local_path.exists():
                return {
                    "mode": direct_mode,
                    "path": str(local_path),
                    "fallback": False,
                }
            if not unresolved_reason:
                unresolved_reason = f"本地文件 {direct_storage_path} 不存在"
        elif direct_storage_path and not unresolved_reason:
            unresolved_reason = f"本地文件 {direct_storage_path} 与片段类型不匹配"
        for direct_url in (direct_content_url, direct_preview_url):
            if not direct_url.startswith(("http://", "https://", "data:")):
                continue
            direct_url_mode = _resolve_direct_visual_mode(
                clip,
                file_name=direct_file_name,
                url=direct_url,
            )
            if not direct_url_mode:
                continue
            local_path = _resolve_internal_api_resource_file_path(
                self._api_data_dir,
                self._project_material_store,
                direct_url,
            )
            if local_path is not None and local_path.exists():
                return {
                    "mode": direct_url_mode,
                    "path": str(local_path),
                    "fallback": False,
                    "url": direct_url[:500],
                }
            extension = _guess_resource_extension(
                url=direct_url,
                mime_type=_normalize_text(clip.get("mime_type"), limit=120),
                asset_type=direct_url_mode,
            )
            file_name = _sanitize_filename(
                direct_file_name or f"{_normalize_text(clip.get('id'), limit=80) or 'clip'}{extension}",
                f"{_normalize_text(clip.get('id'), limit=80) or 'clip'}{extension}",
            )
            destination = temp_dir / "fetched-clips" / file_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                destination.write_bytes(
                    await asyncio.to_thread(_read_remote_resource_bytes, direct_url)
                )
            except StudioExportError as exc:
                if not unresolved_reason:
                    unresolved_reason = _normalize_text(str(exc), limit=500) or "远端素材读取失败"
                continue
            return {
                "mode": direct_url_mode,
                "path": str(destination),
                "fallback": False,
                "remote": True,
                "url": direct_url[:500],
            }
        if not unresolved_reason and (direct_content_url or direct_preview_url):
            unresolved_reason = "远端素材地址与片段类型不匹配或无法访问"
        return {
            "mode": "color",
            "color": _EXPORT_VIDEO_COLOR_SEQUENCE[color_index % len(_EXPORT_VIDEO_COLOR_SEQUENCE)],
            "fallback": True,
            "unresolved_source": bool(unresolved_reason),
            "reason": unresolved_reason,
        }

    async def _resolve_remote_material_source(
        self,
        asset: ProjectMaterialAsset,
        clip: dict[str, Any],
        temp_dir: Path,
    ) -> dict[str, Any] | None:
        resource_url = _pick_material_render_url(asset)
        if not resource_url:
            return None
        local_path = _resolve_internal_api_resource_file_path(
            self._api_data_dir,
            self._project_material_store,
            resource_url,
        )
        if local_path is not None and local_path.exists():
            asset_type = _normalize_text(asset.asset_type, limit=40).lower()
            mime_type = _normalize_text(asset.mime_type, limit=120).lower()
            if asset_type == "video" or mime_type.startswith("video/"):
                mode = "video"
            elif asset_type in {"image", "storyboard"} or mime_type.startswith("image/"):
                mode = "image"
            else:
                return None
            return {
                "mode": mode,
                "path": str(local_path),
                "asset_id": asset.id,
                "fallback": False,
                "url": resource_url[:500],
            }
        source_bytes = await asyncio.to_thread(_read_remote_resource_bytes, resource_url)
        extension = _guess_resource_extension(
            url=resource_url,
            mime_type=asset.mime_type,
            asset_type=asset.asset_type,
        )
        file_name = _sanitize_filename(
            f"{_normalize_text(clip.get('id'), limit=80) or asset.id}{extension}",
            f"{asset.id}{extension}",
        )
        destination = temp_dir / "fetched-assets" / file_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_bytes)
        asset_type = _normalize_text(asset.asset_type, limit=40).lower()
        mime_type = _normalize_text(asset.mime_type, limit=120).lower()
        if asset_type == "video" or mime_type.startswith("video/"):
            mode = "video"
        elif asset_type in {"image", "storyboard"} or mime_type.startswith("image/") or resource_url.startswith("data:image/"):
            mode = "image"
        else:
            return None
        return {
            "mode": mode,
            "path": str(destination),
            "asset_id": asset.id,
            "fallback": False,
            "remote": True,
            "url": resource_url[:500],
        }

    async def _render_clip_segment(
        self,
        *,
        ffmpeg_bin: str,
        job: ProjectStudioExportJob,
        clip: dict[str, Any],
        source: dict[str, Any],
        width: int,
        height: int,
        segment_path: Path,
    ) -> None:
        codec = "libx265" if job.export_format == "mp4-h265" else "libx264"
        crf = "28" if codec == "libx265" else "23"
        clip_duration = max(1, int(clip.get("duration_seconds") or 1))
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            "fps=24,format=yuv420p"
        )
        source_mode = _normalize_text(source.get("mode"), limit=20)
        source_path = _normalize_text(source.get("path"), limit=500)
        source_has_audio = False
        if source_mode == "video" and source_path:
            source_has_audio = await self._source_has_audio_stream(
                ffmpeg_bin=ffmpeg_bin,
                source_path=source_path,
            )
            input_args = [
                "-stream_loop",
                "-1",
                "-t",
                str(clip_duration),
                "-i",
                source_path,
            ]
        elif source_mode == "image" and source_path:
            input_args = [
                "-loop",
                "1",
                "-t",
                str(clip_duration),
                "-i",
                source_path,
            ]
        else:
            input_args = [
                "-f",
                "lavfi",
                "-i",
                f"color=c={source.get('color') or '#264653'}:s={width}x{height}:d={clip_duration}:r=24",
            ]
        command = [ffmpeg_bin, "-y", *input_args]
        if source_mode == "video" and source_path and source_has_audio:
            command.extend(["-map", "0:v:0", "-map", "0:a:0"])
        else:
            command.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    str(clip_duration),
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                ]
            )
        command.extend(
            [
                "-vf",
                vf,
                "-shortest",
                "-r",
                "24",
                "-c:v",
                codec,
                "-preset",
                "veryfast",
                "-crf",
                crf,
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
            ]
        )
        if codec == "libx265":
            command.extend(["-tag:v", "hvc1"])
        command.append(str(segment_path))
        await self._run_ffmpeg_command(job, command)

    async def _source_has_audio_stream(self, *, ffmpeg_bin: str, source_path: str) -> bool:
        ffprobe_bin = shutil.which("ffprobe")
        if ffprobe_bin:
            command = [
                ffprobe_bin,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                source_path,
            ]
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            return process.returncode == 0 and b"audio" in (stdout or b"").lower()
        process = await asyncio.create_subprocess_exec(
            ffmpeg_bin,
            "-v",
            "error",
            "-i",
            source_path,
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return process.returncode == 0

    async def _concat_render_segments(
        self,
        ffmpeg_bin: str,
        job: ProjectStudioExportJob,
        concat_list_path: Path,
        video_path: Path,
    ) -> None:
        command = [
            ffmpeg_bin,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(video_path),
        ]
        await self._run_ffmpeg_command(job, command)

    async def _render_job_audio(
        self,
        *,
        ffmpeg_bin: str,
        job: ProjectStudioExportJob,
        audio_tracks: list[dict[str, Any]],
        duration_seconds: int,
        input_video_path: Path,
        output_video_path: Path,
    ) -> None:
        segment_specs: list[dict[str, Any]] = []
        for track_index, track in enumerate(audio_tracks, start=1):
            kind = _normalize_text(track.get("kind"), limit=40).lower()
            for segment_index, segment in enumerate(track.get("segments") or [], start=1):
                try:
                    start_seconds = max(0.0, float(segment.get("start_seconds") or 0))
                except (TypeError, ValueError):
                    start_seconds = 0.0
                try:
                    clip_duration = max(0.0, float(segment.get("duration_seconds") or 0))
                except (TypeError, ValueError):
                    clip_duration = 0.0
                if clip_duration <= 0:
                    continue
                source = await self._resolve_audio_segment_source(
                    track=track,
                    segment=segment,
                    kind=kind,
                    track_index=track_index,
                    segment_index=segment_index,
                    temp_dir=output_video_path.parent,
                )
                segment_specs.append(
                    {
                        "kind": kind,
                        "start_seconds": start_seconds,
                        "duration_seconds": clip_duration,
                        "source": source,
                        "volume": self._resolve_audio_volume(kind, segment.get("volume")),
                    }
                )
        if not segment_specs:
            return
        base_video_volume = _resolve_video_audio_volume(job)
        input_args = [ffmpeg_bin, "-y", "-i", str(input_video_path)]
        filter_parts: list[str] = [f"[0:a:0]aresample=44100,volume={base_video_volume}[base]"]
        mix_labels: list[str] = ["[base]"]
        for input_index, segment in enumerate(segment_specs, start=1):
            source = segment["source"]
            if source["kind"] == "file":
                input_args.extend(
                    [
                        "-stream_loop",
                        "-1",
                        "-t",
                        str(segment["duration_seconds"]),
                        "-i",
                        str(source["value"]),
                    ]
                )
            else:
                input_args.extend(
                    [
                        "-f",
                        "lavfi",
                        "-t",
                        str(segment["duration_seconds"]),
                        "-i",
                        str(source["value"]),
                    ]
                )
            delay_ms = max(0, int(round(float(segment["start_seconds"]) * 1000)))
            output_label = f"a{input_index}"
            filter_parts.append(
                f"[{input_index}:a]aresample=44100,adelay={delay_ms}|{delay_ms},volume={segment['volume']}[{output_label}]"
            )
            mix_labels.append(f"[{output_label}]")
        if len(mix_labels) == 1:
            filter_parts.append(f"{mix_labels[0]}anull[aout]")
        else:
            filter_parts.append(
                "".join(mix_labels) + f"amix=inputs={len(mix_labels)}:normalize=0[aout]"
            )
        command = [
            *input_args,
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_video_path),
        ]
        await self._run_ffmpeg_command(job, command)

    async def _resolve_audio_segment_source(
        self,
        *,
        track: dict[str, Any],
        segment: dict[str, Any],
        kind: str,
        track_index: int,
        segment_index: int,
        temp_dir: Path,
    ) -> dict[str, Any]:
        storage_path = _normalize_text(
            segment.get("storage_path") or track.get("storage_path"),
            limit=500,
        )
        if storage_path:
            local_path = _resolve_studio_audio_storage_path(self._api_data_dir, storage_path)
            if local_path is not None and local_path.exists():
                return {"kind": "file", "value": str(local_path)}
        source_url = _normalize_text(
            segment.get("source_url") or track.get("source_url"),
            limit=2000,
        )
        if source_url.startswith(("http://", "https://", "data:")):
            local_path = _resolve_internal_api_resource_file_path(
                self._api_data_dir,
                self._project_material_store,
                source_url,
            )
            if local_path is not None and local_path.exists():
                return {"kind": "file", "value": str(local_path)}
            source_bytes = await asyncio.to_thread(_read_remote_resource_bytes, source_url)
            extension = _guess_resource_extension(
                url=source_url,
                mime_type=_normalize_text(
                    segment.get("mime_type") or track.get("mime_type"),
                    limit=120,
                ),
                asset_type="audio",
            )
            file_name = _sanitize_filename(
                _normalize_text(
                    segment.get("original_filename") or track.get("original_filename"),
                    limit=240,
                )
                or f"{kind}-{track_index}-{segment_index}{extension}",
                f"{kind}-{track_index}-{segment_index}{extension}",
            )
            destination = temp_dir / "fetched-audio" / file_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source_bytes)
            return {"kind": "file", "value": str(destination)}
        return {
            "kind": "lavfi",
            "value": self._build_audio_source(kind, track_index, segment_index),
        }

    def _build_audio_source(self, kind: str, track_index: int, segment_index: int) -> str:
        if kind == "voice":
            frequency = 210 + (track_index * 12) + (segment_index % 3) * 18
            return f"sine=frequency={frequency}:sample_rate=44100"
        return f"sine=frequency={140 + track_index * 8}:sample_rate=44100"

    def _resolve_audio_volume(self, kind: str, override: Any = None) -> float:
        try:
            if override not in (None, ""):
                return max(0.0, min(1.5, float(override)))
        except (TypeError, ValueError):
            pass
        if kind == "voice":
            return 0.22
        return 0.08

    async def _render_job_cover(
        self,
        ffmpeg_bin: str,
        job: ProjectStudioExportJob,
        video_path: Path,
        cover_path: Path,
    ) -> None:
        command = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(cover_path),
        ]
        await self._run_ffmpeg_command(job, command)

    async def _run_ffmpeg_command(self, job: ProjectStudioExportJob, command: list[str]) -> None:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        communicate_task = asyncio.create_task(process.communicate())
        try:
            while True:
                try:
                    stdout, stderr = await asyncio.wait_for(asyncio.shield(communicate_task), timeout=0.5)
                    break
                except asyncio.TimeoutError:
                    current = self._project_studio_export_store.get(job.project_id, job.id)
                    if current is not None and current.status == "canceled":
                        process.kill()
                        await process.wait()
                        raise StudioExportCanceled("正式导出任务已取消")
            if process.returncode != 0:
                raise StudioExportError(
                    _normalize_text(
                        (stderr or stdout or b"").decode("utf-8", errors="ignore"),
                        limit=2000,
                    )
                    or "FFmpeg 渲染失败"
                )
        finally:
            if not communicate_task.done():
                communicate_task.cancel()
                try:
                    await communicate_task
                except asyncio.CancelledError:
                    pass

    def _save_rendered_asset(
        self,
        *,
        job: ProjectStudioExportJob,
        clips: list[dict[str, Any]],
        audio_tracks: list[dict[str, Any]],
        duration_seconds: int,
        width: int,
        height: int,
        temp_video_path: Path,
        temp_cover_path: Path,
    ) -> ProjectMaterialAsset:
        if not temp_video_path.exists():
            raise StudioExportError("正式导出结果文件缺失")
        asset_id = self._project_material_store.new_id()
        material_root = _material_file_root(self._api_data_dir)
        asset_dir = Path(job.project_id) / asset_id
        video_file_name = _sanitize_filename(
            f"{job.title or 'studio-export'}-{job.export_resolution}.mp4",
            f"{asset_id}.mp4",
        )
        cover_file_name = _sanitize_filename(
            f"cover-{job.id}.png",
            f"{asset_id}-cover.png",
        )
        relative_video_path = asset_dir / video_file_name
        relative_cover_path = asset_dir / cover_file_name
        absolute_video_path = material_root / relative_video_path
        absolute_cover_path = material_root / relative_cover_path
        absolute_video_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_cover_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_video_path), str(absolute_video_path))
        if temp_cover_path.exists():
            shutil.move(str(temp_cover_path), str(absolute_cover_path))
        now = _now_iso()
        metadata = {
            "artifact_source": "studio-export-final",
            "export_job_id": job.id,
            "requested_export_format": job.export_format,
            "requested_export_resolution": job.export_resolution,
            "aspect_ratio": job.aspect_ratio,
            "timeline_duration_seconds": duration_seconds,
            "clip_count": len(clips),
            "render_backend": "ffmpeg",
            "render_mode": "timeline_local_media_v2",
            "render_width": width,
            "render_height": height,
            "rendered_source_asset_ids": [
                _normalize_text(item.get("render_source_asset_id"), limit=120)
                for item in clips
                if _normalize_text(item.get("render_source_asset_id"), limit=120)
            ],
            "render_audio_track_count": len(audio_tracks),
            "render_audio_segment_count": sum(len(item.get("segments") or []) for item in audio_tracks),
            "render_audio_kinds": [
                _normalize_text(item.get("kind"), limit=40)
                for item in audio_tracks
                if _normalize_text(item.get("kind"), limit=40)
            ],
            "render_audio_mode": "procedural_v1" if audio_tracks else "silent",
            "render_remote_clip_count": sum(1 for item in clips if _normalize_text(item.get("render_source_url"), limit=500)),
            "render_fallback_clip_count": sum(1 for item in clips if item.get("render_fallback")),
            "render_unresolved_clip_count": sum(1 for item in clips if item.get("render_unresolved_source")),
            "render_fallback_clip_ids": [
                _normalize_text(item.get("id"), limit=120)
                for item in clips
                if item.get("render_fallback") and _normalize_text(item.get("id"), limit=120)
            ],
            "storage_path": relative_video_path.as_posix(),
            "video_duration_seconds": duration_seconds,
            "duration_seconds": duration_seconds,
            "durationSeconds": duration_seconds,
            "cover_storage_path": relative_cover_path.as_posix() if absolute_cover_path.exists() else "",
            "cover_original_filename": cover_file_name if absolute_cover_path.exists() else "",
            "cover_mime_type": "image/png" if absolute_cover_path.exists() else "",
            "cover_file_size_bytes": absolute_cover_path.stat().st_size if absolute_cover_path.exists() else 0,
            "generated_at": now,
        }
        summary = (
            f"短片正式导出结果，共 {len(clips)} 个片段，"
            f"{duration_seconds} 秒，{job.export_resolution} / {job.export_format}"
        )
        asset = ProjectMaterialAsset(
            id=asset_id,
            project_id=job.project_id,
            asset_type="video",
            group_type="storyboard_video",
            title=_normalize_text(job.title, limit=120) or "短片正式导出",
            summary=summary,
            source_type="studio_export",
            created_by=_normalize_text(job.created_by, limit=120),
            created_at=now,
            updated_at=now,
            original_filename=video_file_name,
            file_size_bytes=absolute_video_path.stat().st_size,
            preview_url=_build_material_cover_url(job.project_id, asset_id)
            if absolute_cover_path.exists()
            else _build_material_file_url(job.project_id, asset_id),
            content_url=_build_material_file_url(job.project_id, asset_id),
            mime_type="video/mp4",
            status="ready",
            structured_content={
                "kind": "studio_export_final",
                "clips": clips,
            },
            metadata=metadata,
        )
        self._project_material_store.save(asset)
        return asset
