import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
from fastmcp import FastMCP

mcp = FastMCP("Airport MCP Server")

FAA_NASR_URL = "https://www.faa.gov/air_traffic/flight_info/aeronav/Aero_Data/NASR_Subscription/"

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}

MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
}


class StorageBackend(Enum):
    LOCAL = "local"
    S3 = "s3"
    DATABRICKS = "databricks"


@dataclass
class StorageConfig:
    backend: StorageBackend
    local_path: Optional[Path] = None
    s3_bucket: Optional[str] = None
    s3_key: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "StorageConfig":
        backend_str = os.environ.get("AIRPORT_MCP_STORAGE_BACKEND", "local").lower()
        backend = StorageBackend(backend_str)
        
        if backend == StorageBackend.S3:
            return cls(
                backend=backend,
                s3_bucket=os.environ.get("AIRPORT_MCP_S3_BUCKET"),
                s3_key=os.environ.get("AIRPORT_MCP_S3_KEY", "airport_mcp/")
            )
        elif backend == StorageBackend.DATABRICKS:
            return cls(
                backend=backend,
                local_path=Path("/dbfs/mnt/airport_mcp_data")
            )
        else:
            return cls(
                backend=backend,
                local_path=Path.home() / ".airport_mcp_data"
            )


config = StorageConfig.from_env()


def detect_environment() -> StorageBackend:
    """Detect the current runtime environment."""
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        return StorageBackend.DATABRICKS
    
    if config.backend == StorageBackend.S3:
        return StorageBackend.S3
    
    return StorageBackend.LOCAL


def get_base_data_dir() -> Path:
    """Get the base directory for data storage."""
    if detect_environment() == StorageBackend.DATABRICKS and config.local_path:
        return config.local_path
    elif detect_environment() == StorageBackend.S3 and config.local_path:
        return config.local_path
    else:
        base_dir = Path.home() / ".airport_mcp_data"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir


BASE_DATA_DIR = get_base_data_dir()
CSV_PATH = BASE_DATA_DIR / "apt_rwy.csv"
DOWNLOAD_TIME_PATH = BASE_DATA_DIR / "download_time.txt"


def parse_zip_date(zip_url: str) -> datetime:
    """Parse the date from the zip filename."""
    match = re.search(r'(\d{2})_(\w{3})_(\d{4})', zip_url)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        year = int(match.group(3))
        month = MONTH_MAP.get(month_str, 1)
        return datetime(year, month, day)
    return datetime.now()


def get_subscription_info() -> tuple[str, str]:
    """Get the current subscription date from FAA page (under 'Current' section only)."""
    response = requests.get(FAA_NASR_URL, timeout=30)
    response.raise_for_status()
    
    lines = response.text.split('\n')
    in_current_section = False
    
    for line in lines:
        if 'id="current"' in line.lower() or '>Current<' in line:
            in_current_section = True
            continue
        if '>Archives<' in line or 'Preview' in line:
            in_current_section = False
            continue
        if in_current_section:
            pattern = r'Subscription effective (\w+ \d{1,2}, \d{4})'
            match = re.search(pattern, line)
            if match:
                return match.group(1), ""
    
    pattern = r'Subscription effective (\w+ \d{1,2}, \d{4})'
    match = re.search(pattern, response.text)
    
    if match:
        return match.group(1), ""
    
    raise ValueError("Could not find current subscription")


def get_current_subscription_url() -> str:
    """Get the URL for the current subscription from FAA page."""
    date_str, _ = get_subscription_info()
    
    month_names_map = {
        "January": "Jan", "February": "Feb", "March": "Mar", "April": "Apr",
        "May": "May", "June": "Jun", "July": "Jul", "August": "Aug",
        "September": "Sep", "October": "Oct", "November": "Nov", "December": "Dec"
    }
    
    for full, short in month_names_map.items():
        date_str = date_str.replace(full, short)
    
    date_str = date_str.replace(" ", "_").replace(",", "")
    date_parts = date_str.split("_")
    if len(date_parts) >= 3:
        month = date_parts[0]
        day = date_parts[1].zfill(2)
        year = date_parts[2]
        formatted_date = f"{day}_{month}_{year}"
    else:
        formatted_date = date_str
    
    zip_url = f"https://nfdc.faa.gov/webContent/28DaySub/extra/{formatted_date}_APT_CSV.zip"
    return zip_url


def save_to_local(csv_content: bytes, timestamp: datetime) -> None:
    """Save CSV and timestamp to local filesystem."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_bytes(csv_content)
    DOWNLOAD_TIME_PATH.write_text(timestamp.isoformat())


def save_to_s3(csv_content: bytes, timestamp: datetime) -> None:
    """Save CSV and timestamp to AWS S3."""
    try:
        import boto3
        s3 = boto3.client('s3')
        
        s3.put_object(
            Bucket=config.s3_bucket,
            Key=f"{config.s3_key}apt_rwy.csv",
            Body=csv_content
        )
        s3.put_object(
            Bucket=config.s3_bucket,
            Key=f"{config.s3_key}download_time.txt",
            Body=timestamp.isoformat().encode()
        )
    except ImportError:
        raise ImportError("boto3 is required for S3 storage. Install with: pip install boto3")


def save_to_databricks(csv_content: bytes, timestamp: datetime) -> None:
    """Save CSV and timestamp to Databricks filesystem."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_bytes(csv_content)
    DOWNLOAD_TIME_PATH.write_text(timestamp.isoformat())


def read_from_local() -> tuple[bytes, Optional[datetime]]:
    """Read CSV and timestamp from local filesystem."""
    if CSV_PATH.exists():
        csv_data = CSV_PATH.read_bytes()
        timestamp_str = DOWNLOAD_TIME_PATH.read_text().strip() if DOWNLOAD_TIME_PATH.exists() else ""
        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None
        return csv_data, timestamp
    return b"", None


def read_from_s3() -> tuple[bytes, Optional[datetime]]:
    """Read CSV and timestamp from AWS S3."""
    try:
        import boto3
        s3 = boto3.client('s3')
        
        csv_obj = s3.get_object(Bucket=config.s3_bucket, Key=f"{config.s3_key}apt_rwy.csv")
        csv_data = csv_obj['Body'].read()
        
        time_obj = s3.get_object(Bucket=config.s3_bucket, Key=f"{config.s3_key}download_time.txt")
        timestamp_str = time_obj['Body'].read().decode().strip()
        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None
        
        return csv_data, timestamp
    except Exception:
        return b"", None


def read_from_databricks() -> tuple[bytes, Optional[datetime]]:
    """Read CSV and timestamp from Databricks filesystem."""
    if CSV_PATH.exists():
        csv_data = CSV_PATH.read_bytes()
        timestamp_str = DOWNLOAD_TIME_PATH.read_text().strip() if DOWNLOAD_TIME_PATH.exists() else ""
        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None
        return csv_data, timestamp
    return b"", None


def extract_apt_rwy_from_zip(zip_url: str) -> tuple[bytes, datetime]:
    """Download zip and extract APT_RWY.csv."""
    response = requests.get(zip_url, timeout=300)
    response.raise_for_status()
    
    download_date = parse_zip_date(zip_url)
    
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        apt_rwy_files = [f for f in zf.namelist() if "APT_RWY" in f and f.endswith(".csv")]
        
        if apt_rwy_files:
            csv_content = zf.read(apt_rwy_files[0])
        else:
            csv_files = [f for f in zf.namelist() if f.endswith(".csv")]
            if csv_files:
                csv_content = zf.read(csv_files[0])
            else:
                raise ValueError("No CSV files found in zip archive")
    
    return csv_content, download_date


def save_data(csv_content: bytes, timestamp: datetime) -> None:
    """Save data to the configured storage backend."""
    backend = detect_environment()
    
    if config.backend == StorageBackend.S3 or backend == StorageBackend.S3:
        if not config.s3_bucket:
            raise ValueError("S3 bucket not configured. Set AIRPORT_MCP_S3_BUCKET environment variable.")
        save_to_s3(csv_content, timestamp)
    else:
        save_to_local(csv_content, timestamp)
    
    if backend == StorageBackend.DATABRICKS:
        save_to_databricks(csv_content, timestamp)


def load_data_from_storage() -> tuple[bytes, Optional[datetime]]:
    """Load data from the configured storage backend."""
    backend = detect_environment()
    
    if backend == StorageBackend.S3:
        if config.s3_bucket:
            return read_from_s3()
    
    csv_data, ts = read_from_local()
    if csv_data:
        return csv_data, ts
    
    if config.s3_bucket:
        csv_data, ts = read_from_s3()
        if csv_data:
            return csv_data, ts
    
    return b"", None


def download_csv() -> str:
    """Download the runway data from FAA zip archive."""
    zip_url = get_current_subscription_url()
    csv_content, download_date = extract_apt_rwy_from_zip(zip_url)
    save_data(csv_content, download_date)
    return download_date.isoformat()


def needs_download() -> bool:
    """Check if CSV needs to be downloaded (every 28 days)."""
    if not CSV_PATH.exists():
        csv_data, _ = load_data_from_storage()
        if not csv_data:
            return True
    
    _, last_download = load_data_from_storage()
    
    if last_download is None:
        return False
    
    return (datetime.now() - last_download).days > 28


def load_data() -> pd.DataFrame:
    """Load runway data from CSV, downloading if needed."""
    csv_data, _ = load_data_from_storage()
    
    if not csv_data or needs_download():
        download_csv()
        csv_data, _ = load_data_from_storage()
    
    if not csv_data:
        raise ValueError("Could not load runway data from any storage backend")
    
    return pd.read_csv(io.BytesIO(csv_data))


def normalize_airport_id(ident: str) -> str:
    """Normalize airport ID to FAA format.
    
    FAA data uses FAA IDs like 'LAX', 'JFK'.
    ICAO codes in US have 'K' prefix like 'KLAX', 'KJFK'.
    This function converts ICAO to FAA ID for database lookup.
    """
    ident_upper = ident.upper()
    
    if ident_upper.startswith("K") and len(ident_upper) == 6:
        return ident_upper[1:]
    
    return ident_upper


def query_airport(ident: str) -> dict[str, Any] | None:
    """Query airport by ICAO/FAA ID and return runway data."""
    df = load_data()
    ident_normalized = normalize_airport_id(ident)
    
    airport_df = df[df["ARPT_ID"] == ident_normalized]
    
    if airport_df.empty:
        try:
            mask = df["ARPT_ID"].str.upper() == ident_normalized
            airport_df = df[mask]
        except Exception:
            pass
    
    if airport_df.empty:
        try:
            download_csv()
            df = load_data()
            airport_df = df[df["ARPT_ID"] == ident_normalized]
            
            if airport_df.empty:
                try:
                    mask = df["ARPT_ID"].str.upper() == ident_normalized
                    airport_df = df[mask]
                except Exception:
                    pass
        except Exception:
            return None
    
    if airport_df.empty:
        return None
    
    first = airport_df.iloc[0]
    runways: list[dict[str, Any]] = []
    
    for _, row in airport_df.iterrows():
        length_val = row.get("RWY_LEN")
        width_val = row.get("RWY_WIDTH")
        runways.append({
            "rwy_id": row.get("RWY_ID"),
            "length_ft": int(length_val) if pd.notna(length_val) else None,
            "width_ft": int(width_val) if pd.notna(width_val) else None,
            "surface": row.get("SURFACE_TYPE_CODE"),
            "condition": row.get("COND"),
            "latitude_1": row.get("LAT1_DECIMAL"),
            "longitude_1": row.get("LONG1_DECIMAL"),
            "latitude_2": row.get("LAT2_DECIMAL"),
            "longitude_2": row.get("LONG2_DECIMAL"),
            "lights": row.get("RWY_LGT_CODE"),
        })
    
    return {
        "icao_id": first.get("ARPT_ID"),
        "name": first.get("ARPT_NAME"),
        "city": first.get("CITY"),
        "state": first.get("STATE_CODE"),
        "country": first.get("COUNTRY_CODE"),
        "runways": runways,
    }


@mcp.tool()
def get_airport_runways(icao_or_faa_id: str) -> str:
    """
    Query an airport by ICAO or FAA identifier and get runway information.
    
    Args:
        icao_or_faa_id: The ICAO or FAA identifier for the airport (e.g., 'JFK', 'KLAX')
    
    Returns:
        JSON object with airport information and runway details
    """
    result = query_airport(icao_or_faa_id)
    
    if result is None:
        return json.dumps({
            "error": f"Airport '{icao_or_faa_id}' not found"
        }, indent=2)
    
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run()