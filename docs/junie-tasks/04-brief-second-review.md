# Task 4: second review of the scouting brief

The period, the Utility filter and the Operator section are now right: round counts match the app for six views checked independently. Three things are still wrong.

## 1. Key findings lost the sample size

Bullets now read "45 of defense rounds". The fix for the double "of" removed `n`. Each bullet must give both numbers: "45 of 84 defense rounds". The finding has `k`, `n` and a `unit` that starts with "of "; build the sentence from all three.

The tests did not catch this. Add a test that every Key findings bullet contains "k of n" for its finding, and make the data test compare the list of (k, n) pairs parsed from the Key findings section with the (k, n) pairs of `scout_payload["insights"]`, in order.

## 2. The title block lost the dates

It now says "(Last 6 months)" and nothing else. Show the period and the date range from `sample.range_label` together, so a reader sees both which filter was used and which matches it covered.

## 3. Strength wording

"*(strength: strong evidence)*" is clumsy. End the bullet with the plain words: "strong evidence", "moderate evidence" or "thin evidence".

Update the README example to match. Run `python -m pytest` before finishing. Same constraints as the earlier tasks.
