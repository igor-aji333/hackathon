import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from airport_mcp.server import CSV_PATH, DOWNLOAD_TIME_PATH, download_csv, extract_apt_rwy_from_zip, get_current_subscription_url, get_subscription_info, load_data, needs_download, query_airport


class TestAirportMCP:
    def test_get_subscription_info_parses_current_section(self):
        html_with_multiple_sections = """
        <html>
            <div>Preview</div>
            <p>Subscription effective October 29, 2026</p>
            <div id="current">
                <p>Subscription effective October 01, 2026</p>
            </div>
            <div>Archives</div>
            <p>Subscription effective September 03, 2026</p>
        </html>
        """
        with patch('airport_mcp.server.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = html_with_multiple_sections
            mock_get.return_value = mock_response
            
            date, _ = get_subscription_info()
            assert date == "October 01, 2026"
    
    def test_get_current_subscription_url_format(self):
        with patch('airport_mcp.server.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = """
            <html>
                <div id="current">
                    <p>Subscription effective October 01, 2026</p>
                </div>
            </html>
            """
            mock_get.return_value = mock_response
            
            url = get_current_subscription_url()
            assert "nfdc.faa.gov/webContent/28DaySub/extra/" in url
            assert "_APT_CSV.zip" in url
            assert "01_Oct_2026" in url
    
    def test_get_subscription_info_ignores_preview_and_archives(self):
        html_content = """
        <html>
            <div>Preview</div>
            <p>Subscription effective October 29, 2026</p>
            
            <div id="current">
                <p>Subscription effective October 01, 2026</p>
            </div>
            
            <div>Archives</div>
            <p>Subscription effective September 03, 2026</p>
            <p>Subscription effective August 06, 2026</p>
        </html>
        """
        with patch('airport_mcp.server.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = html_content
            mock_get.return_value = mock_response
            
            date, _ = get_subscription_info()
            assert date == "October 01, 2026"
            assert "Preview" not in date
            assert "September" not in date
            assert "August" not in date
    
    def test_extract_apt_rwy_from_zip(self, tmp_path):
        test_csv = b"ARPT_ID,RWY_ID,RWY_LEN\nJFK,04L,14000\nJFK,04R,14000\n"
        
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("extra/2026-10-01_APT_RWY.csv", test_csv)
        
        with patch('airport_mcp.server.CSV_PATH', tmp_path / "apt_rwy.csv"):
            with patch('airport_mcp.server.DOWNLOAD_TIME_PATH', tmp_path / "download_time.txt"):
                extract_apt_rwy_from_zip(str(zip_path))
                
                assert (tmp_path / "apt_rwy.csv").exists()
                df = pd.read_csv(tmp_path / "apt_rwy.csv")
                assert len(df) == 2
                assert df.iloc[0]["ARPT_ID"] == "JFK"
    
    def test_needs_download_no_file(self, tmp_path):
        with patch('airport_mcp.server.CSV_PATH', tmp_path / "nonexistent.csv"):
            with patch('airport_mcp.server.DOWNLOAD_TIME_PATH', tmp_path / "time.txt"):
                assert needs_download() is True
    
    def test_needs_download_recent(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        time_path = tmp_path / "time.txt"
        csv_path.touch()
        time_path.write_text(datetime.now().isoformat())
        
        with patch('airport_mcp.server.CSV_PATH', csv_path):
            with patch('airport_mcp.server.DOWNLOAD_TIME_PATH', time_path):
                assert needs_download() is False
    
    def test_needs_download_old(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        time_path = tmp_path / "time.txt"
        csv_path.touch()
        time_path.write_text(datetime.now().replace(year=2020).isoformat())
        
        with patch('airport_mcp.server.CSV_PATH', csv_path):
            with patch('airport_mcp.server.DOWNLOAD_TIME_PATH', time_path):
                assert needs_download() is True
    
    def test_query_airport_found(self, tmp_path):
        test_csv = b"ARPT_ID,ARPT_NAME,CITY,STATE_CODE,COUNTRY_CODE,RWY_ID,RWY_LEN,RWY_WIDTH,SURFACE_TYPE_CODE,COND,RWYG_CODE,LAT1_DECIMAL,LONG1_DECIMAL,LAT2_DECIMAL,LONG2_DECIMAL\nJFK,JOHN F KENNEDY INTERNATIONAL,AIRPORT,US,NY,04L/22R,14000,150,CONC,STD,RWY,40.641389,-73.778056,40.631389,-73.768056\nJFK,JOHN F KENNEDY INTERNATIONAL,AIRPORT,US,NY,04R/22L,14000,150,CONC,STD,RWY,40.640389,-73.778056,40.630389,-73.768056\n"
        
        csv_path = tmp_path / "apt_rwy.csv"
        csv_path.write_bytes(test_csv)
        time_path = tmp_path / "download_time.txt"
        time_path.write_text(datetime.now().isoformat())
        
        with patch('airport_mcp.server.CSV_PATH', csv_path):
            with patch('airport_mcp.server.DOWNLOAD_TIME_PATH', time_path):
                with patch('airport_mcp.server.needs_download', return_value=False):
                    result = query_airport("JFK")
                    
                    assert result is not None
                    assert result["icao_id"] == "JFK"
                    assert result["name"] == "JOHN F KENNEDY INTERNATIONAL"
                    assert result["city"] == "AIRPORT"
                    assert result["state"] == "NY"
                    assert len(result["runways"]) == 2
                    assert result["runways"][0]["rwy_id"] == "04L/22R"
                    assert result["runways"][0]["length_ft"] == 14000
    
    def test_query_airport_not_found(self, tmp_path):
        test_csv = b"ARPT_ID,RWY_ID,RWY_LEN\nLAX,04L,12000\n"
        
        csv_path = tmp_path / "apt_rwy.csv"
        csv_path.write_bytes(test_csv)
        time_path = tmp_path / "download_time.txt"
        time_path.write_text(datetime.now().isoformat())
        
        with patch('airport_mcp.server.CSV_PATH', csv_path):
            with patch('airport_mcp.server.DOWNLOAD_TIME_PATH', time_path):
                with patch('airport_mcp.server.needs_download', return_value=False):
                    result = query_airport("JFK")
                    assert result is None


class TestIntegration:
    def test_json_output_format(self, tmp_path):
        test_csv = b"ARPT_ID,ARPT_NAME,CITY,STATE_CODE,COUNTRY_CODE,RWY_ID,RWY_LEN,RWY_WIDTH,SURFACE_TYPE_CODE,COND,RWYG_CODE,LAT1_DECIMAL,LONG1_DECIMAL,LAT2_DECIMAL,LONG2_DECIMAL\nJFK,JFK AIRPORT,NEW YORK,NY,US,04L/22R,14000,150,CONC,STD,RWY,40.641389,-73.778056,40.631389,-73.768056\n"
        
        csv_path = tmp_path / "apt_rwy.csv"
        csv_path.write_bytes(test_csv)
        time_path = tmp_path / "download_time.txt"
        time_path.write_text(datetime.now().isoformat())
        
        with patch('airport_mcp.server.CSV_PATH', csv_path):
            with patch('airport_mcp.server.DOWNLOAD_TIME_PATH', time_path):
                with patch('airport_mcp.server.needs_download', return_value=False):
                    result = query_airport("JFK")
                    json_output = json.dumps(result, indent=2)
                    
                    parsed = json.loads(json_output)
                    assert "icao_id" in parsed
                    assert "runways" in parsed
                    assert isinstance(parsed["runways"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])