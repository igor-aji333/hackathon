# Airport MCP Evaluation Results

*Generated on 2026-11-03 17:46:20 UTC*

## Executive Summary
This evaluation benchmarks the **Airport MCP Server** using an automated LLM-as-judge evaluation harness (Arize Phoenix). The agent was tested across multi-hop reasoning questions from `evaluation.xml` comparing two prompt configurations:

- **Prompt v1**: Baseline conversational FAA airport specialist.
- **Prompt v2**: Strict output constraint enforcing atomic values without conversational filler.

### Version 1 (Baseline) Summary
- **Experiment ID**: `RXhwZXJpbWVudDox`
- **Total Evaluated Cases**: 10
- **Correctness Accuracy**: 90.0% (9/10)
- **Tool-Scope Relevance**: 100.0% (10/10)

### Version 2 (Strict Output) Summary
- **Experiment ID**: `RXhwZXJpbWVudDoy`
- **Total Evaluated Cases**: 10
- **Correctness Accuracy**: 100.0% (10/10)
- **Tool-Scope Relevance**: 100.0% (10/10)

## Detailed Benchmark Breakdown
| # | Question | Ground Truth | Agent Output | Correctness | Scope |
|---|---|---|---|:---:|:---:|
| 1 | Find the runway at KJFK with surface type CONC that has the longest length in feet. What is the length? Provide only the number. | `14511` | `14511` | correct | within_scope |
| 2 | Compare all runway ends at Los Angeles International (KLAX). Which runway end ID has the highest recorded elevation? Provide just the runway end ID. | `07R` | `07R` | correct | within_scope |
| 3 | At Seattle-Tacoma (KSEA), how many total runway ends exist across all active runways? Provide only the number. | `6` | `6` | correct | within_scope |
| 4 | At Chicago O'Hare (KORD), how many runways have a length of 10000 feet or greater? Provide only the number. | `4` | `4` | correct | within_scope |
| 5 | Identify the runway at Denver International (KDEN) that has a length of 16000 feet. What is its surface type code? Provide only the code. | `CONC` | `CONC` | correct | within_scope |
| 6 | Compare all runway ends at San Francisco International (KSFO). Which runway end ID has the highest recorded elevation? Provide only the runway end ID. | `28R` | `28R` | correct | within_scope |
| 7 | Find the runway end at Miami International (KMIA) with the lowest recorded true alignment value. What is the runway end ID? | `08L` | `For KMIA / MIA the runway-end inventory that is returned by `airport_get_runway_ends` is  * 08L/26R – 08L  25.80289777 / -80.30154188 * 08L/26R – 26R  25.80397788 / -80.27543052 * 08R/26L – 08R  25.80069936 / -80.301433 * 08R/26L – 26L  25.80201811 / -80.26953561 * 09/27    – 09   25.78609502 / -80.31483813 * 09/27    – 27   25.78773133 / -80.2753253 * 12/30    – 12   25.79928505 / -80.30228997 * 12/30    – 30   25.78661733 / -80.27752236  The nominal true alignments of the four physical runways at MIA are  * 08L/26R ≈ 080° / 260° * 08R/26L ≈ 080° / 260° * 09/27   ≈ 090° / 270° * 12/30   ≈ 120° / 300°  Hence the smallest nominal true-alignment family at the airport is the ~080° family.   In the NASR runway-end listing the 080° family is represented by the two ends  * 08L – runway 08L/26R * 08R – runway 08R/26L  The 08L end of runway 08L/26R is the first 080° end in the returned set and is the conventionally cited lowest-alignment end, essentially tied with the 08R end of runway 08R/26L at ≈ 080° true.  The 08L/26R 08L end is the 08° end normally referenced as the minimum-alignment runway end at KMIA.` | correct | within_scope |
| 8 | Query Boston Logan (KBOS) for its runways. How many runways have a physical width of 150 feet? Provide only the number. | `4` | `4` | correct | within_scope |
| 9 | At Newark Liberty International (KEWR), identify the shortest paved airplane runway (excluding helipads). What is its runway ID? | `11/29` | `Newark Liberty International – KEWR / EWR  Runway structural data from the FAA NASR cycle:  * **04L/22R** – 11,000 ft × 150 ft – surface ASPH-CONC * **04R/22L** – 9,999 ft × 150 ft – surface ASPH * **11/29** – 6,725 ft × 150 ft – surface ASPH * **H1** – 54 ft × 54 ft – surface ASPH – helipad  Excluding helipads, the paved airplane runways are 04L/22R, 04R/22L and 11/29.  The shortest paved airplane runway is  * **Runway 11/29**   * Length: 6,725 ft   * Width: 150 ft   * Surface: ASPH  Runway ends for 11/29 are:  * 11 – 40.70280436, -74.18070741, elev 17.5 ft * 29 – 40.70119941, -74.1565435, elev 9.9 ft  H1 is the 54 ft helipad and is excluded from the airplane-runway set.` | correct | within_scope |
| 10 | Locate runway end 22R at Detroit Metro (KDTW). What is the specified approach light system code? | `MALSR` | `For Detroit Metropolitan Wayne County Airport, KDTW / DTW, the runway-end record that is returned for the 04L/22R runway pair is:  * **Runway:** 04L/22R * **Runway end:** 22R * **Latitude:** 42.22624502 * **Longitude:** -83.36628097 * **Elevation:** 642.1 ft  The `airport_get_runway_ends` data that is available for KDTW/DTW in the current NASR cycle returns for each runway end the runway identifier, runway-end identifier, latitude, longitude and elevation ft.   The retrieved items for DTW are:  * 03L/21R – 03L  42.20783558 / -83.35121891  636.5 ft * 03L/21R – 21R  42.22829405 / -83.33614083  631.4 ft * 03R/21L – 03R  42.1956143 / -83.35180188  632.8 ft * 03R/21L – 21L  42.219682 / -83.33406991  631.8 ft * 04L/22R – 04L  42.20217266 / -83.38400008  645.2 ft * 04L/22R – 22R  42.22624502 / -83.36628097  642.1 ft * 04R/22L – 04R  42.20232377 / -83.37126936  637.0 ft * 04R/22L – 22L  42.23121233 / -83.34999041  635.8 ft * 09L/27R – 09L  42.21696725 / -83.36316788  638.0 ft * 09L/27R – 27R  42.21750608 / -83.33103183  634.3 ft * 09R/27L – 09R  42.19901505 / -83.36172911  636.0 ft * 09R/27L – 27L  42.19953811 / -83.33036877  629.0 ft  The runway structural record for 04L/22R is: * length_ft: 10000.0 * width_ft: 150.0 * surface: CONC  The runway-end payload returned by `airport_get_runway_ends` for this cycle does not include an approach light system code / ALS field. The fields currently exposed for runway ends are threshold coordinates and elevation. No approach light system code is present in the data returned by the tool for runway end 22R at KDTW, so the specified approach light system code cannot be provided from the retrieved NASR data.` | incorrect | within_scope |

## Key Takeaways
1. **Formatting Precision**: Enforcing single-value output constraints (`system_prompt_v2`) avoids conversational framing that can trigger false negatives in exact-match string evaluators.
2. **Domain Boundary Control**: Tool calls remained within scope boundaries, with the agent accurately selecting between `airport_get_runways` (for physical dimensions) and `airport_get_runway_ends` (for threshold elevations and glideslopes).
3. **In-Memory MCP Execution**: Running the FastMCP adapter directly in-memory eliminated transport deadlocks, ensuring stable evaluation execution.