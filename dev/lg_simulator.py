import asyncio
from aiohttp import web

state = {
    "power": True,
    "input": 144,
    "signal": True,
    "volume": 20,
    "mute": 1,
    "commands": [],
}


async def handle(reader, writer):
    try:
        while True:
            raw = (await reader.readuntil(b"\r")).decode().strip()
            parts = raw.split()
            if len(parts) < 3:
                continue
            if len(parts[0]) == 1:
                parts = [parts[0] + parts[1], *parts[2:]]
            cmd = parts[0]
            device = parts[1]
            value = parts[2].lower()
            state["commands"].append(raw)
            settings = {
                "ka": "power",
                "xb": "input",
                "kf": "volume",
                "ke": "mute",
                "kl": "osd",
                "fg": "auto_sleep",
                "fj": "dpm",
                "fw": "wol",
            }
            if cmd in settings:
                key = settings[cmd]
                if value != "ff":
                    state[key] = int(value, 16)
                result = f"{int(state.get(key, 0)):02x}"
            elif cmd == "sv":
                result = (
                    value + ("01" if state["signal"] else "00")
                    if value == "02"
                    else value + "00"
                )
            elif cmd == "sn":
                result = value + "01"
            elif cmd == "mc":
                result = value
            else:
                result = None
            writer.write(
                (
                    f"{cmd[1]} {device} "
                    + ("OK" + result + "x" if result is not None else "NG00x")
                ).encode()
            )
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError):
        pass
    finally:
        writer.close()


async def control(request):
    if request.method == "POST":
        values = await request.json()
        for key in ("power", "input", "signal", "volume", "mute"):
            if key in values:
                state[key] = values[key]
    return web.json_response(state)


async def main():
    app = web.Application()
    app.router.add_get("/state", control)
    app.router.add_post("/state", control)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 18762).start()
    server = await asyncio.start_server(handle, "0.0.0.0", 18761)
    print("LG simulator ready on 18761", flush=True)
    try:
        async with server:
            await server.serve_forever()
    finally:
        await runner.cleanup()


asyncio.run(main())
