# End-to-end example: Why did revenue increase in fiscal year 2025 compared with fiscal year 2024?

Filing: 10-K 0000950170-25-100235, filed 2025-07-30 (https://www.sec.gov/Archives/edgar/data/789019/000095017025100235/msft-20250630.htm).
Data source: fixture; filing text SHA-256 8223271391eda4e8…

## 1. Calculated change (verified pipeline, Milestone 1)

Revenue FY2025 (Jul 2024–Jun 2025): $281,724M; FY2024 (Jul 2023–Jun 2024): $245,122M; change $36,602M (14.93%).

## 2. Evidence retrieved (15 passages of 1248 in the filing)

| rank | evidence ID | section | page | periods | score | text |
|---|---|---|---|---|---|---|
| 1 | `0000950170-25-100235:PII-I7:e21d80cc7e` | PII-I7 | 38 | 12M:2025-06-30, 12M:2024-06-30 | 29.7 | Revenue increased $36.6 billion or 15% with growth across each of our segments. Intelligent Cloud revenue incr… |
| 2 | `0000950170-25-100235:PII-I7:a9e8879166` | PII-I7 | 35 | 12M:2025-06-30, 12M:2024-06-30 | 14.9 | Highlights from fiscal year 2025 compared with fiscal year 2024 included:… |
| 3 | `0000950170-25-100235:PII-I7:3453c85d8b` | PII-I7 | 39 | 12M:2025-06-30, 12M:2024-06-30 | 24.1 | Total - Revenue: 2025 281,724; 2024 245,122; Percentage Change 15%… |
| 4 | `0000950170-25-100235:PII-I7:2c5e9eeeb7` | PII-I7 | 35 | 12M:2025-06-30, 12M:2024-06-30 | 17.3 | LinkedIn revenue increased 9%.… |
| 5 | `0000950170-25-100235:PII-I7:19e9737041` | PII-I7 | 39 | 12M:2025-06-30, 12M:2024-06-30 | 16.6 | Microsoft 365 Consumer products and cloud services revenue increased $756 million or 11%. Microsoft 365 Consum… |
| 6 | `0000950170-25-100235:PII-I7:49693d4374` | PII-I7 | 35 | 12M:2025-06-30, 12M:2024-06-30 | 16.5 | Windows OEM and Devices revenue increased 3%.… |
| 7 | `0000950170-25-100235:PII-I7:929f568218` | PII-I7 | 35 | 12M:2025-06-30, 12M:2024-06-30 | 16.5 | Xbox content and services revenue increased 16%.… |
| 8 | `0000950170-25-100235:PII-I7:0ffc23ae26` | PII-I7 | 40 | 12M:2025-06-30, 12M:2024-06-30 | 16.4 | Search and news advertising revenue increased $1.6 billion or 13%. Search and news advertising revenue excludi… |
| 9 | `0000950170-25-100235:PII-I7:767846368b` | PII-I7 | 40 | 12M:2025-06-30, 12M:2024-06-30 | 16.4 | Revenue increased $18.8 billion or 21%.… |
| 10 | `0000950170-25-100235:PII-I7:30a1239827` | PII-I7 | 35 | 12M:2025-06-30, 12M:2024-06-30 | 12.5 | Dynamics products and cloud services revenue increased 15% driven by Dynamics 365 revenue growth of 19%.… |
| 11 | `0000950170-25-100235:PII-I8:2ec7ba9c02` | PII-I8 | 50 | 12M:2025-06-30, 12M:2024-06-30, 12M:2023-06-30 | 16.3 | Revenue: - Total revenue: 2025 281,724; 2024 245,122; 2023 211,915… |
| 12 | `0000950170-25-100235:PII-I7:50ce400ec3` | PII-I7 | 35 | 12M:2025-06-30, 12M:2024-06-30 | 12.3 | Microsoft Cloud revenue increased 23% to $168.9 billion.… |
| 13 | `0000950170-25-100235:PII-I7:a97410a91e` | PII-I7 | 35 | 12M:2025-06-30, 12M:2024-06-30 | 12.1 | Server products and cloud services revenue increased 23% driven by Azure and other cloud services revenue grow… |
| 14 | `0000950170-25-100235:PII-I7:a837e8c47d` | PII-I7 | 40 | 12M:2025-06-30, 12M:2024-06-30 | 16.2 | Revenue increased $3.8 billion or 7%.… |
| 15 | `0000950170-25-100235:PII-I7:a546184978` | PII-I7 | 40 | 12M:2025-06-30, 12M:2024-06-30 | 12.1 | Windows and Devices revenue increased $288 million or 2%. Windows OEM and Devices revenue increased 3% driven … |

## 3. Model input

Prompt version `m2-explain-1:db3c1f73`; 10,510 characters; cache key `4ecd55328da732c0…`; worst-case cost for claude-opus-5-5 at max_tokens=16000: $0.33.

Timing: load and analyze 2.33s, extract and index the filing 0.59s, retrieve and build the prompt 0.031s.

## 4. Model answer, checked

Status: **supported** (at least one cited management statement passed every check); model said: supported.

- [management, accepted] Revenue increased $36.6 billion or 15%, with growth in every segment.
  - `0000950170-25-100235:PII-I7:e21d80cc7e` p.38: “Revenue increased $36.6 billion or 15% with growth across each of our segments.”
- [management, accepted] Intelligent Cloud revenue grew because of Azure. Server products and cloud services revenue grew 23%, driven by 34% growth in Azure and other cloud services.
  - `0000950170-25-100235:PII-I7:e21d80cc7e` p.38: “Intelligent Cloud revenue increased driven by Azure.”
  - `0000950170-25-100235:PII-I7:767846368b` p.40: “Revenue increased $18.8 billion or 21%.”
  - `0000950170-25-100235:PII-I7:a97410a91e` p.35: “Server products and cloud services revenue increased 23% driven by Azure and other cloud services revenue growth of 34%.”
- [management, REJECTED] Productivity and Business Processes revenue grew because of Microsoft 365 Commercial cloud. Within the segment, Dynamics grew 15% on 19% Dynamics 365 growth. Microsoft 365 Consumer grew 11% on subscriber growth and higher revenue per user from a price increase. LinkedIn revenue rose 9%. — states a cause the quotes do not give (missing: segment, within)
  - `0000950170-25-100235:PII-I7:e21d80cc7e` p.38: “Productivity and Business Processes revenue increased driven by Microsoft 365 Commercial cloud.”
  - `0000950170-25-100235:PII-I7:30a1239827` p.35: “Dynamics products and cloud services revenue increased 15% driven by Dynamics 365 revenue growth of 19%.”
  - `0000950170-25-100235:PII-I7:19e9737041` p.39: “Microsoft 365 Consumer cloud revenue grew 11% driven by Microsoft 365 Consumer subscriber growth of 8% to 89.0 million, as well as growth in revenue per user from the price increase announced in January 2025.”
  - `0000950170-25-100235:PII-I7:2c5e9eeeb7` p.35: “LinkedIn revenue increased 9%.”
- [management, accepted] More Personal Computing revenue grew $3.8 billion or 7%, driven by Gaming and Search and news advertising. Xbox content and services rose 16%. Search and news advertising excluding traffic acquisition costs rose 20% on higher search volume and higher revenue per search. Windows OEM and Devices rose 3%, with Windows OEM growth partly offset by a decline in Devices.
  - `0000950170-25-100235:PII-I7:e21d80cc7e` p.38: “More Personal Computing revenue increased driven by Gaming and Search and news advertising.”
  - `0000950170-25-100235:PII-I7:a837e8c47d` p.40: “Revenue increased $3.8 billion or 7%.”
  - `0000950170-25-100235:PII-I7:929f568218` p.35: “Xbox content and services revenue increased 16%.”
  - `0000950170-25-100235:PII-I7:0ffc23ae26` p.40: “Search and news advertising revenue excluding traffic acquisition costs increased 20% driven by higher search volume and higher revenue per search.”
  - `0000950170-25-100235:PII-I7:a546184978` p.40: “Windows OEM and Devices revenue increased 3% driven by growth in Windows OEM, offset in part by a decline in Devices.”
- [management, accepted] Microsoft Cloud revenue increased 23% to $168.9 billion.
  - `0000950170-25-100235:PII-I7:50ce400ec3` p.35: “Microsoft Cloud revenue increased 23% to $168.9 billion.”
- [inference, accepted] Intelligent Cloud, and Azure within it, appears to account for roughly half of the total revenue increase. This makes it the largest single contributor.
- figure $36.6 billion (revenue, change_amount): verified 
- figure 15% (revenue, change_percent): verified 
- figure 281,724 (revenue, current_value): verified 
- figure 245,122 (revenue, prior_value): verified 
- figure 15% (revenue, change_percent): verified 

Usage: claude-opus-5-5, 5,713 in / 2,144 out tokens, $0.0657, 19.9s (cached).
