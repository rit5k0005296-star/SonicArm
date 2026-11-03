# Evidence rules

- `PASS`: the requested static checks all pass; identity is proven only when a trusted build manifest matches.
- When no manifest is supplied, report `NO_MANIFEST` and complete the remaining structural checks.
- `FAIL`: missing required artifact/IP, malformed XML, overlap, or hash mismatch.
- A runtime `ip_dict` observation proves the current metadata view, not functional board behavior.
