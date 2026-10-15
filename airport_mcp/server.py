import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from fastmcp import FastMCP

mcp = FastMCP("Airport MCP Server")

DATA_DIR = Path.home() / ".airport_mcp_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CSV_PATH = DATA_DIR / "apt_rwy.csv"
DOWNLOAD_TIME_PATH = DATA_DIR / "download_time.txt"
FAA_NASR_URL = "https://www.faa.gov/air_traffic/flight_info/aeronav/Aero_Data/NASR_Subscription/"

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}


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
    
    month_map = {
        "January": "Jan", "February": "Feb", "March": "Mar", "April": "Apr",
        "May": "May", "June": "Jun", "July": "Jul", "August": "Aug",
        "September": "Sep", "October": "Oct", "November": "Nov", "December": "Dec"
    }
    
    for full, short in month_map.items():
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


def extract_apt_rwy_from_zip(zip_url: str) -> None:
    """Download zip and extract APT_RWY.csv."""
    response = requests.get(zip_url, timeout=300)
    response.raise_for_status()
    
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        apt_rwy_files = [f for f in zf.namelist() if "APT_RWY" in f and f.endswith(".csv")]
        
        if apt_rwy_files:
            csv_content = zf.read(apt_rwy_files[0])
            CSV_PATH.write_bytes(csv_content)
        else:
            csv_files = [f for f in zf.namelist() if f.endswith(".csv")]
            if csv_files:
                csv_content = zf.read(csv_files[0])
                CSV_PATH.write_bytes(csv_content)


def download_csv() -> str:
    """Download the runway data from FAA zip archive."""
    zip_url = get_current_subscription_url()
    extract_apt_rwy_from_zip(zip_url)
    download_date = parse_zip_date(zip_url)
    DOWNLOAD_TIME_PATH.write_text(download_date.isoformat())
    return download_date.isoformat()


def needs_download() -> bool:
    """Check if CSV needs to be downloaded (every 28 days)."""
    if not CSV_PATH.exists():
        return True
    
    if not DOWNLOAD_TIME_PATH.exists():
        return False
    
    try:
        last_download = datetime.fromisoformat(DOWNLOAD_TIME_PATH.read_text().strip())
        return (datetime.now() - last_download).days > 28
    except Exception:
        return True


def load_data() -> pd.DataFrame:
    """Load runway data from CSV, downloading if needed."""
    if needs_download():
        download_csv()
    
    if not CSV_PATH.exists():
        download_csv()
    
    return pd.read_csv(CSV_PATH)


def query_airport(ident: str) -> dict[str, Any] | None:
    """Query airport by ICAO/FAA ID and return runway data."""
    df = load_data()
    ident_upper = ident.upper()
    
    airport_df = df[df["ARPT_ID"] == ident_upper]
    
    if airport_df.empty:
        try:
            airport_df = df[df["ARPT_ID"].str.upper() == ident_upper]
        except Exception:
            pass
    
    if airport_df.empty:
        return None
    
    first = airport_df.iloc[0]
    runways: list[dict[str, Any]] = []
    
    for _, row in airport_df.iterrows():
        runways.append({
            "rwy_id": row.get("RWY_ID"),
            "length_ft": int(row["RWY_LEN"]) if pd.notna(row.get("RWY_LEN")) else None,
            "width_ft": int(row["RWY_WIDTH"]) if pd.notna(row.get("RWY_WIDTH")) else None,
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