#!/usr/bin/env python3
"""
EnergyWise web server.

Serves the dashboard UI and provides an /analyze endpoint that runs
the Python simulator on an uploaded C file and returns the JSON report.

Usage:
    python webui/server.py          # http://localhost:8080
    python webui/server.py 3000     # http://localhost:3000
"""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIM_SCRIPT = ROOT / "src" / "energywise.py"
MODEL_PATH = ROOT / "models" / "rv32imc_energy.yaml"
WEBUI_DIR = Path(__file__).resolve().parent

BENCHMARK_DIR = ROOT / "testcases"
BENCHMARK_NAMES = ["matmul.c", "fir.c", "scale.c", "sort.c", "dotprod.c"]


class EnergyWiseHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEBUI_DIR), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/benchmarks":
            self._handle_benchmarks()
        elif parsed.path.startswith("/api/benchmark/"):
            name = urllib.parse.unquote(parsed.path.split("/api/benchmark/")[-1])
            self._handle_run_benchmark(name)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/analyze":
            self._handle_analyze()
        else:
            self.send_error(404)

    def _handle_benchmarks(self):
        data = []
        for name in BENCHMARK_NAMES:
            path = BENCHMARK_DIR / name
            if path.exists():
                try:
                    data.append({
                        "name": name,
                        "source": path.read_text(),
                    })
                except Exception:
                    pass
        self._json_response(data)

    def _handle_run_benchmark(self, name):
        if name not in BENCHMARK_NAMES:
            self._json_response({"error": f"Unknown benchmark: {name}"}, status=404)
            return
        result = self._run_analysis(BENCHMARK_DIR / name)
        self._json_response(result)

    def _handle_analyze(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}

        source_code = payload.get("source", "")
        filename = payload.get("filename", "upload.c")

        if not source_code.strip():
            self._json_response({"error": "Empty source code"}, status=400)
            return

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".c", prefix="ew_", delete=False
        ) as tmp:
            tmp.write(source_code)
            tmp_path = tmp.name

        try:
            result = self._run_analysis(Path(tmp_path), display_name=filename)
        finally:
            os.unlink(tmp_path)

        self._json_response(result)

    def _run_analysis(self, source_path: Path, display_name: str = None) -> dict:
        report_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix="ew_report_", delete=False
            ) as rf:
                report_file = rf.name

            cmd = [
                sys.executable, str(SIM_SCRIPT),
                str(source_path),
                "--model", str(MODEL_PATH),
                "--mode", "sim",
                "--report", report_file,
                "--pretty",
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )

            if proc.returncode != 0:
                return {
                    "error": "Analysis failed",
                    "stderr": proc.stderr[:2000],
                }

            try:
                report = json.loads(Path(report_file).read_text())
            except (json.JSONDecodeError, FileNotFoundError) as e:
                return {
                    "error": f"Could not parse simulator output: {e}",
                    "stdout": proc.stdout[:1000] if proc.stdout else "",
                    "stderr": proc.stderr[:1000] if proc.stderr else "",
                }

            if display_name:
                report["module"] = display_name

            return report

        except subprocess.TimeoutExpired:
            return {"error": "Analysis timed out (30s)"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            if report_file:
                try:
                    os.unlink(report_file)
                except OSError:
                    pass

    def _json_response(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[EnergyWise] {args[0]}")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080

    print(f"  ⚡ EnergyWise Dashboard Server")
    print(f"  ─────────────────────────────")
    print(f"  UI:       http://localhost:{port}")
    print(f"  Analyze:  POST http://localhost:{port}/api/analyze")
    print(f"  Benchmarks: GET http://localhost:{port}/api/benchmarks")
    print()

    server = http.server.HTTPServer(("", port), EnergyWiseHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()