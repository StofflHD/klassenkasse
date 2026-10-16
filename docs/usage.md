# Bedienung

## Erste Schritte

1. Als Administrator anmelden.
2. **Klassenliste** → Schüler/innen eintragen: einzeln mit Kontaktdaten, mehrere Namen auf
   einmal (einer pro Zeile) oder eine vorhandene Liste aus Excel/CSV importieren.
3. **Benutzer** → Konten für Kassenwart/in und Elternvertretung anlegen.
4. **Sammlungen** → erste Sammlung anlegen, z. B. „Ausflug Zoo“, 12 €, Fälligkeitsdatum.

## Rollen

| Rolle | Darf |
|---|---|
| Nur lesen | alles ansehen und exportieren – für Elternvertretung und Kassenprüfung |
| Kassenwart | zusätzlich buchen, stornieren, Sammlungen und Schüler/innen pflegen |
| Administrator | zusätzlich Benutzer anlegen, Rollen ändern, Passwörter setzen, Konten löschen |

Das eigene Konto kann ein Administrator in der Oberfläche weder löschen noch herabstufen.
Sein Passwort ändert jede/r per Klick auf den eigenen Benutzernamen oben rechts.

## Anmeldung und Sperrliste

Nach **3 fehlgeschlagenen Anmeldungen** innerhalb von 24 Stunden wird die IP-Adresse
gesperrt. Vorher zeigt die Anmeldeseite, wie viele Versuche noch bleiben. Eine gesperrte
Adresse erreicht die Klassenkasse gar nicht mehr – auch nicht mit dem richtigen Passwort –,
bis ein Administrator sie freigibt. Eine erfolgreiche Anmeldung setzt den Zähler zurück.

Administratoren sehen unter **Benutzer → Gesperrte IP-Adressen**:

- die gesperrten Adressen mit Zeitpunkt, Grund und *entsperren*,
- *IP-Adresse oder Netz von Hand sperren*, z. B. `203.0.113.7` oder `203.0.113.0/24`
  (die eigene Adresse lässt sich so nicht sperren),
- die letzten Fehlversuche je IP-Adresse mit den versuchten Benutzernamen; *zurücksetzen*
  löscht den Zähler.

Hat sich der einzige Administrator selbst ausgesperrt, hilft im Container:

```bash
klassenkasse-admin blocklist           # Sperren anzeigen
klassenkasse-admin unblock 192.0.2.10  # eine Adresse freigeben
klassenkasse-admin unblock --all       # alle Sperren und Fehlversuche löschen
```

Die Zahl der erlaubten Fehlversuche lässt sich mit `KK_MAX_LOGIN_FAILURES` ändern
([Konfiguration](configuration.md)). Hinter einem Reverse-Proxy unbedingt
`KK_TRUSTED_PROXIES` mit der Adresse des Proxys setzen – sonst sieht die App nur den Proxy
und sperrt im Zweifel alle ([Reverse-Proxy](reverse-proxy.md)).

## Buchungen

Eine Buchung hat Datum, Art (Einnahme/Ausgabe), Betrag, Zweck und optional eine
Schülerin/einen Schüler und eine Sammlung. Beträge gehen mit Komma oder Punkt
(`12,50`, `1.234,56 €`), höchstens zwei Nachkommastellen.

Wird eine Sammlung gewählt und der Zweck leer gelassen, wird der Titel der Sammlung als Zweck
übernommen.

### Storno statt Löschen

Buchungen lassen sich **nicht ändern oder löschen**. Eine falsche Buchung wird storniert
(mit Grund) und bei Bedarf richtig neu gebucht. Stornierte Buchungen zählen nicht mehr zum
Kassenstand, bleiben aber sichtbar („Stornos anzeigen“) und im Export – mit Zeit,
Benutzer und Grund. Ein Storno kann nicht rückgängig gemacht werden. Das erzwingt die
Datenbank selbst, nicht nur die Oberfläche.

## Sammlungen

Eine Sammlung hat einen Betrag pro Kopf. Die Detailseite zeigt für jede aktive Schülerin und
jeden aktiven Schüler, was bezahlt und was offen ist; eine Zahlung ist dort mit einem Klick
gebucht, Teilzahlungen sind möglich. Abgeschlossene Sammlungen nehmen keine Zahlungen mehr
an und zählen nicht mehr bei den offenen Beträgen; sie lassen sich wieder öffnen.

## Klassenliste

Die Klassenliste zeigt alle Schüler/innen als Tabelle: Name (mit Notiz), Anschrift, je eine
Spalte für Erziehungsberechtigte/r 1 und 2 und den offenen Betrag aus allen offenen
Sammlungen.

Jede/r Erziehungsberechtigte hat eigene Felder: Name, Telefon, E-Mail und eine Anschrift,
falls sie von der des Kindes abweicht (z. B. bei getrennt lebenden Eltern).
Unterschiedliche Nachnamen sind so kein Problem. Telefonnummern und E-Mail-Adressen sind anklickbar (Anrufen bzw. Mail
schreiben). Das Suchfeld filtert beim Tippen über alle Spalten, *CSV-Export* liefert die
ganze Liste.

Kontaktdaten ändern Kassenwart/in und Administrator über *Bearbeiten* (in der Tabelle oder
auf der Seite der Schülerin/des Schülers). Alle Felder außer dem Namen des Kindes sind
optional. Ins Telefonfeld gehört eine Nummer – Festnetz oder mobil; wer doch zwei braucht,
trennt sie mit `/`. Bei E-Mail sind mehrere Adressen mit Komma getrennt möglich.

Die Klassenliste sehen alle Konten, auch *Nur lesen*. Für Konten, die nur die Kasse prüfen
sollen, das berücksichtigen.

### Import aus Excel oder CSV

*Klassenliste → Aus Excel oder CSV importieren* (Kassenwart/in und Administrator) liest eine
`.xlsx`- oder `.csv`-Datei (höchstens 5 MB). Die erste Zeile enthält die Überschriften.
Erkannt werden:

| Feld | Überschriften (Groß-/Kleinschreibung egal) |
|---|---|
| Name | Name, Schüler/in, Kind – oder getrennt Vorname und Nachname |
| Anschrift | Straße, PLZ, Ort (auch Postleitzahl, Wohnort) |
| Erziehungsberechtigte/r 1 / 2 | wie im Export, z. B. „Erziehungsb. 1: Name“, „Erziehungsb. 2: Telefon“; Telefon, E-Mail ohne Nummer gehören zu 1 |
| Notiz | Notiz, Bemerkung, Hinweis |
| Status | aktiv / inaktiv |

Andere Spalten werden ignoriert und in der Vorschau genannt. Am einfachsten: die
Klassenliste als Excel exportieren, ergänzen und wieder importieren.

Vor dem Übernehmen zeigt eine **Vorschau** jede Zeile mit ihrer Zeilennummer in der Datei:
*neu*, *ändern* (mit den geänderten Feldern), *gleich* oder *fehler* (z. B. ungültige
E-Mail-Adresse, ungültiges Datum, Name doppelt in der Datei). Erst *Übernehmen* speichert;
Zeilen mit Fehlern werden übersprungen.

Vorhandene Schüler/innen werden **am Namen** erkannt (Groß-/Kleinschreibung egal) und
aktualisiert. Dabei überschreiben nur **gefüllte Zellen** – leere Zellen lassen vorhandene
Daten stehen. Einen Wert löschen geht über *Bearbeiten*. Wer umbenannt wurde, kommt beim
Import als neuer Eintrag dazu.

## Schüler/innen

Die Seite einer Schülerin/eines Schülers zeigt die Kontaktdaten, alle Zahlungen und den Stand bei jeder
Sammlung. Wer die Klasse verlässt, wird auf *inaktiv* gesetzt statt gelöscht: bisherige
Buchungen bleiben erhalten, bei Sammlungen ist nichts mehr offen. In Sammlungen, für die
schon gezahlt wurde, bleibt sie/er mit dem Hinweis *inaktiv* stehen.

## Export

Jede Liste gibt es als **Excel** (.xlsx) und als **CSV**:

- **Buchungen**: alle Buchungen inkl. Stornos (für die Kassenprüfung)
- **Sammlung**: Soll, bezahlt und offen pro Person
- **Klassenliste**: alle Schüler/innen mit Kontaktdaten und Status

In der Excel-Datei sind Beträge echte Zahlen (zum Summieren) und Datumsangaben echte Daten;
die Kopfzeile ist fixiert und hat einen Filter. Die CSV-Datei hat Semikolon als Trenner,
UTF-8 mit BOM und deutsche Beträge. In beiden laufen Texte, die mit `=`, `+`, `-` oder `@`
beginnen, nie als Formel.
