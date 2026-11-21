# 系统后台 (/admin/) and its static files, served only by the admin server block (listen 8081), which Compose
# publishes on the host's 127.0.0.1: open it on the server, or through an SSH tunnel. Included from that block.
    location = /admin/login/ {
        limit_req zone=login burst=20 nodelay;
        limit_req_status 429;
        proxy_pass http://backend:8000;
        # With the port: Django's CSRF check compares the browser's Origin (http://localhost:8091) with it.
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /admin/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Django admin static files (collectstatic output, shared volume).
    location /static/ {
        alias /srv/static/;
    }

    location / {
        return 404;
    }
