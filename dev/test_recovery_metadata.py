"""Focused real HA/TCP acceptance; ONLY reserved simulator/fixture entities."""

import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import time

import aiohttp
from PIL import Image
from lab_scope import lab_entry

BASE = os.environ.get("HA_URL", "http://127.0.0.1:8123")
AV = "media_player.av_split_test_av_system"
LG = "media_player.lg_split_test_display"
SOURCE = "media_player.av_test_source"


async def main():
    results = []
    async with aiohttp.ClientSession(
        headers={"Authorization": "Bearer " + os.environ["HA_TOKEN"]}
    ) as session:

        async def req(method, path, data=None):
            async with session.request(method, BASE + path, json=data) as response:
                response.raise_for_status()
                return await response.json()

        async def service(domain, name, entity, **data):
            return await req(
                "POST", f"/api/services/{domain}/{name}", {"entity_id": entity, **data}
            )

        async def state(entity=AV):
            return await req("GET", "/api/states/" + entity)

        async def sim(**data):
            async with session.post(
                "http://127.0.0.1:18762/state", json=data
            ) as response:
                response.raise_for_status()
                return await response.json()

        async def source(value, **data):
            return await service(
                "av_test_lab", "set_playback", SOURCE, state=value, **data
            )

        async def wait(test, label, seconds=35):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                if await test():
                    return
                await asyncio.sleep(0.25)
            raise AssertionError(label)

        async def power(wanted):
            return bool((await sim())["power"]) is wanted

        def passed(label):
            print("PASS", label, flush=True)
            results.append(label)
            Path("dev/recovery-results.json").write_text(json.dumps(results, indent=2))

        async def image():
            url = (await state())["attributes"]["entity_picture"]
            async with session.get(BASE + url) as response:
                response.raise_for_status()
                raw = await response.read()
                opened = Image.open(BytesIO(raw))
                opened.load()
                return opened.size, raw

        entries = await req("GET", "/api/config/config_entries/entry")
        lab_entry(entries, "lg_rs232_ip")
        av = lab_entry(entries, "av_companion")
        flow = await req(
            "POST",
            "/api/config/config_entries/options/flow",
            {"handler": av["entry_id"]},
        )
        # Reserved lab options only; no access to the real AV entry or devices.
        options = {
            "polling_interval": 5,
            "linked_media_player_entity_id": SOURCE,
            "linked_volume_media_player_entity_id": "media_player.av_test_sound",
            "power_supply_switch_entity_id": "switch.av_test_socket",
            "standby_no_signal_seconds": 15,
            "power_supply_off_delay_seconds": 2,
            "media_player_pending_power_seconds": 12,
            "linked_volume_sync_mode": "always",
        }
        result = await req(
            "POST",
            "/api/config/config_entries/options/flow/" + flow["flow_id"],
            options,
        )
        assert result["type"] == "create_entry", result.get("errors")
        await asyncio.sleep(2)
        await sim(power=True, signal=True, input=144, off_delay=0)
        await service("switch", "turn_on", "switch.av_test_socket")
        await service("media_player", "turn_on", AV)
        await source("playing", app_name="Netflix", app_id="com.netflix.Netflix")
        await asyncio.sleep(2)
        value = await state()
        assert value["attributes"]["media_title"] == "Netflix", value
        assert value["attributes"]["media_artist"] in ["Wiedergabe", "Playing"]
        size, raw = await image()
        assert size == (256, 256), size
        # Netflix's real red icon is distinguishable from the neutral offline badge.
        assert any(
            r > 180 and g < 70 and b < 90
            for r, g, b in Image.open(BytesIO(raw)).convert("RGB").getdata()
        )
        Path("dev/netflix-fallback.png").write_bytes(raw)
        passed(
            "Netflix name, reported playback state and actual App Store icon through HA artwork proxy"
        )
        await source(
            "paused",
            app_name="Netflix",
            app_id="com.netflix.Netflix",
            title="Real title",
            cover=True,
        )
        value = await state()
        assert value["attributes"]["media_title"] == "Real title"
        assert value["attributes"].get("media_artist") is None
        size, _ = await image()
        assert size == (1, 1)
        passed(
            "Real title and real artwork immediately replace app fallback; no reload"
        )
        await source("idle", app_name="Netflix", app_id="com.netflix.Netflix")
        assert (await state())["attributes"]["media_artist"] in ["Idle", "Leerlauf"]
        passed("Idle is displayed honestly, not inferred as paused/playing")
        await asyncio.sleep(16)  # Real startup guard, not a patched clock.
        before = (await state(SOURCE))["attributes"]["turn_off_calls"]
        await source("off")
        await sim(signal=False)
        await service("homeassistant", "update_entity", LG)
        await service("homeassistant", "update_entity", AV)
        started = time.monotonic()
        await wait(lambda: power(False), "no-signal off")
        assert time.monotonic() - started >= 14
        assert (await state(SOURCE))["attributes"]["turn_off_calls"] == before
        passed(
            "15-second confirmed signal loss turns off simulated display without suspending rebooting source"
        )
        await asyncio.sleep(3)  # Include supply-off and pending-power suppression.
        await source("unknown")
        await sim(signal=True)
        await source("idle")
        await wait(lambda: power(True), "reconnect wake")
        await asyncio.sleep(2)
        assert (await state())["state"] == "idle"
        assert (await state(SOURCE))["attributes"]["turn_off_calls"] == before
        passed(
            "off -> unknown -> idle reconnect restores socket/display during off suppression"
        )
        # Active transition while the serial OFF acknowledgement is still pending.
        await asyncio.sleep(15)
        await source("off")
        await sim(signal=False, off_delay=2, clear_commands=True)
        await service("homeassistant", "update_entity", LG)
        await service("homeassistant", "update_entity", AV)

        async def off_started():
            return any(
                command.startswith("ka ") and command.endswith(" 00")
                for command in (await sim())["commands"]
            )

        await wait(off_started, "slow off command")
        await sim(signal=True)
        await source("playing")
        await asyncio.sleep(5)
        assert await power(True)
        assert (await state(SOURCE))["attributes"]["turn_off_calls"] == before
        passed(
            "Playing event during slow serial off is retained and executed after OFF completes"
        )
        await sim(off_delay=0)
        await service("media_player", "turn_off", AV)
        count = (await state(SOURCE))["attributes"]["turn_off_calls"]
        assert count == before + 1
        await source("unknown")
        await source("idle")
        await asyncio.sleep(4)
        assert await power(False)
        passed(
            "Explicit user shutdown still suspends player and rejects reconnect echo"
        )
        print(f"{len(results)} acceptance checks passed", flush=True)


asyncio.run(main())
