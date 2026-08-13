"""Recupera y descarga trabajos CDSE ya iniciados sin volver a crearlos."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import openeo
import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from lab4.config import RAW_DIR  # noqa: E402


JOBS = {
    "atitlan": "j-2608132236374447b1ea616ffc52b543",
    "amatitlan": "j-2608132236584ce09552e7e1bd0e71dd",
}


def update_manifest(entry: dict) -> None:
    path = ROOT / "data" / "jobs" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    manifest.append(entry)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


token_path = ROOT / "data" / "jobs" / "access_token.txt"
if not token_path.exists():
    raise RuntimeError("Primero ejecute scripts/authenticate_cdse.py")
token = token_path.read_text(encoding="utf-8").strip()
token_path.unlink()
connection = openeo.connect("https://openeo.dataspace.copernicus.eu")
connection.authenticate_oidc_access_token(token, provider_id="CDSE")

for lake, job_id in JOBS.items():
    job = connection.job(job_id)
    errors = 0
    while True:
        try:
            status = job.status()
            errors = 0
        except requests.RequestException:
            errors += 1
            if errors > 10:
                raise
            print(f"[red] {lake}: reintento {errors}/10", flush=True)
            time.sleep(30)
            continue
        print(f"[estado] {lake}: {status}", flush=True)
        if status in {"finished", "error", "canceled"}:
            break
        time.sleep(30)
    if status != "finished":
        update_manifest({"job_id": job_id, "lago": lake, "estado": status})
        logs = job.logs()
        for entry in logs[-5:]:
            print(entry.get("level"), entry.get("message"), flush=True)
        continue
    output_dir = RAW_DIR / lake
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = job.get_results().download_files(output_dir)
    update_manifest(
        {
            "job_id": job_id,
            "lago": lake,
            "estado": "downloaded",
            "archivos": [str(path) for path in downloaded],
        }
    )
    print(f"[descargado] {lake}: {len(downloaded)} archivos", flush=True)
