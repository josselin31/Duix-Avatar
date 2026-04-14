#!/usr/bin/env python3
"""Attempt a first Duix rendering test from generated narration."""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT_DIR / "CONTENT_CREATION"
OUTPUT_ROOT = CONTENT_DIR / "GENERATED"
ENV_PATH = ROOT_DIR / ".env"


def case_dir_for_stem(stem: str) -> Path:
    return OUTPUT_ROOT / stem


def artifacts_dir_for_stem(stem: str) -> Path:
    return case_dir_for_stem(stem) / "artifacts"


def artifact_path(stem: str, suffix: str) -> Path:
    return artifacts_dir_for_stem(stem) / f"{stem}.{suffix}"


def load_env_file() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        result[key.strip()] = value
    return result


def is_port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def parse_host_port(url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return host, int(port)


def post_json(url: str, payload: dict) -> bytes:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        return response.read()


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def write_report(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Duix render test from a generated narration file.")
    parser.add_argument(
        "--source-stem",
        default="1",
        help="Base name used in CONTENT_CREATION/GENERATED outputs (default: 1)",
    )
    args = parser.parse_args()

    source_stem = Path(args.source_stem).stem
    env = load_env_file()
    artifacts_dir_for_stem(source_stem).mkdir(parents=True, exist_ok=True)
    case_dir_for_stem(source_stem).mkdir(parents=True, exist_ok=True)

    report_path = artifact_path(source_stem, "render_test_report.md")
    narration_path = artifact_path(source_stem, "duix_narration.txt")
    if not narration_path.exists():
        write_report(
            report_path,
            [
                "# Render Test Report",
                "",
                "Statut: ECHEC",
                "",
                f"- narration manquante: `{narration_path}`",
                "- Lance d'abord: `python CONTENT_CREATION/embed_and_build_prompt.py`",
            ],
        )
        print(f"Render test report saved to: {report_path}")
        return 1

    narration_text = narration_path.read_text(encoding="utf-8").strip()
    if not narration_text:
        write_report(
            report_path,
            [
                "# Render Test Report",
                "",
                "Statut: ECHEC",
                "",
                f"- narration vide: `{narration_path}`",
            ],
        )
        print(f"Render test report saved to: {report_path}")
        return 1

    tts_url = env.get("DUIX_TTS_URL", "http://127.0.0.1:18180/v1/invoke")
    f2f_submit_url = env.get("DUIX_F2F_SUBMIT_URL", "http://127.0.0.1:8383/easy/submit")
    f2f_query_url = env.get("DUIX_F2F_QUERY_URL", "http://127.0.0.1:8383/easy/query")
    model_dir = Path(env.get("DUIX_ASSET_MODEL_DIR", r"C:\duix_avatar_data\face2face\temp"))
    model_video_relpath = env.get("DUIX_MODEL_VIDEO_RELATIVE_PATH", "").strip()
    reference_audio = env.get("DUIX_REFERENCE_AUDIO", "").strip()
    reference_text = env.get("DUIX_REFERENCE_TEXT", "").strip()
    timeout_seconds = int(env.get("DUIX_RENDER_TIMEOUT_SECONDS", "900"))

    checks: list[str] = []
    errors: list[str] = []

    tts_host, tts_port = parse_host_port(tts_url)
    f2f_host, f2f_port = parse_host_port(f2f_submit_url)
    tts_open = is_port_open(tts_host, tts_port)
    f2f_open = is_port_open(f2f_host, f2f_port)
    checks.append(f"- tts endpoint `{tts_url}` reachable: `{tts_open}`")
    checks.append(f"- f2f endpoint `{f2f_submit_url}` reachable: `{f2f_open}`")

    if not tts_open:
        errors.append("Service TTS indisponible.")
    if not f2f_open:
        errors.append("Service Face2Face indisponible.")

    model_dir_exists = model_dir.exists()
    checks.append(f"- model dir exists `{model_dir}`: `{model_dir_exists}`")
    if not model_dir_exists:
        errors.append("Dossier model_dir introuvable.")

    if not model_video_relpath:
        errors.append("DUIX_MODEL_VIDEO_RELATIVE_PATH manquant dans .env.")
    else:
        checks.append(f"- model video relpath configured: `{model_video_relpath}`")

    if not reference_audio:
        errors.append("DUIX_REFERENCE_AUDIO manquant dans .env.")
    else:
        checks.append(f"- reference audio configured: `{reference_audio}`")

    if not reference_text:
        errors.append("DUIX_REFERENCE_TEXT manquant dans .env.")
    else:
        checks.append("- reference text configured: `true`")

    if errors:
        write_report(
            report_path,
            [
                "# Render Test Report",
                "",
                "Statut: ECHEC (pre-check)",
                "",
                "## Checks",
                *checks,
                "",
                "## Erreurs",
                *[f"- {item}" for item in errors],
                "",
                "## Actions",
                "- Demarrer les services Docker Duix (`18180` et `8383`).",
                "- Renseigner les variables DUIX_* dans `.env`.",
            ],
        )
        print(f"Render test report saved to: {report_path}")
        return 1

    job_uuid = str(uuid.uuid4())
    audio_filename = f"{job_uuid}.wav"
    audio_filepath = model_dir / audio_filename

    try:
        tts_payload = {
            "speaker": job_uuid,
            "text": narration_text,
            "format": "wav",
            "topP": 0.7,
            "max_new_tokens": 1024,
            "chunk_length": 100,
            "repetition_penalty": 1.2,
            "temperature": 0.7,
            "need_asr": False,
            "streaming": False,
            "is_fixed_seed": 0,
            "is_norm": 1,
            "reference_audio": reference_audio,
            "reference_text": reference_text,
        }
        audio_bin = post_json(tts_url, tts_payload)
        audio_filepath.write_bytes(audio_bin)

        submit_payload = {
            "audio_url": audio_filename,
            "video_url": model_video_relpath,
            "code": job_uuid,
            "chaofen": 0,
            "watermark_switch": 0,
            "pn": 1,
        }
        submit_res = json.loads(post_json(f2f_submit_url, submit_payload).decode("utf-8"))
        if submit_res.get("code") != 10000:
            raise RuntimeError(f"F2F submit failed: {submit_res}")

        deadline = time.time() + timeout_seconds
        query_url = f"{f2f_query_url}?code={urllib.parse.quote(job_uuid)}"
        final_status = None
        while time.time() < deadline:
            status_res = get_json(query_url)
            if status_res.get("code") in (9999, 10002, 10003):
                raise RuntimeError(f"F2F query returned error code: {status_res}")
            data = status_res.get("data") or {}
            status = data.get("status")
            if status == 2:
                final_status = status_res
                break
            if status == 3:
                raise RuntimeError(f"F2F generation failed: {status_res}")
            time.sleep(5)

        if not final_status:
            raise TimeoutError("Render polling timeout reached.")

        result_rel = final_status["data"]["result"]
        result_path = model_dir / Path(result_rel)
        if not result_path.exists():
            raise FileNotFoundError(f"Rendered file not found: {result_path}")

        final_output = case_dir_for_stem(source_stem) / f"{source_stem}.rendered.mp4"
        shutil.copy2(result_path, final_output)

        write_report(
            report_path,
            [
                "# Render Test Report",
                "",
                "Statut: SUCCES",
                "",
                "## Checks",
                *checks,
                "",
                "## Resultat",
                f"- job_code: `{job_uuid}`",
                f"- rendered_file: `{final_output}`",
                f"- source_result_relpath: `{result_rel}`",
            ],
        )
        print(f"Rendered video: {final_output}")
        print(f"Render test report saved to: {report_path}")
        return 0

    except (urllib.error.URLError, json.JSONDecodeError, RuntimeError, TimeoutError, FileNotFoundError) as exc:
        write_report(
            report_path,
            [
                "# Render Test Report",
                "",
                "Statut: ECHEC (runtime)",
                "",
                "## Checks",
                *checks,
                "",
                "## Erreur",
                f"- {exc}",
                "",
                "## Contexte",
                f"- model_dir: `{model_dir}`",
                f"- model_video_relpath: `{model_video_relpath}`",
                f"- tts_url: `{tts_url}`",
                f"- f2f_submit_url: `{f2f_submit_url}`",
            ],
        )
        print(f"Render test report saved to: {report_path}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
