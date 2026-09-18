# TNM elevation products

Use `products` to request specific elevation products from The National Map:

```bash
fetchez run --global-hook list-only -R -124.5/-124.0/41.5/44.0 tnm --products 1m/1_3as
```

Supported names are `s1m`, `1m`, `1_9as`, `1_3as`, `1_as`, `5m`, and
`2_as`. Each product is queried separately, in the requested order. Repeated
names are queried once. This order does not establish coverage precedence.

Each entry includes `tnm_product` and `tnm_dataset`, along with the existing
source ID, publication date, update date, and metadata links supplied by TNM.
`tnm_project` is the decoded project directory from the download URL, when
present. It is not a verified WESM project identifier. No WESM lookup is made.

Downloads requested through `products` use a product directory and a short
URL hash before the filename, so different endpoints with the same filename
do not overwrite each other. Overlapping entries remain available to hooks.

Product queries raise an error if the API rejects the dataset, fails a request,
or returns incomplete or inconsistent pages. Entries collected during that
run are removed before the error is raised. A failed query must not be treated
as evidence that a higher-resolution product has no coverage. A successful
query returning zero products is allowed.

An API outage is never reported as zero products. If the API does not
respond, answers with a non-200 status, a non-JSON page, or a JSON body that
carries an error or lacks the `total` and `items` fields, the query is treated
as failed: strict queries raise, other queries log an error and return what
was collected so far. The results of a failed query are not written to the
results cache, so a later run asks the API again instead of replaying the
outage as an empty answer.

The existing `datasets` argument and default one-arc-second query remain
available. Do not combine `products` and `datasets`. Use
`--strict-datasets true` with `datasets` to request the same error handling;
otherwise the existing broad-search fallback remains available. Results from
that fallback are not assigned a specific product label.

Discovery provides API bounding boxes. Use footprint hooks to obtain more
precise geometry and `spatial_cull` when whole overlapping entries should be
removed. Partial coverage exclusions, resolution precedence, and WESM project
matching belong in the consuming application, such as Globato.
