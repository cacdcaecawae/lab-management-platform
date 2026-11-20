# Certbot's webroot is mounted read-only by the web service.
location ^~ /.well-known/acme-challenge/ {
    root /srv/certbot/www;
    default_type text/plain;
    try_files $uri =404;
}
