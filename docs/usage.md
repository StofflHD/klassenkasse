# Bedienung

## Erste Schritte

1. Als Administrator anmelden.
2. **Schüler** → Namen eintragen (einer pro Zeile, mehrere auf einmal möglich).
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

## Schüler/innen

Die Seite einer Schülerin/eines Schülers zeigt alle Zahlungen und den Stand bei jeder
Sammlung. Wer die Klasse verlässt, wird auf *inaktiv* gesetzt statt gelöscht: bisherige
Buchungen bleiben erhalten, bei Sammlungen ist nichts mehr offen. In Sammlungen, für die
schon gezahlt wurde, bleibt sie/er mit dem Hinweis *inaktiv* stehen.

## Export

- **Buchungen** → *CSV-Export*: CSV mit allen Buchungen inkl. Stornos (für die Kassenprüfung)
- **Sammlung** → *CSV-Export*: CSV mit Soll, bezahlt und offen pro Person

Die Dateien sind für Excel/LibreOffice gemacht: Semikolon als Trenner, UTF-8 mit BOM,
deutsche Beträge. Texte, die mit `=`, `+`, `-` oder `@` beginnen, werden entschärft, damit
sie in der Tabellenkalkulation nicht als Formel laufen.
