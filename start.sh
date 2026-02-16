#!/bin/sh
# PORT Railway tarafından set edilir; yoksa 8000 kullan
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --timeout-keep-alive 0 --timeout-graceful-shutdown 0
