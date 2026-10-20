"""Shut a Camber GPU node down when a sweep ends, so no credits burn after the run.

    setsid nohup python3 scripts/gpu_autostop.py <PID of run_gpu.sh> [grace_s] \
        > results_gpu/autostop.log 2>&1 < /dev/null &

Run it on the node (docs/gpu_howto.md). It waits until the process exits, waits `grace_s`
seconds (default 600; kill the watcher to cancel), then asks the node's own Jupyter server
to shut down (the API behind JupyterLab's File > Shut Down). On a JupyterHub node such as
Camber's this ends the server, i.e. the node. It authenticates with the server's own token
(JUPYTERHUB_API_TOKEN, scope access:servers on this server only) and checks at start that
the token is accepted. Safety net for sessions that end before the sweep does; still press
STOP in the web app if the node shows as running afterwards.
"""
import datetime
import os
import sys
import time
import urllib.request

PID = int(sys.argv[1])
GRACE = int(sys.argv[2]) if len(sys.argv) > 2 else 600
BASE = os.environ["JUPYTERHUB_SERVICE_URL"].replace("0.0.0.0", "127.0.0.1").rstrip("/") + "/api"
HEADERS = {"Authorization": "token " + os.environ["JUPYTERHUB_API_TOKEN"]}


def log(msg):
    print(f"{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M:%S} UTC {msg}", flush=True)


def call(path, method="GET"):
    req = urllib.request.Request(BASE + path, headers=HEADERS, method=method,
                                 data=b"" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def running(pid):
    """True while the process exists and is not a zombie (the sweep is re-parented to the
    container's init, which may not reap it)."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


log(f"watching PID {PID}; server API check -> HTTP {call('/status')}")
while running(PID):
    time.sleep(60)
log(f"PID {PID} finished; shutting the node down in {GRACE} s (kill {os.getpid()} to cancel)")
time.sleep(GRACE)
log("shutting down")
log(f"shutdown -> HTTP {call('/shutdown', 'POST')}")
