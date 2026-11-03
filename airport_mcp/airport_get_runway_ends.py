import json
import logging
from typing import Annotated, Any, List, Optional
import pandas as pd
from pydantic import BaseModel, Field

from .base_manager import BaseAirportManager

logger = logging.getLogger(__name__)


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


class AirportRunwayEndManager(BaseAirportManager):
    """Manager for querying runway end thresholds, alignments, and elevations."""

    def __init__(self):
        super().__init__(
            dataset_name="APT_RWY_END",
            key_columns=["ARPT_ID", "RWY_ID", "RWY_END_ID"],
        )

    async def query(self, ident: str) -> Optional[dict[str, Any]]:
        await self._prepare_data()
        lookup_id, airport_data = self._resolve_airport_records(ident)

        if airport_data is None or lookup_id is None:
            return None

        numeric_cols = ["RWY_END_ELEV", "VISUAL_GLIDE_PATH_ANGLE"]
        existing_num_cols = [col for col in numeric_cols if col in airport_data.columns]
        if existing_num_cols:
            airport_data[existing_num_cols] = airport_data[existing_num_cols].apply(
                pd.to_numeric, errors="coerce"
            )

        records = airport_data.to_dict(orient="records")
        runway_ends = []
        for record in records:
            r_dict = {
                k: (None if pd.isna(v) or str(v).strip() == "" else v)
                for k, v in record.items()
            }
            re = RunwayEnd(**r_dict)

            # Discard records missing threshold navigational values
            if not any([
                re.latitude,
                re.longitude,
                re.elevation_ft,
                re.true_alignment,
                re.ils_type,
                re.approach_light_system,
                re.visual_glide_path_angle,
            ]):
                continue
            runway_ends.append(re)

        first_row = airport_data.iloc[0]
        info = AirportRunwayEndInfo(
            icao_id=lookup_id,
            city=first_row.get("CITY"),
            state=first_row.get("STATE_CODE"),
            country=first_row.get("COUNTRY_CODE"),
            runway_ends=runway_ends,
        )
        return info.model_dump(exclude_none=True)


airport_runway_end_manager = AirportRunwayEndManager()


async def airport_get_runway_ends(
    icao_or_faa_id: Annotated[
        str,
        Field(
            description="The 3-letter FAA identifier (e.g., 'JFK') or 4-letter ICAO identifier (e.g., 'KJFK') of the target US airport.",
            min_length=3,
            max_length=4,
            pattern=r"^[A-Za-z0-9]+$",
        ),
    ],
    limit: Annotated[
        int, Field(description="Maximum number of runway ends to return", ge=1)
    ] = 20,
    offset: Annotated[
        int, Field(description="Pagination offset", ge=0)
    ] = 0,
    response_format: Annotated[
        str, Field(description="Format of the response: 'json' or 'markdown'")
    ] = "json",
) -> str:
    """Retrieve comprehensive runway end information for a specific US airport."""
    try:
        result = await airport_runway_end_manager.query(icao_or_faa_id)
        if result is None:
            error_msg = f"Airport identifier '{icao_or_faa_id}' not found."
            if response_format == "json":
                return json.dumps({"isError": True, "error": error_msg})
            return f"**Error**: {error_msg}\nEnsure you are querying a valid US airport."

        runway_ends = result.get("runway_ends", [])
        total = len(runway_ends)
        paginated_ends = runway_ends[offset : offset + limit]
        count = len(paginated_ends)
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
                "city": result.get("city"),
                "state": result.get("state"),
                "country": result.get("country"),
                "items": paginated_ends,
            }
            response_data = {k: v for k, v in response_data.items() if v is not None}
            return json.dumps(response_data, indent=2)
        else:
            md = [f"# Runway Ends for {result['icao_id']}"]
            md.append("")
            for re in paginated_ends:
                md.append(
                    f"### Runway End {re.get('rwy_end_id')} (Runway {re.get('rwy_id')})"
                )

                lat = re.get("latitude")
                lon = re.get("longitude")
                if lat and lon:
                    md.append(f"- **Latitude**: {lat}")
                    md.append(f"- **Longitude**: {lon}")

                elev = re.get("elevation_ft")
                if elev is not None:
                    md.append(f"- **Elevation**: {elev} ft")

                alignment = re.get("true_alignment")
                if alignment:
                    md.append(f"- **Alignment**: {alignment}")

                ils = re.get("ils_type")
                if ils:
                    md.append(f"- **ILS Type**: {ils}")

                angle = re.get("visual_glide_path_angle")
                if angle is not None:
                    md.append(f"- **Glide Path Angle**: {angle} degrees")

                als = re.get("approach_light_system")
                if als:
                    md.append(f"- **Approach Lights**: {als}")

                md.append("\n---")

            md.append(f"*Showing {count} of {total} items. (Offset: {offset})*")
            if has_more:
                md.append(f"*Use `offset={next_offset}` to see more.*")

            return "\n".join(md)

    except Exception as e:
        logger.error(f"Runway Ends query execution failed for {icao_or_faa_id}: {e}")
        if response_format == "json":
            return json.dumps({"isError": True, "error": "Internal server error occurred."})
        return "**Error**: Internal server error occurred."
