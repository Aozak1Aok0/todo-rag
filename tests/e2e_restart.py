# 真·重启测试：起两次 uvicorn 子进程（共享同一个临时 DB），验证数据跨进程存活。
import os, subprocess, sys, tempfile, time
from pathlib import Path
import httpx

APP = Path(__file__).resolve().parent.parent
PY = APP / '.venv' / 'Scripts' / 'python.exe'
db = Path(tempfile.mkdtemp(prefix='e2e-db-')) / 'e2e.db'
env = dict(os.environ, TODO_DB=str(db))

def start():
    p = subprocess.Popen([str(PY), '-m', 'uvicorn', 'main:app', '--port', '8123'],
                         cwd=str(APP), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            httpx.get('http://127.0.0.1:8123/', timeout=1)
            return p
        except Exception:
            time.sleep(0.25)
    p.terminate(); raise SystemExit('server did not start')

p1 = start()
r = httpx.post('http://127.0.0.1:8123/api/todos', json={'name': '跨进程存活'}, timeout=10)
print('POST', r.status_code, r.json())
p1.terminate(); p1.wait(timeout=10)

p2 = start()
names = [t['name'] for t in httpx.get('http://127.0.0.1:8123/api/todos', timeout=10).json()]
print('重启后 names =', names)
p2.terminate(); p2.wait(timeout=10)
print('OK' if '跨进程存活' in names else 'FAIL: 数据没活过重启')
print('db =', db, 'exists =', db.exists())
