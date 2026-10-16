# Reverse-Proxy / HTTPS

Die Klassenkasse spricht selbst nur HTTP. Im Heimnetz reicht das; für Zugriff von außen
gehört ein Reverse-Proxy mit HTTPS davor – oder der Zugriff läuft nur per VPN (WireGuard,
Tailscale).

Nach dem Einrichten des Proxys in `/etc/klassenkasse.env` die IP-Adresse des Proxys
eintragen – so, wie die Klassenkasse ihn sieht (bei Nginx Proxy Manager im eigenen LXC also
dessen IP):

```
KK_TRUSTED_PROXIES=192.168.1.10
KK_COOKIE_SECURE=1
```

und `systemctl restart klassenkasse`. Mit `KK_COOKIE_SECURE=1` klappt die Anmeldung nur noch
über HTTPS – direkt per `http://<IP>:8000` nicht mehr.

Unter *Benutzer → Gesperrte IP-Adressen* zeigt die Klassenkasse dann „Deine IP-Adresse: …
(über den Proxy …)“. Steht dort die Adresse deines Geräts bzw. Internetanschlusses, passt es.

### Warum das für die IP-Sperre wichtig ist

Hinter einem Proxy kommen alle Anfragen von der Adresse des Proxys. Die echte Adresse des
Besuchers steht im Header `X-Forwarded-For`, den der Proxy anhängt.

- **Ohne Einstellung** sieht die Klassenkasse nur den Proxy: drei Tippfehler von irgendwem
  sperren den Proxy – und damit alle.
- **Mit `KK_TRUSTED_PROXIES`** wird der Header nur geglaubt, wenn die Anfrage wirklich vom
  eingetragenen Proxy kommt. Wer am Proxy vorbei direkt auf Port 8000 zugreift und sich im
  Header eine Adresse ausdenkt, wird mit seiner echten Adresse gezählt und gesperrt.
- **`KK_BEHIND_PROXY=1`** (ältere Versionen) glaubt den Header von jedem. Damit ließe sich die
  Sperre am Proxy vorbei umgehen; die Benutzerseite warnt in diesem Fall. Bitte auf
  `KK_TRUSTED_PROXIES` umstellen.

**Mehrere Proxys hintereinander** (z. B. Cloudflare → Nginx Proxy Manager → Klassenkasse):
alle eintragen, auch als Netze, z. B.
`KK_TRUSTED_PROXIES=192.168.1.10, 173.245.48.0/20, 103.21.244.0/22, …` (die Cloudflare-Netze
stehen unter <https://www.cloudflare.com/ips/>). Die Klassenkasse geht `X-Forwarded-For` von
hinten durch und nimmt die erste Adresse, die kein eingetragener Proxy ist.

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
- Ein ungültiger Eintrag in `KK_TRUSTED_PROXIES` verhindert den Start (Meldung in
  `journalctl -u klassenkasse`), damit ein Tippfehler den Schutz nicht still abschaltet.
- Am besten nur den Proxy an den Container lassen, z. B. mit der Proxmox-Firewall
  (eingehend TCP 8000 nur von der IP des Proxys).
