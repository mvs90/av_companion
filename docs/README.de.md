# AV Companion

Die optionale Erweiterung fasst LG, Apple TV oder einen anderen Zuspieler, Sonos/Soundsystem und eine Display-Steckdose in einem gemeinsamen TV-Mediaplayer zusammen. Die eigentlichen Geräteintegrationen bleiben erforderlich.

## Einrichtung

1. [LG Professional Display](https://github.com/mvs90/lg_rs232_ip) ab Version 2.0 installieren und das LG konfigurieren.
2. `https://github.com/mvs90/av_companion` in HACS als benutzerdefiniertes Repository der Kategorie **Integration** hinzufügen, herunterladen und HA neu starten.
3. **AV Companion** hinzufügen und das LG auswählen. Pro LG ist ein AV-System erlaubt.
4. Unter **Konfigurieren** die gewünschten Zusatzgeräte zuordnen. Auch nur „LG + Zuspieler“ oder „LG + Lautstärkegerät“ funktioniert.

AV Companion erscheint unter **Einstellungen → Geräte & Dienste → Integrationen**. Im Reiter **Geräte** steht das gemeinsame AV-System unter dem vergebenen Namen, etwa „Wohnzimmer AV“. Ab Version 1.4.1 wird die Erweiterung als Geräteintegration eingeordnet. Nach dem Update HA neu starten; vorhandene Einträge, Geräte-/Entitätskennungen und Einstellungen bleiben erhalten.

Für Apple TV die vorhandene `remote`-Entität auswählen und den Strommodus **apple_tv** verwenden (`wakeup`/`suspend`). Für Sonos den Lautstärke-Mediaplayer sowie optional Nachtmodus/Sprachverbesserung zuweisen. Lautstärkerouting ist am gekoppelten Eingang, immer oder nur am Display möglich. TV-Eingang des Soundsystems kann beim ausdrücklichen Einschalten gewählt werden.

In HomeKit Bridge **Accessory/Einzelgerät** wählen und nur den gemeinsamen AV-Mediaplayer exportieren. Die Geräteentitäten bleiben für HA intern vorhanden. Eine echte HomeKit-Kopplung am iPhone muss vor Ort erfolgen.

## Standby

Die Erweiterung prüft echten Zuspieler-Standby, anhaltenden LG-Signalverlust (standardmäßig 120 Sekunden), optional den Verbrauch ausschließlich des LG sowie eine Idle-Rückfallebene bei unbekanntem Signal (900 Sekunden). Ein gültiges HDMI-Signal verhindert die Idle-Rückfallebene. Bei falschem Idle und weiterhin gültigem Signal bleibt die Situation mehrdeutig. Netzwerkfehler sind niemals bestätigtes Standby.

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
