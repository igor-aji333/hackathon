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
            
            # 1. Drop columns with > 50% N/A
            min_non_na = len(df) / 2
            df = df.dropna(axis=1, thresh=min_non_na)

            # 2. Drop rows where all columns except 'ARPT_ID' and 'RWY_ID' are N/A
            cols_to_check = [c for c in df.columns if c not in ["ARPT_ID", "RWY_ID"]]
            if cols_to_check:
                df = df.dropna(axis=0, how='all', subset=cols_to_check)
            
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
        runways = []
        for record in records:
            # Convert NAs or empty strings to None
            r_dict = {k: (None if pd.isna(v) or str(v).strip() == "" else v) for k, v in record.items()}
            rwy = Runway(**r_dict)
            
            # Drop the runway entirely if all meaningful payload fields are empty (e.g. 19X)
            if not any([rwy.length_ft, rwy.width_ft, rwy.surface, rwy.condition, rwy.latitude_1, rwy.longitude_1, rwy.lights]):
                continue
            runways.append(rwy)
        
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

async def airport_get_runways(
    icao_or_faa_id: Annotated[str, Field(
        description="The 3-letter FAA identifier (e.g., 'JFK') or 4-letter ICAO identifier (e.g., 'KJFK') of the US airport",
        min_length=3,
        max_length=4,
        pattern=r"^[A-Za-z0-9]+$"
    )],
    limit: Annotated[int, Field(description="Maximum number of runways to return", ge=1)] = 20,
    offset: Annotated[int, Field(description="Pagination offset", ge=0)] = 0,
    response_format: Annotated[str, Field(description="Format of the response: 'json' or 'markdown'")] = "markdown"
) -> str:
    """
    Retrieve runway structural information for a specific US airport.
    """
    try:
        result = await airport_manager.query(icao_or_faa_id)
        if result is None:
            error_msg = f"Airport identifier '{icao_or_faa_id}' not found."
            if response_format == "json":
                return json.dumps({"isError": True, "error": error_msg})
            return f"**Error**: {error_msg}\nEnsure you are querying a valid US airport."

        runways = result.get("runways", [])
        total = len(runways)
        paginated_runways = runways[offset : offset + limit]
        count = len(paginated_runways)
        has_more = (offset + limit) < total
        next_offset = offset + limit if has_more else None

        if response_format == "json":
            response_data = {
                "total_count": total,
                "count": count,
                "offset": offset,
                "has_more": has_more,
                "next_offset": next_offset,
                "icao_id": result["icao_id"],
                "name": result.get("name"),
                "city": result.get("city"),
                "state": result.get("state"),
                "country": result.get("country"),
                "items": paginated_runways
            }
            # Strip None values so they don't appear as 'null' in JSON
            response_data = {k: v for k, v in response_data.items() if v is not None}
            return json.dumps(response_data, indent=2)       
        else:
            md = [f"# Runways for {result.get('name')} ({result['icao_id']})"]
            md.append(f"**Location:** {result.get('city')}, {result.get('state')}, {result.get('country')}\n")

            for r in paginated_runways:
                length = f"{r.get('length_ft')} ft" if r.get('length_ft') else "Unknown"
                width = f"{r.get('width_ft')} ft" if r.get('width_ft') else "Unknown"
                
                md.append(f"### Runway {r.get('rwy_id')}")
                md.append(f"- **Dimensions**: {length} x {width}")
                
                surf = r.get('surface')
                cond = r.get('condition')
                if surf or cond:
                    md.append(f"- **Surface**: {surf or 'Unknown'} (Condition: {cond or 'Unknown'})")
                
                lat = r.get('latitude_1')
                lon = r.get('longitude_1')
                if lat and lon:
                    md.append(f"- **Coordinates**: {lat}, {lon}")
                
                lights = r.get('lights')
                if lights:
                    md.append(f"- **Lights**: {lights}")
                    
                md.append("\n")                        
            
            md.append("---")
            md.append(f"*Showing {count} of {total} items. (Offset: {offset})*")
            if has_more:
                md.append(f"*Use `offset={next_offset}` to see more.*")
            
            return "\n".join(md)
            
    except Exception as e:
        logger.error(f"Runway query execution failed for {icao_or_faa_id}: {e}")
        if response_format == "json":
            return json.dumps({"isError": True, "error": "Internal server error occurred."})
        return "**Error**: Internal server error occurred."
    
