import io
import logging
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import httpx
import pandas as pd
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# --- URL Configurations ---
FAA_NASR_SUBSCRIPTION_URL = "https://www.faa.gov/air_traffic/flight_info/aeronav/Aero_Data/NASR_Subscription/"
FAA_NASR_ARCHIVE_BASE_URL = "https://nfdc.faa.gov/webContent/28DaySub/extra/"

# --- Filename Configurations ---
TIMESTAMP_FILENAME = "nasr_cycle_timestamp.txt"
ARCHIVE_PREFIX = "FAA_NASR_"
ARCHIVE_SUFFIX = ".zip"
PARQUET_SUFFIX = ".parquet"
CSV_SUFFIX = ".csv"

# --- Storage & Cache Configurations ---
DEFAULT_S3_PREFIX = "airport_mcp/"
DEFAULT_DATABRICKS_PATH = "/Volumes/users/igor_v_filippov/airport_mcp_data"
DEFAULT_LOCAL_DIR_NAME = ".airport_mcp_data"
CACHE_EXPIRATION_DAYS = 28

class StorageBackend(Enum):
    LOCAL = "local"
    S3 = "s3"
    DATABRICKS = "databricks"

@dataclass
class StorageConfig:
    backend: StorageBackend
    local_path: Optional[Path] = None
    s3_bucket: Optional[str] = None
    s3_prefix: Optional[str] = None
    
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
                s3_prefix=os.environ.get("AIRPORT_MCP_S3_KEY", DEFAULT_S3_PREFIX)
            )
        elif backend == StorageBackend.DATABRICKS:
            return cls(backend=backend, local_path=Path(DEFAULT_DATABRICKS_PATH))
            
        return cls(backend=backend, local_path=Path.home() / DEFAULT_LOCAL_DIR_NAME)

class StorageManager:
    """Manages persistent connections and dynamic I/O for cached data and archives."""
    def __init__(self, config: StorageConfig):
        self.config = config
        self._s3_client = None
        
        if self.config.backend in (StorageBackend.LOCAL, StorageBackend.DATABRICKS):
            self.base_dir = self.config.local_path
            self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def s3(self):
        if self._s3_client is None:
            import boto3
            self._s3_client = boto3.client('s3')
        return self._s3_client

    def save_archive(self, archive_name: str, archive_bytes: bytes) -> None:
        if self.config.backend == StorageBackend.S3:
            self.s3.put_object(Bucket=self.config.s3_bucket, Key=f"{self.config.s3_prefix}{archive_name}", Body=archive_bytes)
        else:
            (self.base_dir / archive_name).write_bytes(archive_bytes)

    def load_archive(self, archive_name: str) -> Optional[bytes]:
        if self.config.backend == StorageBackend.S3:
            try:
                obj = self.s3.get_object(Bucket=self.config.s3_bucket, Key=f"{self.config.s3_prefix}{archive_name}")
                return obj['Body'].read()
            except Exception:
                return None
        else:
            path = self.base_dir / archive_name
            return path.read_bytes() if path.exists() else None

    def save_cycle_timestamp(self, timestamp: datetime) -> None:
        """Saves a single timestamp that applies to the entire downloaded cycle archive."""
        if self.config.backend == StorageBackend.S3:
            self.s3.put_object(Bucket=self.config.s3_bucket, Key=f"{self.config.s3_prefix}{TIMESTAMP_FILENAME}", Body=timestamp.isoformat().encode())
        else:
            (self.base_dir / TIMESTAMP_FILENAME).write_text(timestamp.isoformat())

    def load_cycle_timestamp(self) -> Optional[datetime]:
        """Loads the global cycle timestamp."""
        if self.config.backend == StorageBackend.S3:
            if not self.config.s3_bucket:
                return None
            try:
                time_obj = self.s3.get_object(Bucket=self.config.s3_bucket, Key=f"{self.config.s3_prefix}{TIMESTAMP_FILENAME}")
                return datetime.fromisoformat(time_obj['Body'].read().decode().strip())
            except Exception:
                return None
        else:
            time_path = self.base_dir / TIMESTAMP_FILENAME
            if time_path.exists():
                timestamp_str = time_path.read_text().strip()
                return datetime.fromisoformat(timestamp_str) if timestamp_str else None
            return None

    def save_parquet(self, dataset_name: str, parquet_bytes: bytes) -> None:
        if self.config.backend == StorageBackend.S3:
            self.s3.put_object(Bucket=self.config.s3_bucket, Key=f"{self.config.s3_prefix}{dataset_name}{PARQUET_SUFFIX}", Body=parquet_bytes)
        else:
            (self.base_dir / f"{dataset_name}{PARQUET_SUFFIX}").write_bytes(parquet_bytes)

    def load_parquet(self, dataset_name: str) -> Optional[bytes]:
        if self.config.backend == StorageBackend.S3:
            if not self.config.s3_bucket:
                return None
            try:
                parquet_obj = self.s3.get_object(Bucket=self.config.s3_bucket, Key=f"{self.config.s3_prefix}{dataset_name}{PARQUET_SUFFIX}")
                return parquet_obj['Body'].read()
            except Exception:
                return None
        else:
            data_path = self.base_dir / f"{dataset_name}{PARQUET_SUFFIX}"
            return data_path.read_bytes() if data_path.exists() else None

class FAADataService:
    def __init__(self, storage_manager: StorageManager, target_csv_name: str):
        self.storage = storage_manager
        self.target_csv_name = target_csv_name
        self.df: Optional[pd.DataFrame] = None
        self.last_download: Optional[datetime] = None

    def _validate_url(self, url: str, expected_prefix: str) -> None:
        """Prevent SSRF and hostname confusion by strictly validating origins."""
        if not url.startswith(expected_prefix):
            raise ValueError(f"Security Policy Violation: URL {url} does not match allowed origin {expected_prefix}")

    async def _get_subscription_date(self) -> datetime:
        self._validate_url(FAA_NASR_SUBSCRIPTION_URL, "https://www.faa.gov/")
        
        try:
            # Using httpx with follow_redirects=False for strict security
            async with httpx.AsyncClient(follow_redirects=False) as client:
                response = await client.get(FAA_NASR_SUBSCRIPTION_URL, timeout=15.0)
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
                return datetime.now()
                
            past_dates = [d for d in dates if d <= datetime.now()]
            return max(past_dates) if past_dates else min(dates)
            
        except httpx.RequestError as e:
            logger.error(f"Failed to fetch FAA subscription page: {e}")
            raise

    async def _get_or_download_archive(self, sub_date: datetime) -> bytes:
        formatted_date = sub_date.strftime("%d_%b_%Y")
        archive_name = f"FAA_NASR_{formatted_date}.zip"
        
        archive_bytes = self.storage.load_archive(archive_name)
        if archive_bytes:
            return archive_bytes
            
        zip_url = f"{FAA_NASR_ARCHIVE_BASE_URL}{formatted_date}_APT_CSV.zip"
        self._validate_url(zip_url, FAA_NASR_ARCHIVE_BASE_URL)
        
        logger.info(f"Downloading new FAA archive from {zip_url}")
        
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.get(zip_url, timeout=120.0)
            response.raise_for_status()
            
        self.storage.save_archive(archive_name, response.content)
        return response.content

    async def _extract_target_csv(self, sub_date: datetime) -> pd.DataFrame:
        archive_bytes = await self._get_or_download_archive(sub_date)
        
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            csv_files = [f for f in zf.namelist() if f.endswith(".csv")]
            target_file = next((f for f in csv_files if self.target_csv_name in f), None)
            
            if not target_file:
                raise ValueError(f"Target CSV '{self.target_csv_name}' not found.")
                
            csv_content = zf.read(target_file)
            return pd.read_csv(io.BytesIO(csv_content), dtype=str)

    async def initialize(self, force_refresh: bool = False) -> None:
        cached_ts = self.storage.load_cycle_timestamp()
        parquet_data = self.storage.load_parquet(self.target_csv_name)
        
        is_cache_expired = cached_ts is None or (datetime.now() - cached_ts).days >= CACHE_EXPIRATION_DAYS
        needs_download = force_refresh or not parquet_data or is_cache_expired
        
        if needs_download:
            try:
                sub_date = await self._get_subscription_date()
                if not force_refresh and cached_ts and cached_ts >= sub_date and parquet_data:
                    self.df = pd.read_parquet(io.BytesIO(parquet_data))
                    self.last_download = cached_ts
                else:
                    raw_df = await self._extract_target_csv(sub_date)
                    self.storage.save_parquet(self.target_csv_name, raw_df.to_parquet())
                    self.storage.save_cycle_timestamp(sub_date)
                    self.df = raw_df
                    self.last_download = sub_date
            except Exception as e:
                logger.error(f"Data initialization failed: {e}. Attempting to use stale cache.")
                if parquet_data:
                    self.df = pd.read_parquet(io.BytesIO(parquet_data))
                    self.last_download = cached_ts or datetime.now()
                else:
                    raise
        else:
            self.df = pd.read_parquet(io.BytesIO(parquet_data))
            self.last_download = cached_ts
