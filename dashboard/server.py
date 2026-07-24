"""server - a dependency-free local web server that drives the studio
pipeline and exposes live state to the dashboard UI. Run it via app.py.
"""

import json
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from studio import (settings, logs, assets, pipeline,
                    narration_profile as NP, narration, transcript as T)

HERE = Path(__file__).resolve().parent

STATE = {
    "running": False,
    "stage": {"index": 0, "total": len(pipeline.STAGES), "name": "Idle"},
    "stages": [{"name": n, "status": "pending"} for n in pipeline.STAGES],
    "progress": 0.0,
    "detail": "",
    "metrics": {},
    "log": [],
    "result": None,
    "project": settings.load_config().get("subject", "") or "Untitled",
}
_LOCK = threading.Lock()


def _reset_stages():
    with _LOCK:
        STATE["stages"] = [{"name": n, "status": "pending"}
                           for n in pipeline.STAGES]
        STATE["progress"] = 0.0
        STATE["detail"] = ""
        STATE["metrics"] = {}
        STATE["log"] = []
        STATE["result"] = None


def _on_event(ev):
    with _LOCK:
        t = ev.get("type")
        if t == "log":
            STATE["log"].append({"level": ev.get("level", "info"),
                                 "msg": ev.get("message", ""),
                                 "t": time.strftime("%H:%M:%S")})
            STATE["log"] = STATE["log"][-500:]
        elif t == "stage":
            i = ev["index"]
            STATE["stage"] = {"index": i, "total": ev["total"],
                              "name": ev["name"]}
            for k, s in enumerate(STATE["stages"], 1):
                if k < i:
                    s["status"] = "done"
                elif k == i:
                    s["status"] = "active"
                else:
                    s["status"] = "pending"
            STATE["progress"] = 0.0
        elif t == "progress":
            STATE["progress"] = ev["percent"]
            STATE["detail"] = ev.get("detail", "")
        elif t == "metric":
            STATE["metrics"][ev["key"]] = ev["value"]


logs.set_callback(_on_event)


def _sysinfo():
    info = {"cpu": None, "mem": None}
    try:
        import psutil
        info["cpu"] = psutil.cpu_percent(interval=None)
        info["mem"] = psutil.virtual_memory().percent
    except Exception:
        pass
    return info


def _run_pipeline(params):
    _reset_stages()
    with _LOCK:
        STATE["running"] = True
        STATE["project"] = params.get("name") or "Untitled"
    result = pipeline.generate(params)
    with _LOCK:
        STATE["running"] = False
        STATE["result"] = result
        final = "done" if result.get("ok") else "error"
        for s in STATE["stages"]:
            if s["status"] == "active":
                s["status"] = final
            elif s["status"] == "pending" and result.get("ok"):
                s["status"] = "done"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        if n:
            try:
                return json.loads(self.rfile.read(n))
            except Exception:
                return {}
        return {}

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            html = (HERE / "app.html").read_text(encoding="utf-8")
            return self._send(200, html, "text/html; charset=utf-8")
        if p == "/api/state":
            with _LOCK:
                st = dict(STATE)
            st["sys"] = _sysinfo()
            st["inventory"] = assets.inventory()
            st["project_slug"] = settings.PROJECT_SLUG
            st["project_dir"] = str(settings.PROJECT_DIR)
            st["projects"] = settings.list_projects()
            return self._send(200, st)
        if p == "/api/projects":
            return self._send(200, settings.list_projects())
        if p == "/api/logs.txt":
            return self._send(200, logs.export_text(), "text/plain")
        if p == "/api/settings":
            return self._send(200, settings.load_settings())
        if p.startswith("/api/preview/"):
            fn = p.rsplit("/", 1)[-1]
            fp = settings.CACHE / fn
            if not fp.exists():
                return self._send(404, {"error": "no sample"})
            data = fp.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        if p == "/api/video":
            cfg = settings.load_config()
            out = settings.output_path(cfg)
            if not out.exists():
                return self._send(404, {"error": "no video yet"})
            data = out.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            return self.wfile.write(data)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        p = self.path.split("?")[0]
        if p == "/api/generate":
            if STATE["running"]:
                return self._send(409, {"error": "already running"})
            params = self._body()
            threading.Thread(target=_run_pipeline, args=(params,),
                             daemon=True).start()
            return self._send(200, {"started": True})
        if p == "/api/import":
            b = self._body()
            if b.get("name"):                       # import into that subject
                settings.set_project(T.slugify(b["name"]))
                settings.ensure_dirs()
            n = assets.import_files(b.get("paths", []))
            return self._send(200, {"imported": n,
                                    "project": settings.PROJECT_SLUG,
                                    "inventory": assets.inventory()})
        if p == "/api/project":               # switch active project folder
            b = self._body()
            slug = T.slugify(b.get("name", "") or b.get("slug", ""))
            settings.set_project(slug)
            settings.ensure_dirs()
            cfg = settings.load_config()
            cfg["slug"] = slug
            settings.save_config(cfg)
            return self._send(200, {"project": slug,
                                    "inventory": assets.inventory()})
        if p == "/api/inventory":
            return self._send(200, assets.inventory())
        if p == "/api/settings":
            return self._send(200, settings.save_settings(self._body()))
        if p == "/api/analyze":
            b = self._body()
            text = b.get("text")
            tp = b.get("transcript_path") or \
                settings.load_config().get("transcript")
            try:
                if text:
                    return self._send(200, NP.analyze(text=text))
                if tp and Path(tp).exists():
                    return self._send(200, NP.analyze(transcript_path=tp))
            except Exception as e:
                return self._send(200, {"error": str(e)})
            return self._send(200, {"error": "no transcript to analyze"})
        if p == "/api/preview":
            b = self._body()
            key = b.get("profile", NP.DEFAULT_PROFILE)
            v, rate, pitch = NP.resolve(key, int(b.get("pace", 0)),
                                        int(b.get("energy", 0)))
            fn = f"preview_{key}_{rate}_{pitch}.mp3".replace("+", "p") \
                .replace("%", "").replace(" ", "")
            out = settings.CACHE / fn
            try:
                if not out.exists():
                    narration.preview_sample(v, rate, pitch,
                                             NP.PREVIEW_TEXT, out)
                return self._send(200, {"url": f"/api/preview/{fn}",
                                        "voice": v, "rate": rate})
            except Exception as e:
                return self._send(200, {"error": str(e)})
        return self._send(404, {"error": "not found"})


def serve(port=8760, open_browser=True):
    settings.ensure_dirs()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Documentary Studio dashboard -> {url}\n")
    if open_browser:
        try:
            import webbrowser
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
