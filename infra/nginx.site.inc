# Shared HTTP/HTTPS application paths. Included from a server block.
    # Matches MAX_UPLOAD_SIZE (2GB) plus multipart overhead. Request buffering stays on so
    # slow client uploads do not tie up Gunicorn workers.
    client_max_body_size 2100m;
    client_body_timeout 600s;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    location = /api/auth/login/ {
        limit_req zone=login burst=20 nodelay;
        limit_req_status 429;
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /admin/login/ {
        limit_req zone=login burst=20 nodelay;
        limit_req_status 429;
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /admin/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Django admin static files (collectstatic output, shared volume).
    location /static/ {
        alias /srv/static/;
    }

    # Vue SPA with history-mode fallback.
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
