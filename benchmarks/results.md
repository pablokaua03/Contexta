| Repo | Tool | Tokens | Fits 128k | Time | Recall (files found) |
|---|---|---:|:---:|---:|---|
| flask | contexta (default) | 168,126 | no | 1.1s cold / 0.9s | 4/4 |
| flask | contexta --budget 20k --focus | 8,356 | yes | 0.8s cold / 0.6s | 3/4 (missing ctx.py) |
| flask | contexta --budget 20k --focus --no-graph | 17,174 | yes | 0.6s | 3/4 (missing ctx.py) |
| flask | repomix (default) | 285,568 | no | 0.6s | 4/4 |
| flask | repomix --compress | 228,991 | no | 0.7s | 4/4 |
| flask | repomix --compress --include src/flask/** | 53,926 | yes | 0.6s | 3/4 (missing test_session_interface.py) |
| flask | gitingest (default) | 402,444 | no | 0.9s | 4/4 |
| requests | contexta (default) | 71,689 | yes | 0.7s cold / 0.5s | 4/4 |
| requests | contexta --budget 20k --focus | 17,639 | yes | 0.6s cold / 0.5s | 4/4 |
| requests | contexta --budget 20k --focus --no-graph | 16,597 | yes | 0.4s | 4/4 |
| requests | repomix (default) | 685,407 | no | 0.6s | 3/4 (missing test_requests.py) |
| requests | repomix --compress | 663,115 | no | 0.7s | 2/4 (missing sessions.py, test_requests.py) |
| requests | repomix --compress --include src/requests/** | 32,080 | yes | 0.6s | 2/4 (missing sessions.py, test_requests.py) |
| requests | gitingest (default) | 170,996 | no | 0.7s | 4/4 |
| fastapi | contexta (default) | 2,108,026 | no | 10.4s cold / 8.6s | 5/5 |
| fastapi | contexta --budget 20k --focus | 17,677 | yes | 2.7s cold / 1.4s | 2/5 (missing params.py, models.py, test_dependency_cache.py) |
| fastapi | contexta --budget 20k --focus --no-graph | 17,723 | yes | 3.6s | 2/5 (missing params.py, models.py, test_dependency_cache.py) |
| fastapi | repomix (default) | 8,869,684 | no | 1.3s | 5/5 |
| fastapi | repomix --compress | 8,215,545 | no | 1.6s | 4/5 (missing utils.py) |
| fastapi | repomix --compress --include fastapi/** | 42,527 | yes | 0.7s | 2/5 (missing utils.py, routing.py, test_dependency_cache.py) |
| fastapi | gitingest (default) | 4,373,871 | no | 4.9s | 5/5 |
