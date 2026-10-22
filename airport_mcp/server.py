import io
import json
import logging
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
from pydantic_settings import  BaseSettings, SettingsConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse


# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Airport MCP Server")

FAA_NASR_URL = "https://www.faa.gov/air_traffic/flight_info/aeronav/Aero_Data/NASR_Subscription/"

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
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
    
    return config.backend


def get_base_data_dir() -> Path:
    """Get the base directory for data storage."""
    base_dir = config.local_path if config.local_path else Path.home() / ".airport_mcp_data"
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
    raise ValueError(f"Could not parse date from zip URL: {zip_url}")


def get_subscription_info() -> str:
    """Get the current subscription date from FAA page (under 'Current' section only)."""
    response = requests.get(FAA_NASR_URL, timeout=30)
    response.raise_for_status()
    
    html = response.text
    
    # Find Current section - try multiple strategies
    current_match = re.search(r'id=["\']current["\']', html, re.IGNORECASE)
    
    if not current_match:
        current_heading_match = re.search(
            r'(?i)(?:<[^>]*>)?\s*Current\s*(?:</[^>]*>)?\s*(?:\n|<)',
            html
        )
        if current_heading_match:
            start_pos = current_heading_match.end()
        else:
            current_match = re.search(r'(?i)\bCurrent\b', html)
            if not current_match:
                raise ValueError("Could not find Current section")
            start_pos = current_match.end()
    else:
        start_pos = current_match.start()
    
    remaining_html = html[start_pos:]
    next_section_match = re.search(
        r'(?i)(?:<[^>]*>)?\s*(?:Archives|Preview)\s*(?:</[^>]*>)?',
        remaining_html
    )
    
    if next_section_match:
        current_section = remaining_html[:next_section_match.start()]
    else:
        current_section = remaining_html[:5000]
    
    pattern = r'Subscription effective (\w+ \d{1,2}, \d{4})'
    match = re.search(pattern, current_section)
    if match:
        return match.group(1)
    
    current_idx = html.find('Current')
    if current_idx != -1:
        after_current = html[current_idx:]
        match_after_current = re.search(pattern, after_current)
        if match_after_current:
            archive_pos = re.search(r'(?i)Archives', after_current[match_after_current.end():])
            preview_pos = re.search(r'(?i)Preview', after_current[match_after_current.end():])
            
            # Fix: Provide default float('inf') to avoid ValueError on empty sequence
            positions = [p.start() for p in [archive_pos, preview_pos] if p]
            min_boundary = min(positions, default=float('inf'))
            
            if not archive_pos or not preview_pos or match_after_current.start() < min_boundary:
                return match_after_current.group(1)
    
    raise ValueError("Could not find subscription date in Current section")


def get_current_subscription_url() -> str:
    """Get the URL for the current subscription from FAA page."""
    date_str = get_subscription_info()
    
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


def read_from_local() -> tuple[bytes, Optional[datetime]]:
    """Read CSV and timestamp from local filesystem."""
    if CSV_PATH.exists():
        csv_data = CSV_PATH.read_bytes()
        timestamp_str = DOWNLOAD_TIME_PATH.read_text().strip() if DOWNLOAD_TIME_PATH.exists() else ""
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None
        except ValueError:
            timestamp = None
        return csv_data, timestamp
    return b"", None


def read_from_s3() -> tuple[bytes, Optional[datetime]]:
    """Read CSV and timestamp from AWS S3."""
    try:
        import boto3
        from botocore.exceptions import ClientError
        s3 = boto3.client('s3')
        
        csv_obj = s3.get_object(Bucket=config.s3_bucket, Key=f"{config.s3_key}apt_rwy.csv")
        csv_data = csv_obj['Body'].read()
        
        time_obj = s3.get_object(Bucket=config.s3_bucket, Key=f"{config.s3_key}download_time.txt")
        timestamp_str = time_obj['Body'].read().decode().strip()
        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None
        
        return csv_data, timestamp
    except ImportError:
        logger.error("boto3 is not installed. Unable to read from S3.")
        return b"", None
    except Exception as e:
        # Fix: Catch and log specific errors instead of silently swallowing exceptions
        logger.error(f"Failed to read from S3: {e}")
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
    
    if backend == StorageBackend.S3:
        if not config.s3_bucket:
            raise ValueError("S3 bucket not configured. Set AIRPORT_MCP_S3_BUCKET environment variable.")
        save_to_s3(csv_content, timestamp)
    elif backend == StorageBackend.DATABRICKS:
        save_to_local(csv_content, timestamp)
    else:
        save_to_local(csv_content, timestamp)


def load_data_from_storage() -> tuple[bytes, Optional[datetime]]:
    """Load data from the configured storage backend."""
    backend = detect_environment()
    
    if backend == StorageBackend.S3:
        if config.s3_bucket:
            csv_data, ts = read_from_s3()
            if csv_data:
                return csv_data, ts
            
    elif backend == StorageBackend.DATABRICKS:
        pass
    
    csv_data, ts = read_from_local()
    if csv_data:
        return csv_data, ts
    
    if config.s3_bucket:
        return read_from_s3()
    
    return b"", None


def download_csv() -> str:
    """Download the runway data from FAA zip archive."""
    zip_url = get_current_subscription_url()
    csv_content, download_date = extract_apt_rwy_from_zip(zip_url)
    save_data(csv_content, download_date)
    return download_date.isoformat()


def needs_download() -> bool:
    """Check if CSV needs to be downloaded (every 28 days)."""
    csv_data, last_download = load_data_from_storage()
    
    if not csv_data or last_download is None:
        return True
    
    return (datetime.now() - last_download).days > 28


def load_data() -> pd.DataFrame:
    """Load runway data from CSV, downloading if needed."""
    # Fix: Utilize the previously dead needs_download() function instead of repeating logic
    if needs_download():
        download_csv()
        
    csv_data, _ = load_data_from_storage()
    
    if not csv_data:
        raise ValueError("Could not load runway data from any storage backend")
    
    return pd.read_csv(io.BytesIO(csv_data))


def normalize_airport_id(ident: str) -> str:
    """Normalize airport ID to FAA format."""
    ident_upper = ident.upper()
    
    if ident_upper.startswith("K") and len(ident_upper) == 4:
        return ident_upper[1:]
    
    return ident_upper


def find_airport_row(df: pd.DataFrame, ident: str) -> pd.DataFrame:
    """Find airport row with multiple lookup strategies."""
    ident_upper = normalize_airport_id(ident)
    
    # Fix: Avoid inefficient df["ARPT_ID"].str.upper() on whole column
    # FAA CSV data inherently holds uppercase IDs
    mask = df["ARPT_ID"] == ident_upper
    airport_df = df[mask]
    
    if not airport_df.empty:
        return airport_df
        
    if ident.upper().startswith("K"):
        mask = df["ARPT_ID"] == ident.upper()
        airport_df = df[mask]
        if not airport_df.empty:
            return airport_df

    return df.head(0)


def query_airport(ident: str) -> dict[str, Any] | None:
    """Query airport by ICAO/FAA ID and return runway data."""
    df = load_data()
    
    airport_df = find_airport_row(df, ident)
    
    if airport_df.empty:
        return None
    
    first = airport_df.iloc[0]
    
    def to_int(val):
        try:
            return int(float(val)) if pd.notna(val) else None
        except (ValueError, TypeError):
            return None
    
    runways = []
    for _, row in airport_df.iterrows():
        runways.append({
            "rwy_id": row.get("RWY_ID"),
            "length_ft": to_int(row.get("RWY_LEN")),
            "width_ft": to_int(row.get("RWY_WIDTH")),
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


class Settings(BaseSettings):
    """MCP server settings. Override any field via environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Transport ─────────────────────────────────────────────────────────────
    # "stdio"           — local subprocess (Claude Desktop / Claude Code / Zed)
    # "streamable-http" — remote HTTP server (containers, cloud deploys)
    #
    # NOTE: app.py also auto-selects HTTP when a platform injects DATABRICKS_APP_PORT
    # or PORT, so you usually do NOT need to set this on a cloud host.
    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "service": "airport"})

if __name__ == "__main__":

    settings = Settings()
    platform_port = os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT")

    if platform_port:
        mcp.run(transport="http", host="0.0.0.0", port=int(platform_port))
    elif settings.mcp_transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
    else:
        mcp.run(transport="stdio")


