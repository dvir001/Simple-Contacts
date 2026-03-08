"""Gunicorn configuration for SimpleContacts."""

import logging
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
timeout = 120

# ---- Logging ---- #

# Compact access-log format: timestamp  method  path  status  response-time
access_log_format = '%(t)s "%(m)s %(U)s%(q)s" %(s)s %(b)s %(D)sµs'
accesslog = "-"
errorlog = "-"
loglevel = "info"


class AccessLogFilter(logging.Filter):
    """Suppress noisy access-log lines (static assets, health checks)."""

    def filter(self, record):
        try:
            args = getattr(record, "args", None)
            if isinstance(args, dict):
                path = args.get("U", "") or ""
                status = str(args.get("s", ""))
                remote_addr = args.get("h", "") or ""
                user_agent = args.get("a", "") or ""

                # Static files
                if path.startswith("/static/"):
                    return False

                # Settings polling
                if "/api/settings" in path and status == "200":
                    return False

                # Health-check probes from localhost / curl
                if path == "/" and status == "200" and (
                    remote_addr == "127.0.0.1" or "curl/" in user_agent
                ):
                    return False
        except Exception:
            pass
        return True


def when_ready(server):
    """Attach the filter once gunicorn is ready."""
    logging.getLogger("gunicorn.access").addFilter(AccessLogFilter())
