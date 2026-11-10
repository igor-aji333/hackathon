import asyncio
from datetime import date

import pytest

from airport_mcp.config import Settings
from airport_mcp.repository import AirportRepository, DataUnavailableError, cache_name
from conftest import CURRENT_CYCLE, FakeDownloader

NEXT_CYCLE = date(2026, 11, 26)


async def test_first_load_downloads_once_and_caches_every_table(repository, downloader, store):
    dataset = await repository.get()
    await repository.get()

    assert dataset.cycle == CURRENT_CYCLE
    assert downloader.requested == [CURRENT_CYCLE]
    for table in ("APT_BASE", "APT_RWY", "APT_RWY_END"):
        assert store.read(cache_name(CURRENT_CYCLE, table)) is not None


async def test_cached_cycle_is_reused_by_a_new_process(repository, store):
    await repository.get()
    offline = FakeDownloader(fail=True)
    restarted = AirportRepository(store, downloader=offline, today=lambda: date(2026, 11, 10))

    assert (await restarted.get()).cycle == CURRENT_CYCLE
    assert offline.requested == []


async def test_concurrent_cold_requests_share_one_download(repository, downloader):
    datasets = await asyncio.gather(*(repository.get() for _ in range(10)))

    assert downloader.requested == [CURRENT_CYCLE]
    assert all(d is datasets[0] for d in datasets)


async def test_new_cycle_refreshes_all_tables_together(store, downloader):
    today = [date(2026, 11, 10)]
    repository = AirportRepository(store, downloader=downloader, today=lambda: today[0])
    await repository.get()

    today[0] = NEXT_CYCLE
    dataset = await repository.get()

    assert dataset.cycle == NEXT_CYCLE
    assert downloader.requested == [CURRENT_CYCLE, NEXT_CYCLE]
    for table in ("APT_BASE", "APT_RWY", "APT_RWY_END"):
        assert store.read(cache_name(NEXT_CYCLE, table)) is not None


async def test_failed_refresh_keeps_serving_previous_cycle_without_retry_storm(store, downloader):
    today = [date(2026, 11, 10)]
    repository = AirportRepository(store, downloader=downloader, today=lambda: today[0])
    await repository.get()

    today[0] = NEXT_CYCLE
    downloader.fail = True
    assert (await repository.get()).cycle == CURRENT_CYCLE
    assert (await repository.get()).cycle == CURRENT_CYCLE
    assert downloader.requested == [CURRENT_CYCLE, NEXT_CYCLE]


async def test_cold_start_offline_falls_back_to_older_cached_cycle(store, downloader):
    await AirportRepository(store, downloader=downloader, today=lambda: date(2026, 11, 10)).get()
    offline = AirportRepository(store, downloader=FakeDownloader(fail=True), today=lambda: NEXT_CYCLE)

    assert (await offline.get()).cycle == CURRENT_CYCLE


async def test_cold_start_offline_without_cache_raises(store):
    repository = AirportRepository(store, downloader=FakeDownloader(fail=True))
    with pytest.raises(DataUnavailableError):
        await repository.get()


def test_s3_backend_requires_bucket(monkeypatch):
    monkeypatch.setenv("AIRPORT_MCP_STORAGE_BACKEND", "s3")
    monkeypatch.delenv("AIRPORT_MCP_S3_BUCKET", raising=False)
    with pytest.raises(ValueError, match="AIRPORT_MCP_S3_BUCKET"):
        Settings(_env_file=None)
