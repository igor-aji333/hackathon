# Airport MCP – Agent Evaluation Results

*Generated 2026-11-10 21:44 UTC by `eval/phoenix/generate_results_md.py`.*

Agent model: `muse-glimmer:latest` · Judge model: `gemma4:31b` (different models to avoid self-preference bias).

An LLM agent (LangChain + in-memory MCP adapter) answers every question in
`eval/evaluation.xml` using only the server's tools. Each answer is scored by:

- **Exact match** (headline): normalized response equals the ground truth.
- **Contains answer**: ground truth appears as a whole token (separates formatting from reasoning failures).
- **Scope** (LLM judge): agent stayed within FAA airport-infrastructure data and did not invent out-of-scope facts.

## Summary

| Prompt | Experiment ID | Exact match | Contains answer | Scope | Task errors | Median latency |
|---|---|:---:|:---:|:---:|:---:|:---:|
| v1 | `RXhwZXJpbWVudDoz` | 94% (16/17) | 100% (17/17) | 100% (17/17) | 0 | 30.2s |
| v2 | `RXhwZXJpbWVudDo0` | 100% (17/17) | 100% (17/17) | 100% (17/17) | 0 | 28.4s |

## Per-question results

| # | Question | Expected | v1 output | v1 exact | v2 output | v2 exact |
|---|---|---|---|---|---|---|
| 1 | Find the runway at KJFK with surface type CONC that has the longest length in feet. What is the length? Provide only th… | `14511` | `14511` | ✅ | `14511` | ✅ |
| 2 | Compare all runway ends at Los Angeles International (KLAX). Which runway end ID has the highest recorded elevation? Pr… | `07R` | `07R` | ✅ | `07R` | ✅ |
| 3 | At Seattle-Tacoma (KSEA), how many total runway ends exist across all active runways? Provide only the number. | `6` | `6` | ✅ | `6` | ✅ |
| 4 | At Chicago O'Hare (KORD), how many runways have a length of 10000 feet or greater? Provide only the number. | `4` | `4` | ✅ | `4` | ✅ |
| 5 | Identify the runway at Denver International (KDEN) that has a length of 16000 feet. What is its surface type code? Prov… | `CONC` | `CONC` | ✅ | `CONC` | ✅ |
| 6 | Compare all runway ends at San Francisco International (KSFO). Which runway end ID has the highest recorded elevation? … | `28R` | `28R` | ✅ | `28R` | ✅ |
| 7 | Find the runway end at Miami International (KMIA) with the highest true alignment value. Provide only the runway end ID. | `30` | `30` | ✅ | `30` | ✅ |
| 8 | Query Boston Logan (KBOS) for its runways. How many runways have a physical width of 150 feet? Provide only the number. | `4` | `4` | ✅ | `4` | ✅ |
| 9 | At Newark Liberty International (KEWR), identify the shortest paved airplane runway (excluding helipads). Provide only … | `11/29` | `11/29` | ✅ | `11/29` | ✅ |
| 10 | Locate runway end 22R at Detroit Metro (KDTW). What is the specified approach light system code? Provide only the code. | `MALSR` | `MALSR` | ✅ | `MALSR` | ✅ |
| 11 | What is the ICAO code of Ted Stevens Anchorage International Airport? Provide only the code. | `PANC` | `PANC` | ✅ | `PANC` | ✅ |
| 12 | How many runways does PANC have? Provide only the number. | `3` | `3` | ✅ | `3` | ✅ |
| 13 | What is the FAA identifier of Hartsfield-Jackson Atlanta International Airport? Provide only the identifier. | `ATL` | `ATL` | ✅ | `ATL` | ✅ |
| 14 | A flight near Denver International (KDEN) needs to divert. What is the FAA identifier of the nearest public-use airport… | `CFO` | `CFO` | ✅ | `CFO` | ✅ |
| 15 | Within 40 nautical miles of San Francisco International (KSFO), which other airport is the closest one with a runway at… | `OAK` | `OAK` | ✅ | `OAK` | ✅ |
| 16 | How long is the longest runway at airport KZZQ? If the airport does not exist in the FAA data, answer NOT_FOUND. | `NOT_FOUND` | `NOT_FOUND The FAA NASR data cycle 2026-10-29 contains no US airport with identi…` | ❌ | `NOT_FOUND` | ✅ |
| 17 | What is the current weather (METAR) at KJFK? If your tools cannot provide it, answer UNAVAILABLE. | `UNAVAILABLE` | `UNAVAILABLE` | ✅ | `UNAVAILABLE` | ✅ |
