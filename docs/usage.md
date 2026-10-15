# Bedienung

## Erste Schritte

1. Als Administrator anmelden.
2. **Klassenliste** → Schüler/innen eintragen: einzeln mit Kontaktdaten oder mehrere Namen
   auf einmal (einer pro Zeile) und die Kontaktdaten danach ergänzen.
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

## Klassenliste

Die Klassenliste zeigt alle Schüler/innen als Tabelle: Name (mit Notiz), Geburtstag,
Anschrift, je eine Spalte für Erziehungsberechtigte/r 1 und 2 und den offenen Betrag aus
allen offenen Sammlungen.

Jede/r Erziehungsberechtigte hat eigene Felder: Name, Telefon, E-Mail und eine Anschrift,
falls sie von der des Kindes abweicht (z. B. bei getrennt lebenden Eltern).
Unterschiedliche Nachnamen sind so kein Problem. Telefonnummern und E-Mail-Adressen sind anklickbar (Anrufen bzw. Mail
schreiben). Das Suchfeld filtert beim Tippen über alle Spalten, *CSV-Export* liefert die
ganze Liste für Excel/LibreOffice.

Kontaktdaten ändern Kassenwart/in und Administrator über *Bearbeiten* (in der Tabelle oder
auf der Seite der Schülerin/des Schülers). Alle Felder außer dem Namen des Kindes sind
optional. Ins Telefonfeld gehört eine Nummer – Festnetz oder mobil; wer doch zwei braucht,
trennt sie mit `/`. Bei E-Mail sind mehrere Adressen mit Komma getrennt möglich.

Die Klassenliste sehen alle Konten, auch *Nur lesen*. Für Konten, die nur die Kasse prüfen
sollen, das berücksichtigen.

## Schüler/innen

Die Seite einer Schülerin/eines Schülers zeigt die Kontaktdaten, alle Zahlungen und den Stand bei jeder
Sammlung. Wer die Klasse verlässt, wird auf *inaktiv* gesetzt statt gelöscht: bisherige
Buchungen bleiben erhalten, bei Sammlungen ist nichts mehr offen. In Sammlungen, für die
schon gezahlt wurde, bleibt sie/er mit dem Hinweis *inaktiv* stehen.

## Export

- **Buchungen** → *CSV-Export*: CSV mit allen Buchungen inkl. Stornos (für die Kassenprüfung)
- **Sammlung** → *CSV-Export*: CSV mit Soll, bezahlt und offen pro Person
- **Klassenliste** → *CSV-Export*: alle Schüler/innen mit Kontaktdaten und Status

Die Dateien sind für Excel/LibreOffice gemacht: Semikolon als Trenner, UTF-8 mit BOM,
deutsche Beträge. Texte, die mit `=`, `+`, `-` oder `@` beginnen, werden entschärft, damit
sie in der Tabellenkalkulation nicht als Formel laufen.
