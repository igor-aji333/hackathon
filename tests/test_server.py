import io
import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from airport_mcp.server import (
    StorageBackend, StorageConfig, StorageManager,
    download_and_extract_df, get_current_subscription_url,
    get_subscription_date, normalize_airport_id, query_airport
)


class TestAirportMCP:
    def test_get_subscription_date_valid(self):
        html_content = """
        <html>
            <body>
                <p>Some random text here.</p>
                <strong>Subscription effective October 01, 2026</strong>
            </body>
        </html>
        """
        with patch('airport_mcp.server.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = html_content
            mock_get.return_value = mock_response
            
            date = get_subscription_date()
            assert isinstance(date, datetime)
            assert date.year == 2026
            assert date.month == 10
            assert date.day == 1
            
    def test_get_subscription_date_invalid(self):
        html_content = "<html><body><p>No valid date here.</p></body></html>"
        with patch('airport_mcp.server.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = html_content
            mock_get.return_value = mock_response
            
            with pytest.raises(ValueError, match="Could not find a valid subscription date"):
                get_subscription_date()
                
    def test_get_current_subscription_url_format(self):
        with patch('airport_mcp.server.get_subscription_date', return_value=datetime(2026, 10, 1)):
            url = get_current_subscription_url()
            assert "nfdc.faa.gov/webContent/28DaySub/extra/" in url
            assert "01_Oct_2026_APT_CSV.zip" in url

    def test_download_and_extract_df(self, tmp_path):
        test_csv = b"ARPT_ID,RWY_ID,RWY_LEN\nJFK,04L,14000\nJFK,04R,14000\n"
        
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("extra/2026-10-01_APT_RWY.csv", test_csv)
        
        with open(zip_path, 'rb') as f:
            zip_content = f.read()
            
        mock_response = MagicMock()
        mock_response.content = zip_content
        mock_response.raise_for_status = MagicMock()
        
        with patch('airport_mcp.server.get_current_subscription_url', return_value="https://mock.url"):
            with patch('airport_mcp.server.get_subscription_date', return_value=datetime(2026, 10, 1)):
                with patch('airport_mcp.server.requests.get', return_value=mock_response):
                    df, download_date = download_and_extract_df()
                    
                    assert len(df) == 2
                    assert df.iloc[0]["ARPT_ID"] == "JFK"
                    assert download_date.year == 2026
                    assert download_date.month == 10

    def test_query_airport_found(self):
        mock_df = pd.DataFrame([
            {"ARPT_NAME": "JOHN F KENNEDY INTERNATIONAL", "CITY": "AIRPORT", "STATE_CODE": "NY", "COUNTRY_CODE": "US", "RWY_ID": "04L/22R", "RWY_LEN": "14000"},
            {"ARPT_NAME": "JOHN F KENNEDY INTERNATIONAL", "CITY": "AIRPORT", "STATE_CODE": "NY", "COUNTRY_CODE": "US", "RWY_ID": "04R/22L", "RWY_LEN": "14000"}
        ], index=["JFK", "JFK"])
        
        with patch('airport_mcp.server.load_data', return_value=mock_df):
            result = query_airport("JFK")
            
            assert result is not None
            assert result["icao_id"] == "JFK"
            assert result["name"] == "JOHN F KENNEDY INTERNATIONAL"
            assert result["city"] == "AIRPORT"
            assert result["state"] == "NY"
            assert len(result["runways"]) == 2
            assert result["runways"][0]["rwy_id"] == "04L/22R"
            assert result["runways"][0]["length_ft"] == 14000.0

    def test_query_airport_not_found(self):
        mock_df = pd.DataFrame([
            {"ARPT_NAME": "LOS ANGELES", "RWY_ID": "04L", "RWY_LEN": "12000"}
        ], index=["LAX"])
        
        with patch('airport_mcp.server.load_data', return_value=mock_df):
            result = query_airport("JFK")
            assert result is None

    def test_query_airport_icao_to_faa_conversion(self):
        mock_df = pd.DataFrame([
            {"ARPT_NAME": "LOS ANGELES", "CITY": "CA", "RWY_ID": "04L/22R", "RWY_LEN": "12000"}
        ], index=["LAX"])
        
        with patch('airport_mcp.server.load_data', return_value=mock_df):
            result = query_airport("KLAX")
            assert result is not None
            assert result["icao_id"] == "LAX"

    def test_normalize_airport_id(self):
        assert normalize_airport_id("LAX") == "LAX"
        assert normalize_airport_id("KLAX") == "LAX"
        assert normalize_airport_id("JFK") == "JFK"
        assert normalize_airport_id("KJFK") == "JFK"
        assert normalize_airport_id("klax") == "LAX"
        assert normalize_airport_id("kjfk") == "JFK"


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
            assert config.s3_key == "test/prefix/"
            
    def test_storage_config_databricks(self):
        with patch.dict(os.environ, {"DATABRICKS_RUNTIME_VERSION": "12.2"}, clear=True):
            config = StorageConfig.from_env()
            assert config.backend == StorageBackend.DATABRICKS

    def test_manager_save_and_load_local(self, tmp_path):
        config = StorageConfig(backend=StorageBackend.LOCAL, local_path=tmp_path)
        manager = StorageManager(config)
        
        test_data = b"PARQUET_DATA_MOCK"
        timestamp = datetime(2026, 10, 1)
        
        manager.save(test_data, timestamp)
        
        data, ts = manager.load()
        assert data == test_data
        assert ts == timestamp

    def test_storage_backend_enum(self):
        assert StorageBackend.LOCAL.value == "local"
        assert StorageBackend.S3.value == "s3"
        assert StorageBackend.DATABRICKS.value == "databricks"


class TestIntegration:
    def test_json_output_format(self):
        mock_df = pd.DataFrame([
            {"ARPT_NAME": "JFK AIRPORT", "CITY": "NEW YORK", "STATE_CODE": "NY", "COUNTRY_CODE": "US", "RWY_ID": "04L/22R"}
        ], index=["JFK"])
        
        with patch('airport_mcp.server.load_data', return_value=mock_df):
            result = query_airport("JFK")
            json_output = json.dumps(result, indent=2)
            
            parsed = json.loads(json_output)
            assert "icao_id" in parsed
            assert "runways" in parsed
            assert isinstance(parsed["runways"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
    
