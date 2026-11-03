# Airport MCP Evaluation Results

*Generated on 2026-11-03 18:24:13 UTC*

## Executive Summary
This evaluation benchmarks the **Airport MCP Server** using an automated LLM-as-judge evaluation harness (Arize Phoenix). The agent was tested across multi-hop reasoning questions from `evaluation.xml` comparing two prompt configurations:

- **Prompt v1**: Baseline conversational FAA airport specialist.
- **Prompt v2**: Strict output constraint enforcing atomic values without conversational filler.

### Version 1 (Baseline) Summary
- **Experiment ID**: `RXhwZXJpbWVudDox`
- **Total Evaluated Cases**: 10
- **Correctness Accuracy**: 100.0% (10/10)
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
| 7 | Find the runway end at Miami International (KMIA) with the lowest recorded true alignment value. What is the runway end ID? | `08L` | `Miami International KMIA has 8 runway ends in the current NASR cycle.  The true_alignment values returned for the airport are:  * 08L – 08L/26R – true_alignment 87 * 26R – 08L/26R – true_alignment 267 * 08R – 08R/26L – true_alignment 87 * 26L – 08R/26L – true_alignment 267 * 09  – 09/27      – true_alignment 87 * 27  – 09/27      – true_alignment 267 * 12  – 12/30      – true_alignment 119 * 30  – 12/30      – true_alignment 299  The minimum true alignment recorded for KMIA is 87°.  That minimum is shared by three runway ends:  * rwy_end_id **08L** on rwy_id 08L/26R * rwy_end_id **08R** on rwy_id 08R/26L * rwy_end_id **09**  on rwy_id 09/27  The first occurrence in the returned set is 08L, true_alignment = 87°, lat 25.80289777 / lon -80.30154188, elevation 8.9 ft, ILS type LOC/DME.` | correct | within_scope |
| 8 | Query Boston Logan (KBOS) for its runways. How many runways have a physical width of 150 feet? Provide only the number. | `4` | `4` | correct | within_scope |
| 9 | At Newark Liberty International (KEWR), identify the shortest paved airplane runway (excluding helipads). What is its runway ID? | `11/29` | `Newark Liberty International KEWR has 3 paved airplane runways + 1 helipad in the NASR cycle:  * **04L/22R** – 11,000 ft × 150 ft – ASPH-CONC * **04R/22L** – 9,999 ft × 150 ft – ASPH * **11/29** – 6,725 ft × 150 ft – ASPH * **H1** – 54 ft × 54 ft – ASPH – helipad  Excluding helipads, the paved airplane runway with the smallest length is  **Runway 11/29, 6,725 ft long**  The 54 ft H1 is the shortest paved surface at the airport but it is a helipad and is excluded per your request.` | correct | within_scope |
| 10 | Locate runway end 22R at Detroit Metro (KDTW). What is the specified approach light system code? | `MALSR` | `Detroit Metropolitan Wayne County Airport – KDTW / DTW  Runway 04L/22R – Runway end 22R  * rwy_id: 04L/22R * rwy_end_id: 22R * latitude: 42.22624502 * longitude: -83.36628097 * elevation_ft: 642.1 * true_alignment: 209° * ils_type: ILS/DME * visual_glide_path_angle: 3.0° * approach_light_system: **MALSR**  The specified approach lighting for the 22R threshold is MALSR – Medium Intensity Approach Lighting System with Runway Alignment Indicator Lights.` | correct | within_scope |

## Key Takeaways
1. **Formatting Precision**: Enforcing single-value output constraints (`system_prompt_v2`) avoids conversational framing that can trigger false negatives in exact-match string evaluators.
2. **Domain Boundary Control**: Tool calls remained within scope boundaries, with the agent accurately selecting between `airport_get_runways` (for physical dimensions) and `airport_get_runway_ends` (for threshold elevations and glideslopes).
3. **In-Memory MCP Execution**: Running the FastMCP adapter directly in-memory eliminated transport deadlocks, ensuring stable evaluation execution.