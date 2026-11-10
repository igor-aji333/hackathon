# Tool Reference

Every tool:

- returns structured JSON that matches a published `outputSchema` (also sent as text content for older clients)
- includes `data_cycle`, the effective date of the FAA NASR cycle that answered
- is annotated `readOnlyHint`, `idempotentHint`, and `openWorldHint: false`
- reports failures as MCP tool errors (`isError: true`). The message says what to do next.

Units: lengths and elevations are in **feet**, distances in **nautical miles**, and alignments and
bearings in **true degrees**.

---

## `airport_search`

Finds US airports by name, city, or code. Call it first when the user names an airport instead of
giving its code.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `query` | string (2–100 chars) | required | Name, city or code, e.g. `Boston Logan`, `O'Hare`, `KDEN`. Understands FAA abbreviations (International → INTL, Regional → RGNL, …). |
| `state` | string (2 letters) | – | Restrict to a state or territory, e.g. `TX`. |
| `include_all_facility_types` | bool | `false` | Also return heliports, seaplane bases, gliderports, etc. |
| `limit` | int 1–50 | `10` | |

Results are ranked in this order:

1. exact code match
2. operational
3. has an ICAO code
4. longest runway

```json
// airport_search {"query": "Anchorage International", "limit": 1}
{
  "data_cycle": "2026-10-29",
  "total_matches": 1,
  "airports": [{
    "faa_id": "ANC", "icao_id": "PANC", "name": "TED STEVENS ANCHORAGE INTL",
    "city": "ANCHORAGE", "state": "AK", "country": "US",
    "facility_type": "airport", "status": "operational", "public_use": true,
    "elevation_ft": 151.4, "latitude": 61.17408472, "longitude": -149.9981375,
    "runway_count": 3, "longest_runway_ft": 12400
  }]
}
```

No match is not an error. It returns `total_matches: 0`.

---

## `airport_get_runways`

Returns every runway at one airport, with both runway ends nested, in a single call.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `airport_id` | string | required | FAA (`JFK`, `1N7`) or ICAO (`KJFK`, `PANC`), case-insensitive. |
| `min_length_ft` | int ≥ 0 | – | Only runways at least this long. |
| `paved_only` | bool | `false` | Concrete, asphalt, partially paved or treated surfaces. |
| `include_helipads` | bool | `true` | Helipads have IDs `H1`, `H2`, … |

`total_runways` is always the count before filters are applied.

```json
// airport_get_runways {"airport_id": "KJFK", "min_length_ft": 14000}
{
  "data_cycle": "2026-10-29",
  "airport": {"faa_id": "JFK", "icao_id": "KJFK", "name": "JOHN F KENNEDY INTL", "city": "NEW YORK",
              "state": "NY", "elevation_ft": 13.0, "...": "..."},
  "total_runways": 4,
  "runways": [{
    "runway_id": "13R/31L", "length_ft": 14511, "width_ft": 200, "surface": "CONC",
    "is_paved": true, "is_helipad": false, "condition": "EXCELLENT", "edge_lighting": "HIGH", "has_ils": true,
    "ends": [
      {"end_id": "13R", "latitude": 40.64836133, "longitude": -73.81671472, "elevation_ft": 12.5,
       "touchdown_zone_elevation_ft": 12.6, "true_alignment_deg": 121, "ils_type": null,
       "approach_lighting": "RLLS", "visual_glide_slope_indicator": "P4L", "glide_path_angle_deg": 3.0,
       "displaced_threshold_ft": 2044, "takeoff_run_available_ft": 14511, "landing_distance_available_ft": 12467},
      {"end_id": "31L", "true_alignment_deg": 301, "ils_type": "ILS", "...": "..."}
    ]
  }]
}
```

---

## `airport_find_nearby`

Finds operational airports within a radius whose runways meet your requirements, nearest first. Use it
for diversion and alternate planning.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `airport_id` | string | – | Origin airport. Give this **or** `latitude` + `longitude`. |
| `latitude` / `longitude` | float | – | Origin coordinates in decimal degrees (west is negative). |
| `radius_nm` | float (0, 500] | `50` | |
| `min_runway_length_ft` | int ≥ 0 | – | |
| `paved_only` | bool | `false` | |
| `require_ils` | bool | `false` | ILS or LOC/GS approach on either end. |
| `public_use_only` | bool | `true` | |
| `limit` | int 1–50 | `10` | |

A single runway must meet every runway criterion. Helipads never qualify, and the origin airport is
excluded.

```json
// airport_find_nearby {"airport_id": "KDEN", "radius_nm": 50, "min_runway_length_ft": 8000,
//                      "paved_only": true, "require_ils": true, "limit": 2}
{
  "data_cycle": "2026-10-29",
  "origin_airport": {"faa_id": "DEN", "icao_id": "KDEN", "name": "DENVER INTL", "...": "..."},
  "origin_latitude": 39.86166666, "origin_longitude": -104.67316666, "radius_nm": 50.0,
  "total_found": 5,
  "airports": [
    {"faa_id": "CFO", "icao_id": "KCFO", "name": "COLORADO AIR AND SPACE PORT", "...": "...",
     "distance_nm": 7.8, "bearing_deg": 127, "qualifying_runways": ["08/26", "17/35"],
     "longest_qualifying_runway_ft": 8002},
    {"faa_id": "APA", "icao_id": "KAPA", "name": "CENTENNIAL", "...": "...",
     "distance_nm": 19.3, "bearing_deg": 205, "qualifying_runways": ["17L/35R"],
     "longest_qualifying_runway_ft": 10001}
  ]
}
```

---

## Errors

| Situation | Response (`isError: true`) |
|---|---|
| Unknown airport | `No US airport found with identifier 'KZZQ'. Check the code, or call airport_search with the airport's name or city to find it.` |
| Invalid argument (bad code format, negative length, latitude out of range, limit > 50, …) | Pydantic validation message naming the field. |
| `airport_find_nearby` without an origin | `Provide an origin airport identifier, or both latitude and longitude.` |
| FAA data not yet loadable (first start, offline, no cache) | `FAA airport data is temporarily unavailable (…). Retry in a few minutes.` |

Unexpected internal errors are masked (`mask_error_details`), so stack traces never reach the client.

## Code reference

| Field | Values |
|---|---|
| `surface` | `CONC` concrete, `ASPH` asphalt, `PEM` partially paved, `TURF`, `DIRT`, `GRVL` gravel, `WATER`, `MATS`, … Compound values such as `ASPH-CONC` are possible. |
| `condition` | `EXCELLENT`, `GOOD`, `FAIR`, `POOR`, `FAILED` |
| `edge_lighting` | `HIGH`, `MED`, `LOW`, `NSTD` (non-standard), `PERI` (perimeter), `FLD` (flood), `STRB` (strobe) |
| `approach_lighting` | e.g. `ALSF2`, `MALSR`, `MALSF`, `SSALR`, `ODALS`, `RLLS` |
| `visual_glide_slope_indicator` | e.g. `P4L` 4-box PAPI left, `P2R` 2-box PAPI right, `V4L` 4-box VASI left |
| `facility_type` | `airport`, `heliport`, `seaplane_base`, `ultralight`, `gliderport`, `balloonport` |
| `status` | `operational`, `closed_indefinitely`, `closed_permanently` |
