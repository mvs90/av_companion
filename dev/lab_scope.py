"""Keep destructive acceptance steps scoped to uniquely named lab entries."""

LAB_TITLES = {"lg_rs232_ip": "LG Split Test", "av_companion": "AV Split Test"}


def lab_entry(entries, domain, *, required=True):
    """Refuse ambiguity; never fall back to the first installation of a domain."""
    title = LAB_TITLES[domain]
    matches = [e for e in entries if e["domain"] == domain and e["title"] == title]
    if len(matches) > 1:
        raise ValueError(f"Multiple test entries named {title}; refusing to modify any")
    if not matches:
        if required:
            raise ValueError(
                f"Missing test entry {title}; refusing to use another device"
            )
        return None
    return matches[0]
