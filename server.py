"""Seleciona o backend explicitamente, sem fallback silencioso."""
import os
import runpy
from pathlib import Path

backend = os.environ.get('CONTROLAI_BACKEND', 'supabase')
if backend == 'sqlite':
    runpy.run_path(str(Path(__file__).with_name('sqlite_server.py')), run_name='__main__')
elif backend == 'supabase':
    from supabase_server import serve
    serve()
else:
    raise SystemExit('CONTROLAI_BACKEND deve ser supabase ou sqlite.')
