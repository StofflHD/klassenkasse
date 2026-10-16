# Reverse-Proxy / HTTPS

Die Klassenkasse spricht selbst nur HTTP. Im Heimnetz reicht das; für Zugriff von außen
gehört ein Reverse-Proxy mit HTTPS davor – oder der Zugriff läuft nur per VPN (WireGuard,
Tailscale).

Nach dem Einrichten des Proxys in `/etc/klassenkasse.env`:

```
KK_BEHIND_PROXY=1
KK_COOKIE_SECURE=1
```

und `systemctl restart klassenkasse`. Mit `KK_COOKIE_SECURE=1` klappt die Anmeldung nur noch
über HTTPS – direkt per `http://<IP>:8000` nicht mehr.

**Wichtig für die IP-Sperre:** Ohne `KK_BEHIND_PROXY=1` sieht die Klassenkasse bei jedem
Zugriff nur die IP-Adresse des Proxys. Drei Tippfehler von irgendwem würden dann den Proxy
sperren – und damit alle. Mit `KK_BEHIND_PROXY=1` wertet die App `X-Forwarded-For` aus; der
Proxy muss diesen Header setzen (die Beispiele unten tun das). Läuft die Klassenkasse ohne
Proxy direkt erreichbar, bleibt `KK_BEHIND_PROXY=0`, sonst könnte jeder seine Adresse
vortäuschen.

## Nginx Proxy Manager

Neuer Proxy Host: Domain eintragen, Scheme `http`, Forward Hostname = IP des Containers,
Port `8000`. Unter *SSL* ein Let's-Encrypt-Zertifikat anfordern und *Force SSL* einschalten.

## Caddy

```
kasse.example.de {
    reverse_proxy 192.168.1.60:8000
}
```

## nginx

```nginx
server {
    listen 443 ssl;
    server_name kasse.example.de;
    # ssl_certificate …; ssl_certificate_key …;

    location / {
        proxy_pass http://192.168.1.60:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

## Hinweise

- Den Port 8000 nicht direkt im Router freigeben.
- Am besten nur den Proxy an den Container lassen, z. B. mit der Proxmox-Firewall
  (eingehend TCP 8000 nur von der IP des Proxys).
