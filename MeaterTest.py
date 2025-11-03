#!env python

import aiohttp
import asyncio
from meater import MeaterApi
from pprint import pprint


def main():
    async def fetch_data():
        async with aiohttp.ClientSession() as session:

            api = MeaterApi(session)

            print('Logging in...  ', end='')
            await api.authenticate('gillisj+meater@gmail.com', 'skinapst')
            print('  Success!');

            print('Fetching devices...  ', end='')
            devices = await api.get_all_devices()
            print('Fetched.')
            return devices

    devices = asyncio.run(fetch_data())

    print(f'Found {len(devices)} temperature probes')

    for probe in devices:
        if probe.cook is not None:
            print(f'id       = {probe.id}')
            print(f'internal = {probe.internal_temperature}')
            print(f'ambient  = {probe.ambient_temperature}')
            print(f'time     = {probe.time_updated}')
            if probe.cook is not None:
                print(f'cook:      id: {probe.cook.id}')
                print(f'           name: {probe.cook.name}')
                print(f'           state: {probe.cook.state}')
                print(f'           target temp: {probe.cook.target_temperature}')
                print(f'           peak temp: {probe.cook.peak_temperature}')
                print(f'           remaining: {probe.cook.time_remaining}')
                print(f'           elapsed: {probe.cook.time_elapsed}')
            print('=====================')

if __name__ == '__main__':
    main()
