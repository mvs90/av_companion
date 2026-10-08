import asyncio, json, time, os
from pathlib import Path
import aiohttp
from lab_scope import lab_entry

BASE = os.environ.get("HA_URL", "http://127.0.0.1:8123")
LG = "media_player.lg_split_test_display"
AV = "media_player.av_split_test_av_system"
SOURCE = "media_player.av_test_source"
SOUND = "media_player.av_test_sound"
SOCKET = "switch.av_test_socket"


async def main():
    token = os.environ["HA_TOKEN"]
    checks = (
        json.loads(Path("dev/results.json").read_text())["checks"]
        if os.environ.get("SKIP_STANDBY")
        else []
    )
    async with aiohttp.ClientSession(headers={"Authorization": "Bearer " + token}) as s:

        async def req(method, path, data=None):
            async with s.request(method, BASE + path, json=data) as r:
                body = await r.text()
                if r.status >= 400:
                    raise RuntimeError(f"{method} {path}: {r.status} {body[:300]}")
                return json.loads(body)

        async def svc(domain, name, entity, **data):
            return await req(
                "POST", f"/api/services/{domain}/{name}", {"entity_id": entity, **data}
            )

        async def state(entity):
            return await req("GET", "/api/states/" + entity)

        async def sim(**data):
            async with s.post("http://127.0.0.1:18762/state", json=data) as r:
                return await r.json()

        async def expect(entity, wanted, timeout=15):
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                value = await state(entity)
                if value["state"] == wanted:
                    return value
                await asyncio.sleep(1)
            raise AssertionError(f"{entity}: expected {wanted}, got {value['state']}")

        def passed(text):
            checks.append(text)
            print("PASS", text, flush=True)
            Path("dev/results.json").write_text(
                json.dumps({"ha_version": "2026.9.4", "checks": checks}, indent=2)
            )

        async def update():
            await svc("homeassistant", "update_entity", AV)
            await svc("homeassistant", "update_entity", LG)

        async with s.ws_connect(BASE + "/api/websocket") as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            assert (await ws.receive_json())["type"] == "auth_ok"

            async def wsreq(kind, **data):
                async with s.ws_connect(BASE + "/api/websocket") as channel:
                    await channel.receive_json()
                    await channel.send_json({"type": "auth", "access_token": token})
                    assert (await channel.receive_json())["type"] == "auth_ok"
                    await channel.send_json({"id": 1, "type": kind, **data})
                    result = await channel.receive_json()
                    assert result["success"], result
                    return result.get("result")

            entries = await req("GET", "/api/config/config_entries/entry")
            lab_entry(entries, "lg_rs232_ip")
            lab_entry(entries, "av_companion")

            if not os.environ.get("SKIP_STANDBY"):
                await sim(power=True, input=144, signal=True)
                await svc("switch", "turn_on", SOCKET)
                await svc("media_player", "turn_on", SOUND)
                await svc("media_player", "turn_on", AV)
                await asyncio.sleep(3)
                await update()
                assert (await state(LG))["state"] == "on"
                assert (await state(AV))["state"] == "idle"
                passed("LG and AV configured and running independently")
                await svc("media_player", "volume_set", AV, volume_level=0.42)
                assert (await state(SOUND))["attributes"]["volume_level"] == 0.42
                assert (await sim())["volume"] == 20
                await svc("media_player", "volume_mute", AV, is_volume_muted=True)
                assert (await state(SOUND))["attributes"]["is_volume_muted"] is True
                await svc(
                    "av_companion", "set_sound_mode", AV, mode="night", enabled=False
                )
                await expect("switch.av_test_night", "off")
                passed(
                    "Sound volume, mute and night mode routed without changing LG volume"
                )
                await svc("media_player", "media_play", AV)
                await expect(SOURCE, "playing")
                await svc("media_player", "media_pause", AV)
                await expect(SOURCE, "paused")
                await svc("media_player", "media_stop", AV)
                await expect(SOURCE, "idle")
                passed("Playback commands reach source through real HA services")
                await req(
                    "POST",
                    "/api/events/homekit_tv_remote_key_pressed",
                    {"entity_id": LG, "key_name": "arrow_up"},
                )
                await asyncio.sleep(1)
                assert any("mc 01 40" == c for c in (await sim())["commands"])
                passed("HomeKit remote event routes to targeted LG")
                flow = await req(
                    "POST",
                    "/api/config/config_entries/flow",
                    {"handler": "av_companion"},
                )
                result = await req(
                    "POST",
                    "/api/config/config_entries/flow/" + flow["flow_id"],
                    {"display_entity_id": LG, "name": "Duplicate"},
                )
                assert (
                    result["type"] == "abort"
                    and result["reason"] == "already_configured"
                ), result
                passed("Second AV owner for the same display rejected")
                await asyncio.sleep(35)
                await update()
                assert (await sim())["power"]
                passed("Idle with valid HDMI signal remains on beyond idle timeout")
                await sim(signal=False)
                await expect(SOCKET, "off", 55)
                assert not (await sim())["power"]
                await expect(AV, "off")
                passed(
                    "False Apple TV idle plus sustained signal loss shuts down LG before socket"
                )
                await svc("media_player", "turn_on", SOURCE)
                await asyncio.sleep(6)
                await expect(SOCKET, "off", 2)
                passed("Stale idle does not wake display after confirmed shutdown")
                await sim(signal=True)
                await svc("media_player", "turn_on", AV)
                await expect(SOCKET, "on")
                await asyncio.sleep(4)
                await update()
                assert (await sim())["power"]
                passed("Explicit AV wake restores socket, LG and source")
                await svc("media_player", "select_source", AV, source="HDMI 2")
                assert (await sim())["input"] == 145
                await sim(signal=False)
                await asyncio.sleep(35)
                await update()
                assert (await sim())["power"]
                passed("Standby guard does not shut down a different physical input")
                await sim(signal=True)
                await svc("media_player", "select_source", AV, source="HDMI 1")
            entries = await req("GET", "/api/config/config_entries/entry")
            lg = lab_entry(entries, "lg_rs232_ip")
            av = lab_entry(entries, "av_companion")
            await wsreq(
                "config_entries/disable", entry_id=lg["entry_id"], disabled_by="user"
            )
            await expect(AV, "unavailable")
            assert (await state(SOCKET))["state"] == "on"
            await wsreq(
                "config_entries/disable", entry_id=lg["entry_id"], disabled_by=None
            )
            await expect(LG, "on", 30)
            await update()
            assert (await state(AV))["state"] != "unavailable"
            passed(
                "LG unload makes AV unavailable without cutting supply; reload reconnects"
            )
            await svc("media_player", "turn_off", AV)
            await expect(SOCKET, "off")
            await wsreq(
                "config_entries/disable", entry_id=av["entry_id"], disabled_by="user"
            )
            await svc("media_player", "turn_on", LG)
            assert (await sim())["power"]
            passed("AV unload releases supply hint and standalone LG remains operable")
            await svc("switch", "turn_on", SOCKET)
            await wsreq(
                "config_entries/disable", entry_id=av["entry_id"], disabled_by=None
            )
            await asyncio.sleep(3)
            await wsreq(
                "config/entity_registry/update",
                entity_id=SOURCE,
                new_entity_id="media_player.av_test_source_renamed",
            )
            await asyncio.sleep(3)
            await svc("media_player", "media_play", AV)
            await expect("media_player.av_test_source_renamed", "playing")
            await wsreq(
                "config/entity_registry/update",
                entity_id="media_player.av_test_source_renamed",
                new_entity_id=SOURCE,
            )
            await asyncio.sleep(3)
            passed(
                "Renamed optional player is tracked by options and continues playback"
            )
            entries = await req("GET", "/api/config/config_entries/entry")
            assert (
                next(e for e in entries if e["domain"] == "unifi_air_quality")["state"]
                == "loaded"
            )
            passed("Existing UniFi integration preserved and loaded")
        Path("dev/results.json").write_text(
            json.dumps(
                {
                    "ha_version": (await req("GET", "/api/config"))["version"],
                    "checks": checks,
                },
                indent=2,
            )
        )


asyncio.run(main())
