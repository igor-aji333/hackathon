import io
import json
import logging
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Dict, List

import pandas as pd
import requests
from bs4 import BeautifulSoup
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global cache for the dataset
_CACHED_DF: Optional[pd.DataFrame] = None
_LAST_DOWNLOAD_TIME: Optional[datetime] = None

mcp = FastMCP("Airport MCP Server")

FAA_NASR_URL = "https://www.faa.gov/air_traffic/flight_info/aeronav/Aero_Data/NASR_Subscription/"

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
        backend_str = os.environ.get("DATABRICKS_RUNTIME_VERSION") 
        if backend_str:
            backend = StorageBackend.DATABRICKS
        else:
            backend = StorageBackend(os.environ.get("AIRPORT_MCP_STORAGE_BACKEND", "local").lower())
        
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

class StorageManager:
    """Manages data persistence with persistent connections and dependency injection."""
    def __init__(self, config: StorageConfig):
        self.config = config
        self._s3_client = None
        
        if self.config.backend in (StorageBackend.LOCAL, StorageBackend.DATABRICKS):
            self.base_dir = self.config.local_path
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self.data_path = self.base_dir / "apt_rwy.parquet"
            self.time_path = self.base_dir / "download_time.txt"

    @property
    def s3(self):
        if self._s3_client is None:
            import boto3
            self._s3_client = boto3.client('s3')
        return self._s3_client

    def save(self, parquet_bytes: bytes, timestamp: datetime) -> None:
        if self.config.backend == StorageBackend.S3:
            if not self.config.s3_bucket:
                raise ValueError("S3 bucket not configured.")
            self.s3.put_object(Bucket=self.config.s3_bucket, Key=f"{self.config.s3_key}apt_rwy.parquet", Body=parquet_bytes)
            self.s3.put_object(Bucket=self.config.s3_bucket, Key=f"{self.config.s3_key}download_time.txt", Body=timestamp.isoformat().encode())
        else:
            self.data_path.write_bytes(parquet_bytes)
            self.time_path.write_text(timestamp.isoformat())

    def load(self) -> tuple[bytes, Optional[datetime]]:
        if self.config.backend == StorageBackend.S3:
            if not self.config.s3_bucket:
                return b"", None
            try:
                parquet_obj = self.s3.get_object(Bucket=self.config.s3_bucket, Key=f"{self.config.s3_key}apt_rwy.parquet")
                time_obj = self.s3.get_object(Bucket=self.config.s3_bucket, Key=f"{self.config.s3_key}download_time.txt")
                return parquet_obj['Body'].read(), datetime.fromisoformat(time_obj['Body'].read().decode().strip())
            except Exception as e:
                logger.error(f"Failed to read from S3: {e}")
                return b"", None
        else:
            if self.data_path.exists():
                timestamp_str = self.time_path.read_text().strip() if self.time_path.exists() else ""
                timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None
                return self.data_path.read_bytes(), timestamp
            return b"", None

storage = StorageManager(StorageConfig.from_env())

# --- Data Models ---

class Runway(BaseModel):
    rwy_id: Optional[str] = Field(None, alias="RWY_ID")
    length_ft: Optional[float] = Field(None, alias="RWY_LEN")
    width_ft: Optional[float] = Field(None, alias="RWY_WIDTH")
    surface: Optional[str] = Field(None, alias="SURFACE_TYPE_CODE")
    condition: Optional[str] = Field(None, alias="COND")
    latitude_1: Optional[str] = Field(None, alias="LAT1_DECIMAL")
    longitude_1: Optional[str] = Field(None, alias="LONG1_DECIMAL")
    latitude_2: Optional[str] = Field(None, alias="LAT2_DECIMAL")
    longitude_2: Optional[str] = Field(None, alias="LONG2_DECIMAL")
    lights: Optional[str] = Field(None, alias="RWY_LGT_CODE")

class AirportInfo(BaseModel):
    icao_id: Optional[str]
    name: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    runways: List[Runway]

# --- Core Logic ---

def get_subscription_date() -> datetime:
    """Robustly parse the subscription date using BeautifulSoup."""
    response = requests.get(FAA_NASR_URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Locate the Current section and find the date text
    for element in soup.find_all(string=True):
        if "Subscription effective" in element:
            date_str = element.replace("Subscription effective", "").strip()
            try:
                # E.g., parses "October 3, 2024"
                return datetime.strptime(date_str, "%B %d, %Y")
            except ValueError:
                continue
    raise ValueError("Could not find a valid subscription date on the FAA page.")

def get_current_subscription_url() -> str:
    """Constructs the FAA download URL using standard datetime formatting."""
    sub_date = get_subscription_date()
    formatted_date = sub_date.strftime("%d_%b_%Y") # e.g., 03_Oct_2024
    return f"https://nfdc.faa.gov/webContent/28DaySub/extra/{formatted_date}_APT_CSV.zip"

def download_and_extract_df() -> tuple[pd.DataFrame, datetime]:
    """Downloads zip, extracts CSV, and returns a DataFrame and timestamp."""
    zip_url = get_current_subscription_url()
    download_date = get_subscription_date() # Syncs with URL date
    
    response = requests.get(zip_url, timeout=300)
    response.raise_for_status()
    
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        csv_files = [f for f in zf.namelist() if f.endswith(".csv")]
        apt_rwy = next((f for f in csv_files if "APT_RWY" in f), csv_files[0] if csv_files else None)
        
        if not apt_rwy:
            raise ValueError("No CSV files found in zip archive")
        
        csv_content = zf.read(apt_rwy)
        df = pd.read_csv(io.BytesIO(csv_content), dtype=str)
        return df, download_date

def initialize_data() -> None:
    """Load or reload data into the global cache using Parquet and Pandas Indexing."""
    global _CACHED_DF, _LAST_DOWNLOAD_TIME
    
    parquet_data, ts = storage.load()
    
    needs_download = not parquet_data or ts is None or (datetime.now() - ts).days > 28
    
    if needs_download:
        logger.info("Downloading latest FAA dataset...")
        df, ts = download_and_extract_df()
        
        # Clean and optimize DataFrame
        min_non_na = len(df) / 2
        df = df.dropna(axis=1, thresh=min_non_na)
        
        # O(1) Indexing on Airport ID
        if "ARPT_ID" in df.columns:
            df["ARPT_ID"] = df["ARPT_ID"].str.upper()
            df.set_index("ARPT_ID", inplace=True)
            
        # Convert to Parquet for fast reads and compressed storage
        parquet_bytes = df.to_parquet()
        storage.save(parquet_bytes, ts)
    else:
        df = pd.read_parquet(io.BytesIO(parquet_data))
        
    _CACHED_DF = df
    _LAST_DOWNLOAD_TIME = ts
    logger.info(f"Data loaded into memory. Timestamp: {_LAST_DOWNLOAD_TIME}")

def load_data() -> pd.DataFrame:
    global _CACHED_DF, _LAST_DOWNLOAD_TIME
    if _CACHED_DF is None or _LAST_DOWNLOAD_TIME is None or (datetime.now() - _LAST_DOWNLOAD_TIME).days > 28:
        initialize_data()
    return _CACHED_DF

def normalize_airport_id(ident: str) -> str:
    ident_upper = ident.upper()
    return ident_upper[1:] if ident_upper.startswith("K") and len(ident_upper) == 4 else ident_upper

def query_airport(ident: str) -> dict[str, Any] | None:
    df = load_data()
    ident_upper = normalize_airport_id(ident)
    
    # O(1) Lookup using Pandas Index
    if ident_upper not in df.index:
        if ident.upper().startswith("K") and ident.upper() in df.index:
            ident_upper = ident.upper()
        else:
            return None
            
    # Handle both single row (Series) and multiple rows (DataFrame) returns from loc
    airport_data = df.loc[[ident_upper]] 
    first_row = airport_data.iloc[0]
    
    runways = []
    for _, row in airport_data.iterrows():
        # Clean numeric fields safely
        length = float(row.get("RWY_LEN")) if pd.notna(row.get("RWY_LEN")) else None
        width = float(row.get("RWY_WIDTH")) if pd.notna(row.get("RWY_WIDTH")) else None
        
        rwy_dict = row.to_dict()
        rwy_dict["RWY_LEN"] = length
        rwy_dict["RWY_WIDTH"] = width
        
        runways.append(Runway(**rwy_dict))
        
    info = AirportInfo(
        icao_id=ident_upper,
        name=first_row.get("ARPT_NAME"),
        city=first_row.get("CITY"),
        state=first_row.get("STATE_CODE"),
        country=first_row.get("COUNTRY_CODE"),
        runways=runways
    )
    
    return info.model_dump(exclude_none=True)

@mcp.tool()
def get_airport_runways(icao_or_faa_id: str) -> str:
    result = query_airport(icao_or_faa_id)
    if result is None:
        return json.dumps({"error": f"Airport '{icao_or_faa_id}' not found"}, indent=2)
    return json.dumps(result, indent=2)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "service": "airport"})

if __name__ == "__main__":
    settings = Settings()
    platform_port = os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT")

    try:
        initialize_data()
    except Exception as e:
        logger.error(f"Failed to initialize data on startup: {e}")

    if platform_port:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=int(platform_port))
    elif settings.mcp_transport == "streamable-http":
        mcp.run(transport="streamable-http", host=settings.mcp_host, port=settings.mcp_port)
    elif settings.mcp_transport == "sse":
        mcp.run(transport="sse", host=settings.mcp_host, port=settings.mcp_port)
    else:
        mcp.run(transport="stdio")
        
