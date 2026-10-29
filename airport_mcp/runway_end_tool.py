import json
import logging
from datetime import datetime
from typing import Any, List, Optional

import pandas as pd
from pydantic import BaseModel, Field

from .faa_data_client import FAADataService, StorageConfig, StorageManager

logger = logging.getLogger(__name__)

# --- Data Models ---
class RunwayEnd(BaseModel):
    rwy_id: Optional[str] = Field(None, alias="RWY_ID")
    rwy_end_id: Optional[str] = Field(None, alias="RWY_END_ID")
    latitude: Optional[str] = Field(None, alias="LAT_DECIMAL")
    longitude: Optional[str] = Field(None, alias="LONG_DECIMAL")
    elevation_ft: Optional[float] = Field(None, alias="RWY_END_ELEV")
    true_alignment: Optional[str] = Field(None, alias="TRUE_ALIGNMENT")
    ils_type: Optional[str] = Field(None, alias="ILS_TYPE")
    approach_light_system: Optional[str] = Field(None, alias="APCH_LGT_SYSTEM_CODE")
    visual_glide_path_angle: Optional[float] = Field(None, alias="VISUAL_GLIDE_PATH_ANGLE")

class AirportRunwayEndInfo(BaseModel):
    icao_id: Optional[str] = Field(None)
    city: Optional[str] = Field(None)
    state: Optional[str] = Field(None)
    country: Optional[str] = Field(None)
    runway_ends: List[RunwayEnd] = Field(default_factory=list)

# --- Manager ---
class AirportRunwayEndManager:
    def __init__(self):
        storage = StorageManager(StorageConfig.from_env())
        self.client = FAADataService(storage, "APT_RWY_END")

    def _prepare_data(self):
        if self.client.df is None or self.client.last_download is None or (datetime.now() - self.client.last_download).days > 28:
            self.client.initialize()
            df = self.client.df
            
            min_non_na = len(df) / 2
            df = df.dropna(axis=1, thresh=min_non_na)
            if "ARPT_ID" in df.columns:
                df["ARPT_ID"] = df["ARPT_ID"].str.upper()
                self.client.df = df.set_index("ARPT_ID")

    def query(self, ident: str) -> dict[str, Any] | None:
        self._prepare_data()
        df = self.client.df
        
        ident_upper = ident.upper()
        norm_ident = ident_upper[1:] if ident_upper.startswith("K") and len(ident_upper) == 4 else ident_upper
        lookup_id = norm_ident if norm_ident in df.index else ident_upper
        
        if lookup_id not in df.index:
            return None
            
        airport_data = df.loc[[lookup_id]].copy()
        
        numeric_cols = ["RWY_END_ELEV", "VISUAL_GLIDE_PATH_ANGLE"]
        existing_num_cols = [col for col in numeric_cols if col in airport_data.columns]
        if existing_num_cols:
            airport_data[existing_num_cols] = airport_data[existing_num_cols].apply(pd.to_numeric, errors="coerce")
        
        records = airport_data.to_dict(orient="records")
        runway_ends = [
            RunwayEnd(**{k: (None if pd.isna(v) else v) for k, v in record.items()})
            for record in records
        ]
        
        first_row = airport_data.iloc[0]
        info = AirportRunwayEndInfo(
            icao_id=lookup_id,
            city=first_row.get("CITY"),
            state=first_row.get("STATE_CODE"),
            country=first_row.get("COUNTRY_CODE"),
            runway_ends=runway_ends
        )
        return info.model_dump(exclude_none=True)

# Shared Instance
airport_runway_end_manager = AirportRunwayEndManager()

# --- Tool Function ---
def get_airport_runway_ends(icao_or_faa_id: str) -> str:
    """
    Retrieve comprehensive runway end information (thresholds, elevations, alignments, glideslopes, etc.) for a specific US airport.
    
    Args:
        icao_or_faa_id: The 3-letter FAA identifier (e.g., 'JFK', 'ORD') or 4-letter
                        ICAO identifier (e.g., 'KJFK', 'KORD') of the target airport.
    """
    try:
        result = airport_runway_end_manager.query(icao_or_faa_id)
        if result is None:
            return json.dumps({"error": f"Airport identifier '{icao_or_faa_id}' not found."}, indent=2)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Runway Ends query execution failed for {icao_or_faa_id}: {e}")
        return json.dumps({"error": "Internal server error occurred while retrieving runway end data."}, indent=2)
    
