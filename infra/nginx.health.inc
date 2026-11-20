# Require a real 204 from Django. No browser or public health probe.
location = /healthz {
    allow 127.0.0.1;
    allow ::1;
    deny all;
    proxy_pass http://backend:8000/api/auth/csrf/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_hide_header Set-Cookie;
    add_header Cache-Control "no-store" always;
}
