import io
import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from airport_mcp.faa_data_client import (
    FAADataService, StorageBackend, StorageConfig, StorageManager,
    TIMESTAMP_FILENAME
)
from airport_mcp.airport_get_runways import AirportRunwayManager
from airport_mcp.airport_get_runway_ends import AirportRunwayEndManager

# --- MOCK DATA ---
MOCK_HTML_CONTENT = """
<html>
    <body>
        <strong>Subscription effective October 01, 2026</strong>
    </body>
</html>
"""

def create_mock_zip_bytes(target_csv: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr(target_csv, content)
    return buf.getvalue()


# --- FAA Data Client Tests ---
class TestFAADataClient:
    
    @pytest.mark.asyncio
    async def test_get_subscription_date_valid(self):
        config = StorageConfig(backend=StorageBackend.LOCAL, local_path=Path("/tmp/mock"))
        service = FAADataService(StorageManager(config), "APT_RWY")
        
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = MOCK_HTML_CONTENT
            mock_get.return_value = mock_response
            
            date = await service._get_subscription_date()
            assert date.year == 2026
            assert date.month == 10
            assert date.day == 1

    @pytest.mark.asyncio
    async def test_extract_target_csv(self):
        config = StorageConfig(backend=StorageBackend.LOCAL, local_path=Path("/tmp/mock"))
        service = FAADataService(StorageManager(config), "APT_RWY")
        
        test_csv = b"ARPT_ID,RWY_ID,RWY_LEN\nJFK,04L,14000\nJFK,04R,14000\n"
        zip_bytes = create_mock_zip_bytes("2026-10-01_APT_RWY.csv", test_csv)
        
        with patch.object(service, '_get_or_download_archive', new_callable=AsyncMock, return_value=zip_bytes):
            df = await service._extract_target_csv(datetime(2026, 10, 1))
            assert len(df) == 2
            assert df.iloc[0]["ARPT_ID"] == "JFK"


# --- Storage Manager Tests ---
class TestStorageManager:
    
    def test_storage_config_from_env_local(self):
        with patch.dict(os.environ, {}, clear=True):
            config = StorageConfig.from_env()
            assert config.backend == StorageBackend.LOCAL
            
    def test_storage_config_from_env_s3(self):
        with patch.dict(os.environ, {
            "AIRPORT_MCP_STORAGE_BACKEND": "s3",
            "AIRPORT_MCP_S3_BUCKET": "test-bucket",
            "AIRPORT_MCP_S3_KEY": "test/prefix/"
        }, clear=True):
            config = StorageConfig.from_env()
            assert config.backend == StorageBackend.S3
            assert config.s3_bucket == "test-bucket"
            assert config.s3_prefix == "test/prefix/"
            
    def test_storage_config_databricks_env_var(self):
        with patch.dict(os.environ, {"DATABRICKS_RUNTIME_VERSION": "12.2"}, clear=True):
            config = StorageConfig.from_env()
            assert config.backend == StorageBackend.DATABRICKS

    def test_manager_save_and_load_local(self, tmp_path):
        config = StorageConfig(backend=StorageBackend.LOCAL, local_path=tmp_path)
        manager = StorageManager(config)
        
        timestamp = datetime(2026, 10, 1)
        manager.save_cycle_timestamp(timestamp)
        assert manager.load_cycle_timestamp() == timestamp
        
        test_data = b"PARQUET_DATA_MOCK"
        dataset_name = "TEST_DATA"
        manager.save_parquet(dataset_name, test_data)
        assert manager.load_parquet(dataset_name) == test_data


# --- Server Logic Tests ---
class TestAirportRunwayManager:
    
    @pytest.fixture
    def mock_manager(self):
        manager = AirportRunwayManager()
        mock_df = pd.DataFrame([
            {"ARPT_NAME": "JOHN F KENNEDY INTERNATIONAL", "CITY": "AIRPORT", "STATE_CODE": "NY", "COUNTRY_CODE": "US", "RWY_ID": "04L/22R", "RWY_LEN": "14000", "RWY_WIDTH": "150"},
            {"ARPT_NAME": "JOHN F KENNEDY INTERNATIONAL", "CITY": "AIRPORT", "STATE_CODE": "NY", "COUNTRY_CODE": "US", "RWY_ID": "04R/22L", "RWY_LEN": "14000", "RWY_WIDTH": "150"}
        ], index=["JFK", "JFK"])
        
        manager.client.df = mock_df
        manager.client.last_download = datetime(2026, 10, 1)
        
        # Patch the async preparation layer natively
        manager._prepare_data = AsyncMock()
        return manager
        
    @pytest.mark.asyncio
    async def test_query_airport_found(self, mock_manager):
        result = await mock_manager.query("JFK")
        
        assert result is not None
        assert result["icao_id"] == "JFK"
        assert result["name"] == "JOHN F KENNEDY INTERNATIONAL"
        assert result["city"] == "AIRPORT"
        assert result["state"] == "NY"
        assert len(result["runways"]) == 2
        assert result["runways"][0]["rwy_id"] == "04L/22R"
        assert result["runways"][0]["length_ft"] == 14000.0

    @pytest.mark.asyncio
    async def test_query_airport_not_found(self, mock_manager):
        result = await mock_manager.query("LAX")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_airport_icao_to_faa_conversion(self, mock_manager):
        result = await mock_manager.query("KJFK")
        assert result is not None
        assert result["icao_id"] == "JFK"

    @pytest.mark.asyncio
    async def test_prepare_data_drops_columns_and_rows(self):
        manager = AirportRunwayManager()
        # Mock dataframe with 3 rows. RWY_LEN has 2 valid (passes 50% thresh).
        # MOSTLY_NA_COL has 1 valid (dropped).
        # LAX row will have all NAs in remaining data columns (dropped).
        mock_df = pd.DataFrame({
            "ARPT_ID": ["JFK", "BOS", "LAX"],
            "RWY_ID": ["04L", "09", "24R"],
            "RWY_LEN": ["14000", "10000", pd.NA],
            "MOSTLY_NA_COL": [pd.NA, pd.NA, "TEST"]
        })
        manager.client.df = mock_df
        manager.client.last_download = None
        manager.client.initialize = AsyncMock()

        await manager._prepare_data()
        df = manager.client.df

        # MOSTLY_NA_COL should be dropped
        assert "MOSTLY_NA_COL" not in df.columns
        # RWY_LEN survives. Then LAX is dropped because RWY_LEN is NA.
        # JFK and BOS survive.
        assert len(df) == 2
        assert "JFK" in df.index
        assert "BOS" in df.index
        
class TestAirportRunwayEndManager:
    
    @pytest.fixture
    def mock_end_manager(self):
        manager = AirportRunwayEndManager()
        mock_df = pd.DataFrame([
            {"CITY": "JAMAICA", "STATE_CODE": "NY", "COUNTRY_CODE": "US", "RWY_ID": "04L/22R", "RWY_END_ID": "04L", "RWY_END_ELEV": "12.5", "VISUAL_GLIDE_PATH_ANGLE": "3.0"},
            {"CITY": "JAMAICA", "STATE_CODE": "NY", "COUNTRY_CODE": "US", "RWY_ID": "04L/22R", "RWY_END_ID": "22R", "RWY_END_ELEV": "11.1", "VISUAL_GLIDE_PATH_ANGLE": "3.0"}
        ], index=["JFK", "JFK"])
        
        manager.client.df = mock_df
        manager.client.last_download = datetime(2026, 10, 1)
        manager._prepare_data = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_query_runway_end_found(self, mock_end_manager):
        result = await mock_end_manager.query("JFK")
        
        assert result is not None
        assert result["icao_id"] == "JFK"
        assert result["city"] == "JAMAICA"
        assert len(result["runway_ends"]) == 2
        assert result["runway_ends"][0]["rwy_end_id"] == "04L"
        assert result["runway_ends"][0]["elevation_ft"] == 12.5
        assert result["runway_ends"][0]["visual_glide_path_angle"] == 3.0

    @pytest.mark.asyncio
    async def test_query_runway_end_not_found(self, mock_end_manager):
        result = await mock_end_manager.query("LAX")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_runway_end_json_format(self, mock_end_manager):
        result = await mock_end_manager.query("JFK")
        json_output = json.dumps(result)
        
        parsed = json.loads(json_output)
        assert "icao_id" in parsed
        assert "runway_ends" in parsed
        assert isinstance(parsed["runway_ends"], list)

    @pytest.mark.asyncio
    async def test_prepare_data_drops_columns_and_rows(self):
        manager = AirportRunwayEndManager()
        mock_df = pd.DataFrame({
            "ARPT_ID": ["JFK", "BOS", "LAX"],
            "RWY_ID": ["04L/22R", "09/27", "24L/24R"],
            "RWY_END_ID": ["04L", "09", "24L"],
            "RWY_END_ELEV": ["12.5", "15.0", pd.NA],
            "SPARSE_COL": [pd.NA, pd.NA, "TEST"]
        })
        manager.client.df = mock_df
        manager.client.last_download = None
        manager.client.initialize = AsyncMock()

        await manager._prepare_data()
        df = manager.client.df

        assert "SPARSE_COL" not in df.columns
        assert len(df) == 2
        assert "JFK" in df.index
        assert "BOS" in df.index

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
    
