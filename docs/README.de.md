# AV Companion

Die optionale Erweiterung fasst LG, Apple TV oder einen anderen Zuspieler, Sonos/Soundsystem und eine Display-Steckdose in einem gemeinsamen TV-Mediaplayer zusammen. Die eigentlichen Geräteintegrationen bleiben erforderlich.

## Einrichtung

1. [LG Professional Display](https://github.com/mvs90/lg_rs232_ip) ab Version 2.0 installieren und das LG konfigurieren.
2. `https://github.com/mvs90/av_companion` in HACS als benutzerdefiniertes Repository der Kategorie **Integration** hinzufügen, herunterladen und HA neu starten.
3. **AV Companion** hinzufügen und das LG auswählen. Pro LG ist ein AV-System erlaubt.
4. Unter **Konfigurieren** die gewünschten Zusatzgeräte zuordnen. Auch nur „LG + Zuspieler“ oder „LG + Lautstärkegerät“ funktioniert.

AV Companion erscheint unter **Einstellungen → Geräte & Dienste → Integrationen**. Im Reiter **Geräte** steht das gemeinsame AV-System unter dem vergebenen Namen, etwa „Wohnzimmer AV“. Ab Version 1.4.1 wird die Erweiterung als Geräteintegration eingeordnet. Nach dem Update HA neu starten; vorhandene Einträge, Geräte-/Entitätskennungen und Einstellungen bleiben erhalten.

Für Apple TV die vorhandene `remote`-Entität auswählen und den Strommodus **apple_tv** verwenden (`wakeup`/`suspend`). Für Sonos den Lautstärke-Mediaplayer sowie optional Nachtmodus/Sprachverbesserung zuweisen. Lautstärkerouting ist am gekoppelten Eingang, immer oder nur am Display möglich. Die optionale TV-Ton-Umschaltung erfolgt ausschließlich bei ausdrücklicher HDMI-Auswahl. Sie ist standardmäßig aus, damit Sonos TV-Autoplay entscheiden kann.

In HomeKit Bridge **Accessory/Einzelgerät** wählen und nur den gemeinsamen AV-Mediaplayer exportieren. Die Geräteentitäten bleiben für HA intern vorhanden. Eine echte HomeKit-Kopplung am iPhone muss vor Ort erfolgen.

## Standby

Auch „aus“ oder „Standby“ des Zuspielers muss durch fehlendes HDMI-Signal bestätigt werden. Ein vorhandenes Signal verhindert die automatische Abschaltung; ein unbekanntes Signal bestätigt keinen Aus-Zustand. Die Erweiterung prüft anhaltenden LG-Signalverlust (standardmäßig 15 Sekunden), optional den Verbrauch ausschließlich des LG sowie eine Idle-Rückfallebene bei unbekanntem Signal (900 Sekunden). Bei dauerhaft falschem „aus“ wird trotzdem nach bestätigtem Signalverlust abgeschaltet, ohne einen neuen Zustandswechsel abzuwarten. Die Signalverlustprüfung und ihre Wartezeit müssen dafür aktiviert sein. Manuelles Ausschalten bleibt jederzeit möglich. Ein gültiges HDMI-Signal verhindert auch die Idle-Rückfallebene. Bei falschem Idle und weiterhin gültigem Signal bleibt die Situation mehrdeutig. Netzwerkfehler sind niemals bestätigtes Standby.

**Alert Status** warnt nach mindestens zwei Prüfungen über 120 Sekunden, wenn der Zuspieler „aus/Standby“ meldet, aber HDMI-Signal anliegt. Diese Prüfung arbeitet auch bei gesperrter Automatik. Der Code `linked_power_state_conflict` und das gleichnamige Attribut am AV-Player sind für Automationen verfügbar. Die Meldung benennt einen bestätigten Statuswiderspruch; auch ein aktiver HDMI-Extractor kann ein Signal aufrechterhalten. Sie verschwindet, sobald der Widerspruch nicht mehr bestätigt werden kann, und erzeugt keine wiederholten Meldungen bei unverändertem Zustand.

Die Steckdose wird erst nach einer frischen Aus-Bestätigung des LG abgeschaltet. Ein neuer Einschaltbefehl beendet geplante Abschaltung. Wartende/laufende native LG-Inhalte sperren die Standby-Automatik und verbergen Apple-TV-Metadaten. Die Diagnoseattribute erklären den jeweiligen Kandidaten und die letzte Abschaltentscheidung.

**FeinTech AX310 bleibt dauerhaft versorgt. Nur das LG-Display hängt an der schaltbaren Steckdose.** Native LG-Inhalte geben über diese Verkabelung ihren Ton nicht automatisch an Sonos zurück.

## Inhalte und Zusatzfunktionen

- `av_companion.show_content`: temporäre Medien auf dem externen Inhaltsplayer.
- `av_companion.show_display_content`: native Bilder/Videos/Streams/Webseiten auf dem LG; darf als ausdrücklicher Wiedergabebefehl auch die Stromversorgung herstellen.
- `av_companion.show_notification`: eigenes Anzeige-Skript mit Sitzungskennung.
- `av_companion.clear_content`: Warteschlangen beenden und aufräumen.
- `av_companion.send_remote_command`: Fernbedienung passend zum Eingang.
- `av_companion.set_sound_mode`: Sonos-Nachtmodus/Sprachverbesserung.
- `av_companion.announce`: Durchsage über ein unterstütztes Soundsystem.

Für native Textüberblendungen `lg_rs232_ip.show_toast` am LG-Mediaplayer verwenden. Passwort, Zertifikat, OSD, Bootlogo und Vorschau werden ausschließlich in der LG-Integration eingerichtet.

[Ausführliche Aktionsbeispiele](FEATURES.md) · [Standby-Regeln](STANDBY.md) · [Prüfbericht](TESTING.md).

### Studio-Quellen ab AV Companion 1.4 / LG 2.14

Dashboard, Dashboard PiP, Mediaplayer und alle zusätzlich gespeicherten Studio-Ansichten erscheinen automatisch als Quellen am kombinierten Player. Namen folgen Änderungen im Studio; die interne Kennung bleibt gleich. Wird die aktive eigene Ansicht gelöscht, folgt Dashboard. Der vorhandene Standby-Schutz gilt auch für eigene Ansichten. Ältere LG-Versionen bleiben unterstützt.

### HDMI in der App und PiP bei Signalverlust

Ab LG Professional Display **2.33.0** wird im App-Vollbild das eingebettete HDMI-Bild geprüft. Die aktive SI-App selbst zählt nicht als vorhandenes HDMI-Signal. Auch bei einem dauerhaft fälschlich ausgeschalteten Apple TV kann das Display nach bestätigtem Signalverlust abschalten.

Unter **AV Companion → Konfigurieren** gibt es für dauerhafte PiP-Ansichten eine eigene Regel: **Ansicht beibehalten** (Standard), **Ansicht ohne HDMI anzeigen** oder **Display ausschalten**. Wartezeit und Zielansicht sind einstellbar; Standard 15 Sekunden, 0 deaktiviert die Aktion. Die Auswahl umfasst gespeicherte Ansichten ohne HDMI-Element. Der Wechsel bleibt innerhalb der App und verwendet die vorhandene OSD-Unterdrückung. Automationssperre, Start-/Quellenwechsel und unbekanntes Signal verhindern die Aktion; temporäre Mitteilungen und zeitlich begrenzte Ansichten bleiben geschützt.

Der Text der Countdown-Meldung ist ebenfalls in den AV-Optionen bearbeitbar. `{seconds}` zeigt die Restzeit, `{action}` benennt Ausschalten oder Ansichtswechsel. Die Meldung lässt sich auch ausblenden. Der Countdown läuft lokal auf dem Display, ohne sekündliche Netzwerkabfragen.

## Sonos und PiP Sonos (1.6)

Der separate Lautstärke-Mediaplayer wird auch als Wiedergabequelle berücksichtigt. **Sonos** öffnet die Mediaplayer-Ansicht, **PiP Sonos** standardmäßig die bearbeitbare Dashboard-PiP-Ansicht; über **Ansicht für PiP Sonos** kann eine eigene gespeicherte Ansicht zugeordnet werden. Die Auswahl startet keine Playlist und unterbricht keine bestehende Wiedergabe. Titel, Cover, Fortschritt und Transportsteuerung folgen Sonos-Musik – auch bei HDMI-Anzeige. Eine Pause bleibt für das Fortsetzen an Sonos gebunden. Bei Sonos-TV-Ton stammen diese Daten wieder vom Apple TV; fehlende Cover können nicht erzeugt werden.

Für diese automatische Auswahl in Widgets und Cover-Hintergründen die **kombinierte AV-Entität** im Display Studio auswählen. Vorhandene Layouts bleiben beim Update erhalten. Eine eigene PiP-Sonos-Ansicht kann HDMI und Medienkarte getrennt anordnen. Wird die zugeordnete Ansicht gelöscht, greift wieder Dashboard PiP.

Unter **AV Companion → Konfigurieren → Sonos bei HDMI-Auswahl auf TV-Ton umschalten** lässt sich die TV-Umschaltung abschalten. Aus ist der Standard: Sonos verwendet seine eigene TV-Autoplay-Einstellung. Auch bei eingeschalteter Option ändern Einschalten, App-Auswahl, Sonos, Dashboard, Mediaplayer und PiP die Audioquelle nicht.

Meldungen nennen den konkreten Player, z. B. „Wohnzimmer Apple TV“. Im Countdown-Text steht dafür `{player}` zur Verfügung; `{seconds}` und `{action}` bleiben erhalten. Eine vorhandene Standardmeldung wird automatisch angepasst, eigene Texte bleiben erhalten.

## Projekt unterstützen

Wenn dir dieses Projekt hilft, kannst du seine Weiterentwicklung und Pflege
freiwillig über [PayPal](https://www.paypal.me/mvs90) unterstützen.
Vielen Dank für deine Unterstützung!
