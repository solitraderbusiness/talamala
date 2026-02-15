# Data Lineage — Institutional Money Flow Module

## Overview

```
                SPDR Gold Trust                    CFTC
                     │                               │
                     ▼                               ▼
               etf_scraper.py                  cot_parser.py
               (daily, 6h cycle)               (weekly, 6h cycle)
                     │                               │
                     ▼                               ▼
              etf_holdings table               cot_data table
              (source_url saved)               (source_url saved)
                     │                               │
                     └───────────┬───────────────────┘
                                 │
                                 ▼
                     money_flow_service.py
                     (queries last 2-3 years)
                                 │
                                 ▼
                     derived_money_flow.py
                     (pure math, no DB)
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
         z-score 90d       percentiles        combined signal
         (ETF changes)     (ETF 2yr,          (rule-based
                           COT 1yr/3yr)        classification)
              │                  │                   │
              └──────────────────┼───────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              API response    Chat tools   Live snapshot
              /money-flow     get_metric   get_live_snapshot
```

## ETF Pipeline

### Source
- **URL:** `https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv`
- **Type:** CSV file with full history since November 2004
- **Frequency:** Updated daily by the analysis worker (every 6 hours)
- **Saved as:** `source_url` column in `etf_holdings` table

### Processing Steps
1. **Download** — `_download_spdr_csv()` fetches the full archive CSV
2. **Parse** — `_parse_spdr_rows()` extracts date, total tonnes, ounces, value
3. **Dedup** — Checks if `holding_date` already exists for GLD
4. **Delta** — Computes `change_tonnes` from previous row
5. **Store** — Inserts into `etf_holdings` with provenance logging
6. **Backfill** — On first run (< 30 records), downloads full history (~5500 rows)

### Derived Statistics
- **z-score (90d):** `(latest_change - mean_90d) / std_90d` — measures today's change relative to recent volatility
- **Percentile (2yr):** Rank of latest change within up to 500 trading days — shows how unusual the flow is historically

## COT Pipeline

### Source
- **URL:** `https://www.cftc.gov/dea/newcot/deafut.txt`
- **Type:** Headerless comma-delimited text, one row per commodity per week
- **Contract Code:** `088691` (Gold - COMEX)
- **Frequency:** Weekly reports (published Fridays), checked by worker every 6 hours
- **Saved as:** `source_url` column in `cot_data` table

### Processing Steps
1. **Download** — Fetches the weekly report from CFTC
2. **Filter** — Selects rows where contract code contains `088691`
3. **Parse** — Extracts non-commercial longs/shorts, commercial longs/shorts, open interest
4. **Compute Net** — `non_commercial_net = long - short`
5. **Delta** — `change_non_commercial_net` from previous week
6. **Store** — Inserts into `cot_data` with provenance logging
7. **Backfill** — `backfill_cot_history()` downloads yearly ZIP archives from CFTC (2014+)

### Derived Statistics
- **WoW % of OI:** `change_non_commercial_net / open_interest * 100` — weekly position change normalized by market size
- **Percentile (1yr/3yr):** Rank of current net position within 1-year and 3-year distributions

## Combined Signal

Rule-based classification combining ETF z-score and COT percentile:

| Signal | Condition | Persian Label | Confidence |
|--------|-----------|---------------|------------|
| `EXTREME_RISK` | \|ETF z\| > 2.0 OR COT pct > 95% or < 5% | ریسک بحرانی | 85% |
| `CONFIRMING` | ETF z > +0.5 AND COT pct > 60% | تأیید صعودی | 75% |
| `CONFIRMING_BEARISH` | ETF z < -0.5 AND COT pct < 40% | تأیید نزولی | 75% |
| `DIVERGING` | One bullish + one bearish | واگرایی | 55% |
| `NEUTRAL` | Otherwise | خنثی | 30% |

**Priority:** EXTREME_RISK > CONFIRMING/CONFIRMING_BEARISH > DIVERGING > NEUTRAL

### Thresholds (module constants in `derived_money_flow.py`)
```python
ETF_Z_BULLISH = 0.5       # z > 0.5 = accumulation
ETF_Z_BEARISH = -0.5      # z < -0.5 = liquidation
ETF_Z_EXTREME = 2.0       # |z| > 2 = 2-sigma event
COT_PCT_BULLISH = 60.0    # > 60th percentile
COT_PCT_BEARISH = 40.0    # < 40th percentile
COT_PCT_EXTREME_HIGH = 95.0
COT_PCT_EXTREME_LOW = 5.0
```

## Provenance Trail

Every data fetch is logged through the data reliability system (migration 013):

1. **calc_run_log** — Tracks each scraper execution (start time, end time, status)
2. **ingest_log** — Records HTTP request details (URL, status code, response size, latency)
3. **transform_log** — Documents each processing step (parsing, delta calculation)
4. **metric_qa** — Validates output against historical bounds, staleness thresholds

To trace any ETF value back to source:
1. Find the row in `etf_holdings` — note the `source_url` and `fetched_at`
2. Query `calc_run_log` for `metric_id='etf_gld'` around that time
3. Follow `ingest_log` for the HTTP request details
4. Check `metric_qa` for any quality warnings

## Admin Dashboard

The data reliability admin page at `/admin/data-reliability/` shows:
- Pipeline health status for all metrics including `etf_gld` and `cot_gold`
- Recent run history with success/failure indicators
- QA alerts when values fall outside expected ranges
- Staleness warnings when data hasn't been updated within expected intervals
