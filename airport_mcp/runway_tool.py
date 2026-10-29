import json
import logging
from datetime import datetime
from typing import Any, List, Optional, Annotated
import pandas as pd
from pydantic import BaseModel, Field
from .faa_data_client import FAADataService, StorageConfig, StorageManager, CACHE_EXPIRATION_DAYS

logger = logging.getLogger(__name__)

class Runway(BaseModel):
    rwy_id: Optional[str] = Field(None, alias="RWY_ID")
    length_ft: Optional[float] = Field(None, alias="RWY_LEN")
    width_ft: Optional[float] = Field(None, alias="RWY_WIDTH")
    surface: Optional[str] = Field(None, alias="SURFACE_TYPE_CODE")
    condition: Optional[str] = Field(None, alias="COND")
    latitude_1: Optional[str] = Field(None, alias="LAT1_DECIMAL")
    longitude_1: Optional[str] = Field(None, alias="LONG1_DECIMAL")
    lights: Optional[str] = Field(None, alias="RWY_LGT_CODE")

class AirportInfo(BaseModel):
    icao_id: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    city: Optional[str] = Field(None)
    state: Optional[str] = Field(None)
    country: Optional[str] = Field(None)
    runways: List[Runway] = Field(default_factory=list)

class AirportRunwayManager:
    def __init__(self):
        storage = StorageManager(StorageConfig.from_env())
        self.client = FAADataService(storage, "APT_RWY")

    async def _prepare_data(self):
        if self.client.df is None or self.client.last_download is None or (datetime.now() - self.client.last_download).days > CACHE_EXPIRATION_DAYS:
            await self.client.initialize()
            df = self.client.df
            
            min_non_na = len(df) / 2
            df = df.dropna(axis=1, thresh=min_non_na)
            if "ARPT_ID" in df.columns:
                df["ARPT_ID"] = df["ARPT_ID"].str.upper()
                self.client.df = df.set_index("ARPT_ID")

    async def query(self, ident: str) -> dict[str, Any] | None:
        await self._prepare_data()
        df = self.client.df
        
        ident_upper = ident.upper()
        norm_ident = ident_upper[1:] if ident_upper.startswith("K") and len(ident_upper) == 4 else ident_upper
        lookup_id = norm_ident if norm_ident in df.index else ident_upper
        
        if lookup_id not in df.index:
            return None
            
        airport_data = df.loc[[lookup_id]].copy()
        airport_data[["RWY_LEN", "RWY_WIDTH"]] = airport_data[["RWY_LEN", "RWY_WIDTH"]].apply(pd.to_numeric, errors="coerce")
        
        records = airport_data.to_dict(orient="records")
        runways = [Runway(**{k: (None if pd.isna(v) else v) for k, v in record.items()}) for record in records]
        
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

airport_manager = AirportRunwayManager()

async def get_airport_runways(
    icao_or_faa_id: Annotated[str, Field(
        description="The 3-letter FAA identifier (e.g., 'JFK') or 4-letter ICAO identifier (e.g., 'KJFK') of the US airport
