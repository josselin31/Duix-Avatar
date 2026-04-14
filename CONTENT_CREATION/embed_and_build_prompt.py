#!/usr/bin/env python3
"""Build a Duix-ready prompt package from a simple content brief."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path

from openai import OpenAI

ROOT_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT_DIR / "CONTENT_CREATION"
REVERSE_DIR = ROOT_DIR / "init_ASSET" / "REVERSE_PROMPT"
OUTPUT_DIR = CONTENT_DIR / "GENERATED"
ENV_PATH = ROOT_DIR / ".env"


def load_env_file() -> dict[str, str]:
    if not ENV_PATH.exists():
        raise FileNotFoundError(f"Missing .env file at {ENV_PATH}")

    result: dict[str, str] = {}
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        result[key] = value
    return result


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def clean_reverse_prompt(raw: str) -> str:
    lines = [line for line in raw.splitlines() if not line.strip().startswith("<!--")]
    return "\n".join(lines).strip()


def build_reverse_chunks() -> list[dict[str, str]]:
    files = sorted(REVERSE_DIR.glob("REVERSE_PROMPT_*.md"))
    if not files:
        raise FileNotFoundError(f"No reverse prompt files found in {REVERSE_DIR}")

    chunks: list[dict[str, str]] = []
    for file_path in files:
        text = clean_reverse_prompt(file_path.read_text(encoding="utf-8"))
        # Full context chunk
        chunks.append(
            {
                "source_file": file_path.name,
                "chunk_id": f"{file_path.stem}:full",
                "text": text,
            }
        )

        # Section chunks
        sections = re.split(r"(?m)^##\s+", text)
        for section in sections:
            section = section.strip()
            if not section:
                continue
            title = section.splitlines()[0].strip().lower().replace(" ", "_")
            chunks.append(
                {
                    "source_file": file_path.name,
                    "chunk_id": f"{file_path.stem}:{title}",
                    "text": "## " + section,
                }
            )
    return chunks


def extract_narration_block(markdown_text: str) -> str:
    markers = [
        ("## DUIX_NARRATION_SCRIPT", "##"),
        ("## NARRATION_SCRIPT_DUIX", "##"),
    ]
    for marker, next_header in markers:
        if marker not in markdown_text:
            continue
        tail = markdown_text.split(marker, 1)[1].strip()
        if f"\n{next_header} " in tail:
            tail = tail.split(f"\n{next_header} ", 1)[0].strip()
        return tail.strip()
    return ""


def case_dir_for_stem(stem: str) -> Path:
    return OUTPUT_DIR / stem


def artifacts_dir_for_stem(stem: str) -> Path:
    return case_dir_for_stem(stem) / "artifacts"


def resolve_source_files(source_value: str, process_all: bool) -> list[Path]:
    if process_all:
        files = sorted(
            p for p in CONTENT_DIR.glob("*.md") if p.name.lower() != "readme.md" and p.parent.name != "GENERATED"
        )
        if not files:
            raise FileNotFoundError(f"No source markdown files found in {CONTENT_DIR}")
        return files

    source_path = Path(source_value)
    if not source_path.is_absolute():
        source_path = (CONTENT_DIR / source_value).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Missing source file: {source_path}")
    return [source_path]


def process_source_file(
    source_file: Path,
    reverse_chunks: list[dict[str, str]],
    client: OpenAI,
    prompt_model: str,
    embedding_model: str,
    top_k: int,
) -> None:
    source_text = source_file.read_text(encoding="utf-8").strip()
    if not source_text:
        raise ValueError(f"Source file is empty: {source_file}")

    embedding_inputs = [source_text] + [chunk["text"] for chunk in reverse_chunks]
    embeddings = client.embeddings.create(model=embedding_model, input=embedding_inputs).data
    source_vector = embeddings[0].embedding

    ranked = []
    for idx, chunk in enumerate(reverse_chunks, start=1):
        score = cosine_similarity(source_vector, embeddings[idx].embedding)
        ranked.append({**chunk, "score": score})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    selected = ranked[: max(1, top_k)]

    context_blocks = []
    for index, item in enumerate(selected, start=1):
        context_blocks.append(
            (
                f"[Contexte {index}] source={item['source_file']} "
                f"chunk={item['chunk_id']} score={item['score']:.4f}\n"
                f"{item['text']}"
            )
        )

    system_instruction = (
        "Tu es un prompt engineer expert short-video (TikTok/Reels) et un integrateur Duix.Avatar. "
        "Tu dois transformer un brief simple en package de prompt ultra exploitable. "
        "Important: Duix.Avatar utilise une narration texte continue pour la voix, "
        "et ne comprend pas directement les storyboards complexes. "
        "Tu dois donc produire une version compatible Duix."
    )

    user_instruction = f"""
Brief source (a transformer):
{source_text}

Contextes reverse prompts (retrieves via embeddings):
{chr(10).join(context_blocks)}

Rends exactement en Markdown avec cette structure:

# PERFECT_PROMPT_PACKAGE
## MASTER_VIDEO_PROMPT
<prompt principal tres concret, en francais, pret a copier dans un modele text-to-video>

## NEGATIVE_PROMPT
<liste virgulee concise>

## DUIX_NARRATION_SCRIPT
<texte parle continu en francais, 45 a 70 mots max, naturel, sans jargon medical>

## ON_SCREEN_OVERLAYS
- [00:00-00:03] ...
- [00:03-00:05] ...
- [00:05-00:10] ...
- [00:10-00:12] ...
- [00:12-00:17] ...
- [00:17-00:20] ...

## DUIX_RENDER_NOTES
- format: 9:16
- duree cible: 15-20s
- ton voix: ...
- rythme: ...
- call to action: ...

Contraintes:
- reste coherent avec le brief source
- integre le style visuel des reverse prompts les plus pertinents
- priorise clarte, viralite, lisibilite mobile
- pas de promesses medicales
"""

    response = client.responses.create(
        model=prompt_model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": system_instruction}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_instruction}]},
        ],
        max_output_tokens=1500,
    )

    output_text = (response.output_text or "").strip()
    if not output_text:
        raise RuntimeError("OpenAI returned an empty response for prompt generation.")

    stem = source_file.stem
    case_dir = case_dir_for_stem(stem)
    artifacts_dir = artifacts_dir_for_stem(stem)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    source_copy = case_dir / f"{stem}.md"
    source_copy.write_text(source_text.strip() + "\n", encoding="utf-8")

    prompt_output = artifacts_dir / f"{stem}.perfect_prompt.md"
    prompt_output.write_text(output_text + "\n", encoding="utf-8")

    narration = extract_narration_block(output_text)
    narration_output = artifacts_dir / f"{stem}.duix_narration.txt"
    narration_output.write_text((narration or "").strip() + "\n", encoding="utf-8")

    ranking_output = artifacts_dir / f"{stem}.context_ranking.json"
    ranking_output.write_text(
        json.dumps(
            [
                {
                    "source_file": item["source_file"],
                    "chunk_id": item["chunk_id"],
                    "score": round(item["score"], 6),
                }
                for item in ranked
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"[ok] source: {source_file.relative_to(ROOT_DIR)}")
    print(f"     prompt package: {prompt_output.relative_to(ROOT_DIR)}")
    print(f"     duix narration: {narration_output.relative_to(ROOT_DIR)}")
    print(f"     context ranking: {ranking_output.relative_to(ROOT_DIR)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed reverse prompts and generate Duix-ready prompt packages.")
    parser.add_argument(
        "--source",
        default="1.md",
        help="Source markdown file name/path in CONTENT_CREATION (default: 1.md)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all markdown files in CONTENT_CREATION",
    )
    args = parser.parse_args()

    env = load_env_file()
    api_key = env.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")

    prompt_model = env.get("OPENAI_PROMPT_MODEL", "gpt-4.1")
    embedding_model = env.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    top_k = int(env.get("REVERSE_CONTEXT_TOP_K", "5"))

    source_files = resolve_source_files(args.source, args.all)
    reverse_chunks = build_reverse_chunks()
    client = OpenAI(api_key=api_key)

    for source_file in source_files:
        process_source_file(
            source_file=source_file,
            reverse_chunks=reverse_chunks,
            client=client,
            prompt_model=prompt_model,
            embedding_model=embedding_model,
            top_k=top_k,
        )

    print(f"Processed {len(source_files)} source file(s).")
    print(f"Models used: prompt={prompt_model}, embedding={embedding_model}, top_k={top_k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
