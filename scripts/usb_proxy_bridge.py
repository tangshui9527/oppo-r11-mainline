#!/usr/bin/env python3
import asyncio
import sys

LOCAL_HOST = '0.0.0.0'
LOCAL_PORT = 8080
TARGET_HOST = '127.0.0.1'
TARGET_PORT = 7890

async def pipe(reader, writer):
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()

async def handle_client(client_reader, client_writer):
    try:
        remote_reader, remote_writer = await asyncio.open_connection(TARGET_HOST, TARGET_PORT)
    except Exception as e:
        client_writer.close()
        return

    asyncio.create_task(pipe(client_reader, remote_writer))
    asyncio.create_task(pipe(remote_reader, client_writer))

async def main():
    server = await asyncio.start_server(handle_client, LOCAL_HOST, LOCAL_PORT)
    print(f"Proxy bridge listening on {LOCAL_HOST}:{LOCAL_PORT} -> {TARGET_HOST}:{TARGET_PORT}", flush=True)
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
