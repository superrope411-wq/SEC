# Company selection: Microsoft, Salesforce, Adobe

The provisional trio is all large-cap US enterprise software, which keeps business mix
broadly comparable (subscription/cloud revenue, high gross margins, deferred revenue as a
key balance-sheet item). The main comparability problem is **fiscal calendars**.

| Company | CIK | Fiscal year ends | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|---|
| Microsoft | 789019 | June 30 | Jul–Sep | Oct–Dec | Jan–Mar | Apr–Jun |
| Salesforce | 1108524 | January 31 | Feb–Apr | May–Jul | Aug–Oct | Nov–Jan |
| Adobe | 796343 | Friday nearest Nov 30 (52/53 weeks) | Dec–Feb | Mar–May | Jun–Aug | Sep–Nov |

(Fiscal-year ends are the companies' long-standing public reporting calendars and are
verified on ingest against the `fiscalYearEnd` field of the SEC submissions API; the
pipeline derives quarter boundaries from reported period dates rather than assuming them.)

## Implications

1. **"Q2" means a different calendar window for each company.** Salesforce's FY2026 Q2 is
   May–Jul 2025; Microsoft's FY2026 Q2 is Oct–Dec 2025. Every period label therefore shows
   both the fiscal label and the calendar months, e.g. *FY2026 Q2 (Oct–Dec 2025)*.
2. **Cross-company comparisons need calendar alignment, not fiscal alignment.** Milestone 3
   will align on overlapping calendar quarters (e.g. the quarter ending nearest Sep 30) and
   warn when windows differ by more than a few weeks (Adobe's 52/53-week quarters end on
   varying dates).
3. **Adobe's 52/53-week year** means quarter lengths vary (91 or 98 days) and the fiscal
   year occasionally has 53 weeks; the calendar builder tolerates this (quarter detection
   uses 80–100 day windows and ±20 days around 3/6/9/12 months).
4. **Business mix**: Microsoft includes hardware (Xbox, Surface) and LinkedIn; Salesforce and
   Adobe are nearly pure software. Margins are comparable in direction, not level.
5. **Deferred revenue**: all three report contract liabilities, but Salesforce reports
   "unearned revenue" (current only on the face of the balance sheet) and Adobe reports
   "deferred revenue" current and non-current; the approved-concept lists cover both tag
   families, and non-comparable items show as missing rather than forced.

## Recommendation

Keep the trio. The fiscal-calendar differences are real but they are exactly the problem a
robust period-normalization layer must solve, and solving it is more convincing in a
portfolio than picking three December year-end companies. Microsoft goes first because its
June year-end exercises the fiscal-vs-calendar logic from day one while its quarters are
regular calendar quarters.
