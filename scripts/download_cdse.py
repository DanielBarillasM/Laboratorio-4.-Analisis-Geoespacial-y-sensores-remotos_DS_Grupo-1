"""Descarga productos derivados desde CDSE sin almacenar credenciales.

Ejemplo de prueba:
    python scripts/download_cdse.py --lake amatitlan --limit 1 --submit

Ejemplo completo:
    python scripts/download_cdse.py --lake all --submit
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lab4.config import RAW_DIR, ensure_output_directories, load_observations  # noqa: E402
from lab4.copernicus import (  # noqa: E402
    authenticate_cdse,
    build_lake_timeseries_cube,
    connect_cdse,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lake",
        choices=["atitlan", "amatitlan", "all"],
        default="all",
        help="Lago que se procesará.",
    )
    parser.add_argument("--resolution", type=float, default=20, help="Resolución de salida en metros.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita el número de fechas por lago para una prueba controlada.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Crea y ejecuta trabajos. Sin esta bandera solo valida las gráficas de proceso.",
    )
    return parser.parse_args()


def update_manifest(entry: dict) -> None:
    manifest_path = ROOT / "data" / "jobs" / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = []
    manifest.append(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    args = parse_args()
    ensure_output_directories()
    observations = load_observations()
    lakes = ["atitlan", "amatitlan"] if args.lake == "all" else [args.lake]

    connection = connect_cdse()
    cubes = {}
    for lake in lakes:
        lake_dates = observations.loc[observations["lago"] == lake, "fecha"].dt.date.astype(str).tolist()
        if args.limit is not None:
            lake_dates = lake_dates[: args.limit]
        cube = build_lake_timeseries_cube(
            connection,
            lake,
            lake_dates,
            resolution=args.resolution,
        )
        validation_errors = connection.validate_process_graph(cube)
        if validation_errors:
            raise RuntimeError(f"La gráfica de {lake} no es válida: {validation_errors}")
        cubes[lake] = (cube, lake_dates)
        print(f"[validado] {lake}: {len(lake_dates)} fecha(s), bandas NDVI/NDWI/CYA")

    if not args.submit:
        print("Validación terminada. Use --submit para autenticar, procesar y descargar.")
        return 0

    token_path = ROOT / "data" / "jobs" / "access_token.txt"
    if token_path.exists():
        access_token = token_path.read_text(encoding="utf-8").strip()
        token_path.unlink()
        connection.authenticate_oidc_access_token(access_token, provider_id="CDSE")
        print("[autenticado] Se utilizó y eliminó el token temporal.")
    else:
        authenticate_cdse(connection)
    submitted = []
    for lake, (cube, lake_dates) in cubes.items():
        title = f"Lab4 {lake} indices {lake_dates[0]} a {lake_dates[-1]}"
        job = cube.create_job(
            out_format="GTiff",
            title=title,
            description="NDVI, NDWI y proxy Se2WaQ de cianobacteria; máscara SCL y NDWI.",
        )
        created = {
            "job_id": job.job_id,
            "lago": lake,
            "fechas": lake_dates,
            "resolucion_m": args.resolution,
            "creado_utc": datetime.now(timezone.utc).isoformat(),
            "estado": "created",
        }
        update_manifest(created)
        print(f"[creado] {lake}: trabajo {job.job_id}")
        job.start_job()
        submitted.append((lake, lake_dates, job, created))
        print(f"[iniciado] {lake}: trabajo {job.job_id}")

    for lake, lake_dates, job, created in submitted:
        consecutive_connection_errors = 0
        while True:
            try:
                status = job.status()
                consecutive_connection_errors = 0
            except requests.RequestException as exc:
                consecutive_connection_errors += 1
                if consecutive_connection_errors > 10:
                    raise RuntimeError(
                        f"No se pudo consultar {job.job_id} después de 10 reintentos"
                    ) from exc
                print(
                    f"[red] {lake}: consulta fallida; reintento "
                    f"{consecutive_connection_errors}/10 en 30 s"
                )
                time.sleep(30)
                continue
            print(f"[estado] {lake}: {status}")
            if status in {"finished", "error", "canceled"}:
                break
            time.sleep(30)
        if status != "finished":
            update_manifest({**created, "estado": status})
            print(f"[advertencia] {lake}: el trabajo terminó con estado {status}")
            continue
        output_dir = RAW_DIR / lake
        output_dir.mkdir(parents=True, exist_ok=True)
        downloaded = job.get_results().download_files(output_dir)
        update_manifest({**created, "estado": "downloaded", "archivos": [str(p) for p in downloaded]})
        print(f"[descargado] {lake}: {len(downloaded)} archivo(s) en {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
