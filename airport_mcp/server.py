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
from starlette.responses import JSONResponse, RedirectResponse


# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

FAA_NASR_URL = "https://www.faa.gov/air_traffic/flight_info/aeronav/Aero_Data/NASR_Subscription/"

# --- Configuration & Storage ---

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
        backend = StorageBackend.DATABRICKS if backend_str else StorageBackend(
            os.environ.get("AIRPORT_MCP_STORAGE_BACKEND", "local").lower()
        )
        
        if backend == StorageBackend.S3:
            return cls(
                backend=backend,
                s3_bucket=os.environ.get("AIRPORT_MCP_S3_BUCKET"),
                s3_key=os.environ.get("AIRPORT_MCP_S3_KEY", "airport_mcp/")
            )
        elif backend == StorageBackend.DATABRICKS:
            return cls(backend=backend, local_path=Path("/dbfs/mnt/airport_mcp_data"))
        
        return cls(backend=backend, local_path=Path.home() / ".airport_mcp_data")

class StorageManager:
    """Manages persistent connections and I/O for cached airport data."""
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
                logger.error(f"S3 Read Error: {e}")
                return b"", None
        else:
            if self.data_path.exists():
                timestamp_str = self.time_path.read_text().strip() if self.time_path.exists() else ""
                timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None
                return self.data_path.read_bytes(), timestamp
            return b"", None

# --- Data Models (Agent-Facing) ---

class Runway(BaseModel):
    rwy_id: Optional[str] = Field(None, alias="RWY_ID", description="Runway identifier (e.g., '09/27', '18L/36R').")
    length_ft: Optional[float] = Field(None, alias="RWY_LEN", description="Runway length in feet.")
    width_ft: Optional[float] = Field(None, alias="RWY_WIDTH", description="Runway width in feet.")
    surface: Optional[str] = Field(None, alias="SURFACE_TYPE_CODE", description="Surface material code (e.g., ASPH, CONC).")
    condition: Optional[str] = Field(None, alias="COND", description="Current surface condition.")
    latitude_1: Optional[str] = Field(None, alias="LAT1_DECIMAL", description="Latitude of the first runway threshold.")
    longitude_1: Optional[str] = Field(None, alias="LONG1_DECIMAL", description="Longitude of the first runway threshold.")
    latitude_2: Optional[str] = Field(None, alias="LAT2_DECIMAL", description="Latitude of the second runway threshold.")
    longitude_2: Optional[str] = Field(None, alias="LONG2_DECIMAL", description="Longitude of the second runway threshold.")
    lights: Optional[str] = Field(None, alias="RWY_LGT_CODE", description="Runway lighting system code.")

class AirportInfo(BaseModel):
    icao_id: Optional[str] = Field(None, description="The 3 or 4 letter ICAO or FAA identifier.")
    name: Optional[str] = Field(None, description="Official name of the airport.")
    city: Optional[str] = Field(None, description="City where the airport is located.")
    state: Optional[str] = Field(None, description="State code.")
    country: Optional[str] = Field(None, description="Country code.")
    runways: List[Runway] = Field(default_factory=list, description="List of all runways available at this airport.")

# --- Data Service ---

class AirportDataService:
    """Encapsulates data ingestion, caching, and querying logic."""
    def __init__(self, storage_manager: StorageManager):
        self.storage = storage_manager
        self.df: Optional[pd.DataFrame] = None
        self.last_download: Optional[datetime] = None

    def _get_subscription_date(self) -> datetime:
        try:
            response = requests.get(FAA_NASR_URL, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            dates = []
            for element in soup.find_all(string=True):
                if "Subscription effective" in element:
                    date_str = element.replace("Subscription effective", "").strip()
                    try:
                        dates.append(datetime.strptime(date_str, "%B %d, %Y"))
                    except ValueError:
                        continue
                        
            if not dates:
                logger.warning("Could not parse subscription dates. Defaulting to current date.")
                return datetime.now()
                
            now = datetime.now()
            past_dates = [d for d in dates if d <= now]
            return max(past_dates) if past_dates else min(dates)
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch FAA subscription page: {e}")
            raise

    def _download_and_extract(self) -> tuple[pd.DataFrame, datetime]:
        sub_date = self._get_subscription_date()
        formatted_date = sub_date.strftime("%d_%b_%Y")
        zip_url = f"https://nfdc.faa.gov/webContent/28DaySub/extra/{formatted_date}_APT_CSV.zip"
        
        logger.info(f"Downloading FAA dataset from {zip_url}")
        response = requests.get(zip_url, timeout=120)
        response.raise_for_status()
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            csv_files = [f for f in zf.namelist() if f.endswith(".csv")]
            apt_rwy = next((f for f in csv_files if "APT_RWY" in f), csv_files[0] if csv_files else None)
            
            if not apt_rwy:
                raise ValueError("Target CSV not found in FAA zip archive.")
            
            csv_content = zf.read(apt_rwy)
            return pd.read_csv(io.BytesIO(csv_content), dtype=str), sub_date

    def initialize(self) -> None:
        parquet_data, ts = self.storage.load()
        needs_download = not parquet_data or ts is None or (datetime.now() - ts).days > 28
        
        if needs_download:
            try:
                raw_df, ts = self._download_and_extract()
                min_non_na = len(raw_df) / 2
                clean_df = raw_df.dropna(axis=1, thresh=min_non_na)
                
                if "ARPT_ID" in clean_df.columns:
                    clean_df["ARPT_ID"] = clean_df["ARPT_ID"].str.upper()
                    clean_df = clean_df.set_index("ARPT_ID")
                    
                self.storage.save(clean_df.to_parquet(), ts)
                self.df = clean_df
                self.last_download = ts
            except Exception as e:
                logger.error(f"Data initialization failed: {e}. Attempting to use stale cache.")
                if parquet_data:
                    self.df = pd.read_parquet(io.BytesIO(parquet_data))
                    self.last_download = ts
                else:
                    raise
        else:
            self.df = pd.read_parquet(io.BytesIO(parquet_data))
            self.last_download = ts
            
        logger.info(f"Airport Data Service initialized. Cache date: {self.last_download}")

    def query(self, ident: str) -> dict[str, Any] | None:
        # Re-initialize if data is missing or older than 28 days
        if self.df is None or self.last_download is None or (datetime.now() - self.last_download).days > 28:
            logger.info("Dataset is missing or expired. Refreshing data...")
            self.initialize()
            
        ident_upper = ident.upper()
        norm_ident = ident_upper[1:] if ident_upper.startswith("K") and len(ident_upper) == 4 else ident_upper
        
        lookup_id = norm_ident if norm_ident in self.df.index else ident_upper
        if lookup_id not in self.df.index:
            return None
            
        airport_data = self.df.loc[[lookup_id]].copy()
        airport_data[["RWY_LEN", "RWY_WIDTH"]] = airport_data[["RWY_LEN", "RWY_WIDTH"]].apply(pd.to_numeric, errors="coerce")
        
        records = airport_data.to_dict(orient="records")
        runways = [
            Runway(**{k: (None if pd.isna(v) else v) for k, v in record.items()})
            for record in records
        ]
        
        first_row = airport_data.iloc[0]
        info = AirportInfo(
            icao_id=lookup_id,
            name=first_row.get("ARPT_NAME"),
            city=first_row.get("CITY"),
            state=first_row.get("STATE_CODE"),
            country=first_row.get("COUNTRY_CODE"),
            runways=runways
        )
        return info.model_dump(exclude_none=True)
      

# --- MCP Application ---

mcp = FastMCP("Airport MCP Server")
data_service = AirportDataService(StorageManager(StorageConfig.from_env()))

@mcp.tool()
def get_airport_runways(icao_or_faa_id: str) -> str:
    """
    Retrieve comprehensive runway and structural information for a specific US airport.
    
    Use this tool when you need to know the physical layout of an airport, including 
    the number of runways, their lengths, widths, and surface types (e.g., Asphalt, Concrete).
    
    Args:
        icao_or_faa_id: The 3-letter FAA identifier (e.g., 'JFK', 'ORD') or 4-letter 
                        ICAO identifier (e.g., 'KJFK', 'KORD') of the target airport.
    """
    try:
        result = data_service.query(icao_or_faa_id)
        if result is None:
            return json.dumps({"error": f"Airport identifier '{icao_or_faa_id}' not found in the current FAA dataset."}, indent=2)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Query execution failed for {icao_or_faa_id}: {e}")
        return json.dumps({"error": "Internal server error occurred while retrieving airport data."}, indent=2)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    is_ready = data_service.df is not None
    return JSONResponse({
        "status": "healthy" if is_ready else "initializing", 
        "service": "airport_mcp",
        "cache_timestamp": data_service.last_download.isoformat() if data_service.last_download else None
    })

@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> RedirectResponse:
    return RedirectResponse(url="/health")

if __name__ == "__main__":
    settings = Settings()
    platform_port = os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT")

    try:
        data_service.initialize()
    except Exception as e:
        logger.critical(f"Fatal initialization failure: {e}")

    if platform_port:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=int(platform_port))
    elif settings.mcp_transport == "streamable-http":
        mcp.run(transport="streamable-http", host=settings.mcp_host, port=settings.mcp_port)
    elif settings.mcp_transport == "sse":
        mcp.run(transport="sse", host=settings.mcp_host, port=settings.mcp_port)
    else:
        mcp.run(transport="stdio")
        
