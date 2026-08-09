# Gunicorn config for the Forge-a-Class app on a DigitalOcean droplet.
# Run from the web/ dir:  gunicorn --config deploy/gunicorn.conf.py app:app
#
# gthread workers (not the default sync) because /api/forge-class holds one connection open for the whole
# multi-minute forge as it streams SSE progress — threads let other requests through meanwhile. `timeout`
# is generous so gunicorn never kills a worker mid-forge.

bind = "127.0.0.1:8000"
workers = 1            # MUST stay 1 while forge admission + the hosted daily cap are process-local
                       # (app.py) — a second worker would silently double both limits and split the
                       # forge queue. The forge is I/O-bound; threads give the concurrency on this box.
worker_class = "gthread"
threads = 32           # each running OR QUEUED forge holds one thread for its SSE stream (the forge
                       # work itself runs on separate daemon threads). 32 covers the admission worst
                       # case (3 running + 12 in line — app.py FORGE_* knobs) with ~2x headroom for
                       # page loads. gthreads are cheap here: they idle on I/O, not CPU.
timeout = 600          # a full class forge can take several minutes; queue wait rides the SSE
                       # keepalives, not this timeout
graceful_timeout = 30
keepalive = 5
accesslog = "-"        # -> journald via systemd
errorlog = "-"
