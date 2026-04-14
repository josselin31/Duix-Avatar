#!/usr/bin/env python3
"""One-command pipeline for CONTENT_CREATION/*.md.

Steps:
1) Build perfect prompt package from reverse-prompt embeddings
2) Auto-start/check Duix services
3) Try Duix render
4) Fallback render (OpenAI TTS + ffmpeg) if Duix services unavailable
"""

from __future__ import annotations

import argparse
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from openai import OpenAI

ROOT_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT_DIR / "CONTENT_CREATION"
GENERATED_DIR = CONTENT_DIR / "GENERATED"
INIT_ASSET_DIR = ROOT_DIR / "init_ASSET"
ENV_PATH = ROOT_DIR / ".env"
DEPLOY_DIR = ROOT_DIR / "deploy"


def case_dir_for_stem(stem: str) -> Path:
    return GENERATED_DIR / stem


def artifacts_dir_for_stem(stem: str) -> Path:
    return case_dir_for_stem(stem) / "artifacts"


def source_copy_path(stem: str) -> Path:
    return case_dir_for_stem(stem) / f"{stem}.md"


def primary_rendered_path(stem: str) -> Path:
    return case_dir_for_stem(stem) / f"{stem}.rendered.mp4"


def artifact_path(stem: str, suffix: str) -> Path:
    return artifacts_dir_for_stem(stem) / f"{stem}.{suffix}"


def load_env_file() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        env[key] = value
    return env


def is_port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def append_check(checks: list[tuple[str, bool, str]], name: str, ok: bool, detail: str) -> None:
    checks.append((name, ok, detail))


def run_command(
    checks: list[tuple[str, bool, str]],
    name: str,
    cmd: list[str],
    cwd: Path,
    check: bool = False,
) -> int:
    try:
        result = subprocess.run(cmd, cwd=cwd, check=check)
        ok = result.returncode == 0
        append_check(checks, name, ok, f"cmd={' '.join(cmd)} | rc={result.returncode}")
        return result.returncode
    except subprocess.CalledProcessError as exc:
        append_check(checks, name, False, f"cmd={' '.join(cmd)} | rc={exc.returncode}")
        return exc.returncode
    except Exception as exc:  # pylint: disable=broad-except
        append_check(checks, name, False, f"cmd={' '.join(cmd)} | err={exc}")
        return 1


def is_path_locked(path: Path) -> bool:
    if not path.exists():
        return False
    probe = path.with_name(f"{path.name}.lockprobe")
    try:
        path.rename(probe)
        probe.rename(path)
        return False
    except OSError:
        return True


def choose_writable_output(base_path: Path) -> Path:
    if not base_path.exists():
        return base_path
    if not is_path_locked(base_path):
        base_path.unlink()
        return base_path

    for idx in range(2, 20):
        candidate = base_path.with_name(f"{base_path.stem}.v{idx}{base_path.suffix}")
        if not candidate.exists():
            return candidate
        if not is_path_locked(candidate):
            candidate.unlink()
            return candidate
    raise RuntimeError(f"No writable output path available near {base_path}")


def ffmpeg_escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("%", "\\%")
    )


def extract_markdown_section(markdown_text: str, section_title: str) -> str:
    pattern = rf"(?ms)^##\s+{re.escape(section_title)}\s*\n(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, markdown_text)
    if not match:
        return ""
    return match.group(1).strip()


def build_sora_prompt(source_stem: str) -> str:
    package_path = artifact_path(source_stem, "perfect_prompt.md")
    if not package_path.exists():
        raise FileNotFoundError(f"Missing prompt package: {package_path}")

    content = package_path.read_text(encoding="utf-8")
    master = extract_markdown_section(content, "MASTER_VIDEO_PROMPT")
    overlays = extract_markdown_section(content, "ON_SCREEN_OVERLAYS")
    notes = extract_markdown_section(content, "DUIX_RENDER_NOTES")

    prompt_parts = [
        master.strip(),
        "Storyboard overlays à intégrer visuellement:",
        overlays.strip(),
        "Notes de rendu:",
        notes.strip(),
        "Contraintes strictes: vidéo verticale 9:16, dynamique TikTok, texte lisible mobile, réalisme élevé.",
    ]
    return "\n\n".join([part for part in prompt_parts if part]).strip()


def generate_openai_tts_audio(
    env: dict[str, str],
    checks: list[tuple[str, bool, str]],
    source_stem: str,
) -> Path:
    narration_path = artifact_path(source_stem, "duix_narration.txt")
    if not narration_path.exists():
        raise FileNotFoundError(f"Missing narration file: {narration_path}")

    narration_text = narration_path.read_text(encoding="utf-8").strip()
    if not narration_text:
        raise ValueError(f"Narration is empty: {narration_path}")

    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")

    tts_model = env.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    tts_voice = env.get("OPENAI_TTS_VOICE", "nova")
    tts_instructions = env.get(
        "OPENAI_TTS_INSTRUCTIONS",
        "Voix de femme jeune, energique, active, sourire dans la voix, diction claire.",
    )

    tts_audio_path = choose_writable_output(artifact_path(source_stem, "openai_tts.wav"))
    client = OpenAI(api_key=api_key)
    with client.audio.speech.with_streaming_response.create(
        model=tts_model,
        voice=tts_voice,
        input=narration_text,
        instructions=tts_instructions,
        response_format="wav",
        speed=1.12,
    ) as speech_response:
        speech_response.stream_to_file(tts_audio_path)

    append_check(
        checks,
        "openai_tts_audio",
        tts_audio_path.exists(),
        f"voice={tts_voice} | audio={tts_audio_path}",
    )
    return tts_audio_path


def render_sora_video(
    env: dict[str, str],
    checks: list[tuple[str, bool, str]],
    source_stem: str,
) -> Path:
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")

    prompt = build_sora_prompt(source_stem)
    model = env.get("OPENAI_VIDEO_MODEL", "sora-2")
    seconds = env.get("OPENAI_VIDEO_SECONDS", "12")
    size = env.get("OPENAI_VIDEO_SIZE", "720x1280")
    max_seconds = int(env.get("MAX_RENDER_SECONDS", "18"))

    client = OpenAI(api_key=api_key)
    append_check(checks, "sora_request", True, f"model={model} seconds={seconds} size={size}")

    video = client.videos.create_and_poll(
        model=model,
        prompt=prompt,
        seconds=seconds,
        size=size,
        poll_interval_ms=2000,
    )
    status = getattr(video, "status", "unknown")
    video_id = getattr(video, "id", "")
    if status != "completed" or not video_id:
        raise RuntimeError(f"Sora generation not completed: status={status} id={video_id}")
    append_check(checks, "sora_generation_completed", True, f"video_id={video_id}")

    raw_video_path = choose_writable_output(artifact_path(source_stem, "sora_raw.mp4"))
    content = client.videos.download_content(video_id, variant="video")
    content.stream_to_file(raw_video_path)
    if not raw_video_path.exists():
        raise RuntimeError("Sora content download failed.")
    append_check(checks, "sora_video_download", True, f"path={raw_video_path}")

    tts_audio_path = generate_openai_tts_audio(env=env, checks=checks, source_stem=source_stem)
    output_video = choose_writable_output(primary_rendered_path(source_stem))

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    mux_cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(raw_video_path),
        "-i",
        str(tts_audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-t",
        str(max_seconds),
        "-shortest",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "26",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_video),
    ]
    subprocess.run(mux_cmd, check=True, cwd=ROOT_DIR)
    append_check(checks, "sora_mux_with_tts", output_video.exists(), f"output={output_video}")

    try:
        if raw_video_path.exists():
            raw_video_path.unlink()
    except OSError:
        pass

    return output_video


def find_docker_desktop_exe() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe"),
        Path.home() / "AppData" / "Local" / "Docker" / "Docker Desktop.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def ensure_local_assets(env: dict[str, str], checks: list[tuple[str, bool, str]]) -> tuple[Path, str, Path]:
    model_dir = Path(env.get("DUIX_ASSET_MODEL_DIR", r"C:\duix_avatar_data\face2face\temp"))
    voice_root = model_dir.parent.parent / "voice" / "data"
    origin_audio_dir = voice_root / "origin_audio"

    model_dir.mkdir(parents=True, exist_ok=True)
    origin_audio_dir.mkdir(parents=True, exist_ok=True)
    append_check(checks, "create_data_dirs", True, f"model_dir={model_dir}")

    model_rel = env.get("DUIX_MODEL_VIDEO_RELATIVE_PATH", "").strip()
    if not model_rel:
        model_rel = "WhatsApp Video 2026-04-14 at 09.02.34.mp4"
    model_path = model_dir / model_rel

    if not model_path.exists():
        source_candidate = INIT_ASSET_DIR / model_rel
        if not source_candidate.exists():
            videos = sorted(INIT_ASSET_DIR.glob("*.mp4"))
            if not videos:
                raise FileNotFoundError("No source videos found in init_ASSET.")
            source_candidate = videos[0]
            model_rel = source_candidate.name
            model_path = model_dir / model_rel
        shutil.copy2(source_candidate, model_path)
        append_check(checks, "seed_model_video", True, f"copied={source_candidate} -> {model_path}")
    else:
        append_check(checks, "seed_model_video", True, f"already_exists={model_path}")

    reference_audio_rel = env.get("DUIX_REFERENCE_AUDIO", "origin_audio/reference.wav").strip() or "origin_audio/reference.wav"
    reference_audio_path = (
        Path(reference_audio_rel) if Path(reference_audio_rel).is_absolute() else voice_root / reference_audio_rel
    )
    reference_audio_path.parent.mkdir(parents=True, exist_ok=True)

    if not reference_audio_path.exists():
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(model_path),
            str(reference_audio_path),
        ]
        subprocess.run(cmd, check=True)
        append_check(checks, "seed_reference_audio", True, f"generated={reference_audio_path}")
    else:
        append_check(checks, "seed_reference_audio", True, f"already_exists={reference_audio_path}")

    return model_dir, model_rel, reference_audio_path


def try_start_duix_services(env: dict[str, str], checks: list[tuple[str, bool, str]]) -> bool:
    tts_ready = is_port_open("127.0.0.1", 18180)
    f2f_ready = is_port_open("127.0.0.1", 8383)
    if tts_ready and f2f_ready:
        append_check(checks, "services_ready_initial", True, "ports 18180 and 8383 already reachable")
        return True

    auto_start = env.get("DUIX_AUTO_START_SERVICES", "0").strip().lower() in {"1", "true", "yes", "on"}
    if not auto_start:
        append_check(checks, "auto_start_services", False, "disabled (set DUIX_AUTO_START_SERVICES=1 to enable)")
        return False

    docker_cmd = shutil.which("docker")
    if not docker_cmd:
        docker_desktop = find_docker_desktop_exe()
        if docker_desktop:
            try:
                subprocess.Popen([str(docker_desktop)])  # noqa: S603
                append_check(checks, "start_docker_desktop", True, f"started={docker_desktop}")
                time.sleep(12)
                docker_cmd = shutil.which("docker")
            except Exception as exc:  # pylint: disable=broad-except
                append_check(checks, "start_docker_desktop", False, str(exc))
        else:
            append_check(checks, "start_docker_desktop", False, "Docker Desktop executable not found")

    if not docker_cmd:
        append_check(checks, "docker_cli_available", False, "docker command not found in PATH")
        return False

    append_check(checks, "docker_cli_available", True, f"docker={docker_cmd}")
    compose_file = env.get("DUIX_DOCKER_COMPOSE_FILE", "docker-compose.yml").strip() or "docker-compose.yml"
    compose_path = DEPLOY_DIR / compose_file
    if not compose_path.exists():
        append_check(checks, "compose_file_exists", False, f"missing={compose_path}")
        return False
    append_check(checks, "compose_file_exists", True, str(compose_path))

    rc = run_command(
        checks=checks,
        name="docker_compose_up",
        cmd=["docker", "compose", "-f", compose_file, "up", "-d"],
        cwd=DEPLOY_DIR,
    )
    if rc != 0:
        rc_legacy = run_command(
            checks=checks,
            name="docker_compose_legacy_up",
            cmd=["docker-compose", "-f", compose_file, "up", "-d"],
            cwd=DEPLOY_DIR,
        )
        if rc_legacy != 0:
            return False

    timeout_s = int(env.get("DUIX_STARTUP_TIMEOUT_SECONDS", "180"))
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        tts_ready = is_port_open("127.0.0.1", 18180)
        f2f_ready = is_port_open("127.0.0.1", 8383)
        if tts_ready and f2f_ready:
            append_check(checks, "services_ready_after_start", True, "ports 18180 and 8383 reachable")
            return True
        time.sleep(5)

    append_check(
        checks,
        "services_ready_after_start",
        False,
        f"timeout={timeout_s}s | tts={is_port_open('127.0.0.1', 18180)} | f2f={is_port_open('127.0.0.1', 8383)}",
    )
    return False


def render_fallback_video(
    env: dict[str, str],
    checks: list[tuple[str, bool, str]],
    source_stem: str,
    model_dir: Path,
    model_rel: str,
) -> Path:
    max_seconds = int(env.get("MAX_RENDER_SECONDS", "18"))
    tts_audio_path = generate_openai_tts_audio(env=env, checks=checks, source_stem=source_stem)
    artifacts_dir = artifacts_dir_for_stem(source_stem)

    scene_sources = [
        INIT_ASSET_DIR / "WhatsApp Video 2026-04-14 at 09.02.34.mp4",
        INIT_ASSET_DIR / "WhatsApp Video 2026-04-14 at 09.02.26.mp4",
        INIT_ASSET_DIR / "WhatsApp Video 2026-04-14 at 09.02.41.mp4",
    ]
    if not all(path.exists() for path in scene_sources):
        source_video = model_dir / model_rel
        if not source_video.exists():
            raise FileNotFoundError(f"Fallback source video not found: {source_video}")
        scene_sources = [source_video, source_video, source_video]
        append_check(checks, "storyboard_sources", False, "init_ASSET videos missing, single-source fallback used")
    else:
        append_check(checks, "storyboard_sources", True, "using 3 init_ASSET videos")

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    segment_plan = [
        (scene_sources[0], 0.5, 3.0),  # hook
        (scene_sources[0], 4.0, 2.0),  # problem
        (scene_sources[1], 8.0, 4.0),  # errors
        (scene_sources[1], 15.0, 2.0),  # explanation
        (scene_sources[2], 6.0, 4.0),  # solution
        (scene_sources[0], 10.0, 3.0),  # CTA
    ]

    segment_paths: list[Path] = []
    for idx, (src, start_at, duration) in enumerate(segment_plan, start=1):
        seg_path = artifacts_dir / f"{source_stem}.scene_{idx:02d}.mp4"
        seg_cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(start_at),
            "-t",
            str(duration),
            "-i",
            str(src),
            "-an",
            "-vf",
            "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "30",
            "-pix_fmt",
            "yuv420p",
            str(seg_path),
        ]
        subprocess.run(seg_cmd, check=True, cwd=ROOT_DIR)
        segment_paths.append(seg_path)
    append_check(checks, "storyboard_segments", True, f"segments={len(segment_paths)}")

    concat_list_path = artifacts_dir / f"{source_stem}.concat.txt"
    concat_lines = [f"file '{path.as_posix()}'" for path in segment_paths]
    concat_list_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    storyboard_base = artifacts_dir / f"{source_stem}.storyboard_base.mp4"
    concat_cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "29",
        "-pix_fmt",
        "yuv420p",
        str(storyboard_base),
    ]
    subprocess.run(concat_cmd, check=True, cwd=ROOT_DIR)
    append_check(checks, "storyboard_concat", storyboard_base.exists(), str(storyboard_base))

    font_expr = "font='Arial'"
    overlays = [
        (0, 3, "Les 3 erreurs du petit-dej"),
        (3, 5, "Jamais vraiment cale"),
        (5, 10, "IG eleve = faim rapide"),
        (10, 12, "Rapide mais pas rassasiant"),
        (12, 17, "IG bas = energie stable"),
        (17, 18, "Rejoins Glyce - lien en bio"),
    ]
    draw_filters = []
    for start_t, end_t, text in overlays:
        draw_filters.append(
            "drawtext="
            + font_expr
            + f":text='{ffmpeg_escape_text(text)}'"
            + ":x=(w-text_w)/2:y=h*0.08:fontsize=42:fontcolor=white:borderw=3:bordercolor=black"
            + ":box=1:boxcolor=black@0.35:boxborderw=18"
            + f":enable='between(t,{start_t},{end_t})'"
        )
    overlay_filter = ",".join(draw_filters)

    storyboard_overlay = artifacts_dir / f"{source_stem}.storyboard_overlay.mp4"
    overlay_cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(storyboard_base),
        "-vf",
        overlay_filter,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "29",
        "-pix_fmt",
        "yuv420p",
        str(storyboard_overlay),
    ]
    subprocess.run(overlay_cmd, check=True, cwd=ROOT_DIR)
    append_check(checks, "storyboard_overlay", storyboard_overlay.exists(), str(storyboard_overlay))

    output_video = choose_writable_output(primary_rendered_path(source_stem))
    mux_cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(storyboard_overlay),
        "-i",
        str(tts_audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-t",
        str(max_seconds),
        "-shortest",
        "-vf",
        "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_video),
    ]
    subprocess.run(mux_cmd, check=True, cwd=ROOT_DIR)
    append_check(checks, "fallback_video_mux", output_video.exists(), f"output={output_video}")

    for temp_file in segment_paths + [concat_list_path, storyboard_base, storyboard_overlay]:
        try:
            if temp_file.exists():
                temp_file.unlink()
        except OSError:
            pass

    return output_video


def write_checklist(
    source_stem: str,
    checks: list[tuple[str, bool, str]],
    final_video: Path | None,
    used_fallback: bool,
) -> Path:
    artifacts_dir = artifacts_dir_for_stem(source_stem)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    checklist_path = artifact_path(source_stem, "pipeline_checklist.md")

    lines = [
        "# Pipeline Checklist",
        "",
        f"- source_stem: `{source_stem}`",
        f"- generated_at_video: `{final_video}`" if final_video else "- generated_at_video: `none`",
        f"- fallback_used: `{used_fallback}`",
        "",
        "## Steps",
    ]

    for name, ok, detail in checks:
        icon = "✅" if ok else "❌"
        lines.append(f"- {icon} `{name}` — {detail}")

    checklist_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return checklist_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one-command CONTENT_CREATION pipeline.")
    parser.add_argument(
        "--source",
        required=True,
        help="Markdown brief in CONTENT_CREATION (e.g. 1.md)",
    )
    args = parser.parse_args()

    source_name = Path(args.source).name
    source_path = CONTENT_DIR / source_name
    source_stem = Path(source_name).stem
    checks: list[tuple[str, bool, str]] = []
    final_video: Path | None = None
    used_fallback = False

    if not source_path.exists():
        append_check(checks, "source_exists", False, str(source_path))
        write_checklist(source_stem, checks, None, False)
        print(f"ERROR: missing source file {source_path}")
        return 1
    append_check(checks, "source_exists", True, str(source_path))

    env = load_env_file()
    case_dir = case_dir_for_stem(source_stem)
    artifacts_dir = artifacts_dir_for_stem(source_stem)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    source_copy = source_copy_path(source_stem)
    source_copy.write_text(source_path.read_text(encoding="utf-8").strip() + "\n", encoding="utf-8")
    append_check(checks, "source_copied_to_case_dir", True, str(source_copy))

    # Step 1: prompt generation
    rc_prompt = run_command(
        checks=checks,
        name="build_perfect_prompt",
        cmd=[sys.executable, str(CONTENT_DIR / "embed_and_build_prompt.py"), "--source", source_name],
        cwd=ROOT_DIR,
    )
    if rc_prompt != 0:
        write_checklist(source_stem, checks, None, False)
        return 1

    try:
        provider = env.get("TEXT_TO_VIDEO_PROVIDER", "sora").strip().lower()
        append_check(checks, "text_to_video_provider", True, provider)

        if provider == "sora":
            try:
                final_video = render_sora_video(env=env, checks=checks, source_stem=source_stem)
            except Exception as sora_exc:  # pylint: disable=broad-except
                append_check(checks, "sora_failed", False, str(sora_exc))
                allow_storyboard_fallback = env.get("ALLOW_STORYBOARD_FALLBACK", "0").strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                if not allow_storyboard_fallback:
                    raise

                used_fallback = True
                append_check(checks, "storyboard_fallback_enabled", True, "ALLOW_STORYBOARD_FALLBACK=1")
                model_dir, model_rel, _ = ensure_local_assets(env, checks)
                final_video = render_fallback_video(
                    env=env,
                    checks=checks,
                    source_stem=source_stem,
                    model_dir=model_dir,
                    model_rel=model_rel,
                )
        elif provider == "duix":
            model_dir, model_rel, reference_audio_path = ensure_local_assets(env, checks)
            append_check(checks, "model_relpath", True, model_rel)
            append_check(checks, "reference_audio_path", reference_audio_path.exists(), str(reference_audio_path))

            services_ready = try_start_duix_services(env, checks)
            rc_render = run_command(
                checks=checks,
                name="duix_render_test",
                cmd=[sys.executable, str(CONTENT_DIR / "render_video_test.py"), "--source-stem", source_stem],
                cwd=ROOT_DIR,
            )
            duix_video = primary_rendered_path(source_stem)
            if rc_render == 0 and duix_video.exists():
                final_video = duix_video
            else:
                append_check(checks, "duix_render_output_exists", False, str(duix_video))
                used_fallback = True
                if not services_ready:
                    append_check(
                        checks,
                        "duix_services_status",
                        False,
                        "fallback triggered because services are unavailable",
                    )
                final_video = render_fallback_video(
                    env=env,
                    checks=checks,
                    source_stem=source_stem,
                    model_dir=model_dir,
                    model_rel=model_rel,
                )
        elif provider == "storyboard":
            used_fallback = True
            model_dir, model_rel, _ = ensure_local_assets(env, checks)
            final_video = render_fallback_video(
                env=env,
                checks=checks,
                source_stem=source_stem,
                model_dir=model_dir,
                model_rel=model_rel,
            )
        else:
            raise ValueError(f"Unsupported TEXT_TO_VIDEO_PROVIDER: {provider}")

    except Exception as exc:  # pylint: disable=broad-except
        append_check(checks, "pipeline_exception", False, str(exc))
        checklist = write_checklist(source_stem, checks, final_video, used_fallback)
        print(f"Checklist written: {checklist}")
        return 1

    checklist = write_checklist(source_stem, checks, final_video, used_fallback)
    print(f"Final video: {final_video}")
    print(f"Checklist written: {checklist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
