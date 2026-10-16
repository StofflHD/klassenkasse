# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 StofflHD
"""Echte Client-Adresse hinter vertrauenswürdigen Reverse-Proxys (KK_TRUSTED_PROXIES).

X-Forwarded-* wird nur ausgewertet, wenn die Anfrage von einem eingetragenen Proxy kommt.
Wer am Proxy vorbei direkt zugreift, kann sich so keine fremde Adresse ausdenken – seine
Anfragen zählen für seine echte Absenderadresse (wichtig für die IP-Sperre).
"""
import ipaddress


def parse_trusted(text):
    """'10.0.0.2, 172.16.0.0/12' -> Liste von Netzen; ungültige Einträge sind ein Fehler."""
    nets = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            raise ValueError(f"KK_TRUSTED_PROXIES: ungültige Adresse oder ungültiges Netz: {part}")
    return nets


def _last(value):
    parts = [p.strip() for p in (value or "").split(",") if p.strip()]
    return parts[-1] if parts else ""


class TrustedProxyFix:
    def __init__(self, wsgi_app, nets):
        self.wsgi_app = wsgi_app
        self.nets = nets

    def trusted(self, ip):
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in net for net in self.nets)

    def client_ip(self, remote, forwarded_for):
        """Von rechts nach links durch X-Forwarded-For, solange die Adressen eigene Proxys sind.

        Jeder Proxy hängt die Adresse an, von der er die Anfrage bekommen hat. Die erste
        Adresse von rechts, die kein eingetragener Proxy ist, ist der Besucher – alles weiter
        links hat der Besucher womöglich selbst geschickt.
        """
        chain = [p.strip() for p in (forwarded_for or "").split(",") if p.strip()]
        client = remote
        while chain and self.trusted(client):
            candidate = chain.pop()
            try:
                client = str(ipaddress.ip_address(candidate))
            except ValueError:
                break  # kaputter Eintrag: beim letzten Proxy stehen bleiben
        return client

    def __call__(self, environ, start_response):
        remote = environ.get("REMOTE_ADDR", "")
        if self.trusted(remote):
            environ["kk.proxy_addr"] = remote
            environ["REMOTE_ADDR"] = self.client_ip(remote, environ.get("HTTP_X_FORWARDED_FOR"))
            proto = _last(environ.get("HTTP_X_FORWARDED_PROTO")).lower()
            if proto in ("http", "https"):
                environ["wsgi.url_scheme"] = proto
            host = _last(environ.get("HTTP_X_FORWARDED_HOST"))
            if host:
                environ["HTTP_HOST"] = host
        return self.wsgi_app(environ, start_response)
