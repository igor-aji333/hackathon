# Usage Instructions

## Available Tool

### `get_airport_runways(icao_or_faa_id)`

Query an airport by ICAO or FAA identifier to get runway information.

**Parameters:**
- `icao_or_faa_id` (string): The airport identifier (e.g., 'JFK', 'KLAX', 'KJFK', 'LAX')

**Returns:**
JSON object containing:
- `icao_id`: Airport identifier
- `name`: Airport name
- `city`: City location
- `state`: State code
- `country`: Country code
- `runways`: Array of runway objects with:
  - `rwy_id`: Runway identifier
  - `length_ft`: Runway length in feet
  - `width_ft`: Runway width in feet
  - `surface`: Surface type code
  - `condition`: Condition code
  - `latitude_1`, `longitude_1`: First coordinate pair
  - `latitude_2`, `longitude_2`: Second coordinate pair
  - `lights`: Lighting code

## Examples

### Query JFK Airport Runways
```json
{
  "tool": "get_airport_runways",
  "parameters": {
    "icao_or_faa_id": "JFK"
  }
}
```

### Query Los Angeles International Airport
```json
{
  "tool": "get_airport_runways",
  "parameters": {
    "icao_or_faa_id": "KLAX"
  }
}
```

## Sample Response
```json
{
  "icao_id": "JFK",
  "name": "JOHN F. KENNEDY INTERNATIONAL AP",
  "city": "JAMAICA",
  "state": "NY",
  "country": "US",
  "runways": [
    {
      "rwy_id": "04L/22R",
      "length_ft": 14000,
      "width_ft": 150,
      "surface": "CONC",
      "condition": "STD",
      "latitude_1": 40.641389,
      "longitude_1": -73.778056,
      "latitude_2": 40.631389,
      "longitude_2": -73.768056,
      "lights": "RWY"
    }
  ]
}
```

## Error Handling

If airport is not found:
```json
{
  "error": "Airport 'XXX' not found"
}
```