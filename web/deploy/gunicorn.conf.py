# Gunicorn config for the Forge-a-Class app on a DigitalOcean droplet.
# Run from the web/ dir:  gunicorn --config deploy/gunicorn.conf.py app:app
#
# gthread workers (not the default sync) because /api/forge-class holds one connection open for the whole
# multi-minute forge as it streams SSE progress — threads let other requests through meanwhile. `timeout`
# is generous so gunicorn never kills a worker mid-forge.

bind = "127.0.0.1:8000"
workers = 1            # 1GB droplet: one worker fits comfortably; the forge is I/O-bound so threads, not
                       # workers, give the concurrency. Bump to 2 only on a larger box (>=2GB RAM).
worker_class = "gthread"
threads = 8            # each in-flight forge uses ~2 threads (the request + its background worker)
timeout = 600          # a full class forge can take several minutes
graceful_timeout = 30
keepalive = 5
accesslog = "-"        # -> journald via systemd
errorlog = "-"
