import asyncio, os
import aiohttp
from lab_scope import lab_entry

BASE = os.environ.get("HA_URL", "http://127.0.0.1:8123")


async def main():
    token = os.environ["HA_TOKEN"]
    async with aiohttp.ClientSession(headers={"Authorization": "Bearer " + token}) as s:

        async def req(method, path, data=None):
            async with s.request(method, BASE + path, json=data) as r:
                if r.status >= 400:
                    raise RuntimeError(
                        f"{method} {path}: {r.status} {(await r.text())[:500]}"
                    )
                return await r.json()

        async def service(domain, name, entity, **data):
            return await req(
                "POST", f"/api/services/{domain}/{name}", {"entity_id": entity, **data}
            )

        async def state(entity):
            return await req("GET", "/api/states/" + entity)

        entries = await req("GET", "/api/config/config_entries/entry")
        lab_entry(entries, "lg_rs232_ip")
        lab_entry(entries, "av_companion", required=False)
        if not any(e["domain"] == "av_test_lab" for e in entries):
            result = await req(
                "POST", "/api/config/config_entries/flow", {"handler": "av_test_lab"}
            )
            print("fixture flow", result.get("type"), result.get("errors"), flush=True)
        await service("media_player", "turn_on", "media_player.av_test_source")
        entries = await req("GET", "/api/config/config_entries/entry")
        av = lab_entry(entries, "av_companion", required=False)
        if av is None:
            flow = await req(
                "POST", "/api/config/config_entries/flow", {"handler": "av_companion"}
            )
            assert flow["type"] == "form", flow
            result = await req(
                "POST",
                "/api/config/config_entries/flow/" + flow["flow_id"],
                {
                    "display_entity_id": "media_player.lg_split_test_display",
                    "name": "AV Split Test",
                },
            )
            print("AV flow", result.get("type"), result.get("errors"), flush=True)
            assert result["type"] == "create_entry", result
            av = result["result"]
        flow = await req(
            "POST",
            "/api/config/config_entries/options/flow",
            {"handler": av["entry_id"]},
        )
        result = await req(
            "POST",
            "/api/config/config_entries/options/flow/" + flow["flow_id"],
            {
                "polling_interval": 5,
                "linked_media_player_entity_id": "media_player.av_test_source",
                "linked_volume_media_player_entity_id": "media_player.av_test_sound",
                "power_supply_switch_entity_id": "switch.av_test_socket",
                "sonos_night_sound_entity_id": "switch.av_test_night",
                "sonos_speech_enhancement_entity_id": "switch.av_test_speech",
                "power_supply_off_delay_seconds": 2,
                "standby_no_signal_seconds": 30,
                "standby_idle_seconds": 30,
                "media_player_pending_power_seconds": 0,
                "media_player_pending_source_seconds": 0,
                "linked_volume_sync_mode": "always",
                "sonos_select_tv_source": True,
            },
        )
        assert result["type"] == "create_entry", result
        print("AV options saved", flush=True)
        await asyncio.sleep(3)
        for entity in [
            "media_player.lg_split_test_display",
            "media_player.av_split_test_av_system",
        ]:
            value = await state(entity)
            print(entity, value["state"], value["attributes"], flush=True)


asyncio.run(main())
