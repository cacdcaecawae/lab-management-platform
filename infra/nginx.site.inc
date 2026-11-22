# Shared HTTP/HTTPS application paths. Included from a server block.
    # Matches MAX_UPLOAD_SIZE (2GB) plus multipart overhead. Request buffering stays on so
    # slow client uploads do not tie up Gunicorn workers.
    client_max_body_size 2100m;
    client_body_timeout 600s;

    # Applied at server level so HTTPS HSTS (nginx.https.conf.template) is inherited everywhere;
    # API locations hide upstream duplicates from Django's SecurityMiddleware.
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "same-origin" always;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Referrer-Policy;
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
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Referrer-Policy;
    }

    # 系统后台 is not on the public port: see nginx.admin.inc.
    location /admin/ {
        return 404;
    }

    # Hashed Vite assets can be cached long-term; index.html must revalidate after upgrades.
    # Uses `expires` instead of `add_header` so server-level security / HSTS headers stay inherited.
    location ^~ /assets/ {
        root /usr/share/nginx/html;
        expires 1y;
    }

    location = /index.html {
        root /usr/share/nginx/html;
        expires -1;
    }

    # Vue SPA with history-mode fallback.
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
