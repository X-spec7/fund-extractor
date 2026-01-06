COUNTRY_TO_ISO3 = {
    # Common countries in the sample reports
    "Canada": "CAN",
    "Sweden": "SWE",
    "Switzerland": "CHE",
    "China": "CHN",
    "Taiwan": "TWN",
    "Denmark": "DNK",
    "France": "FRA",
    "Germany": "DEU",
    "India": "IND",
    "Italy": "ITA",
    "Japan": "JPN",
    "Netherlands": "NLD",
    "Singapore": "SGP",
    "South Korea": "KOR",
    "Spain": "ESP",
    "United Kingdom": "GBR",
    "United States": "USA",
    "Brazil": "BRA",
    "Mexico": "MEX",
    "Peru": "PER",
    "Philippines": "PHL",
    "Indonesia": "IDN",
    "Romania": "ROU",
    "Saudi Arabia": "SAU",
    "South Africa": "ZAF",
    "Egypt": "EGY",
    "Greece": "GRC",
    "Hong Kong": "HKG",
    "Slovenia": "SVN",
    "Thailand": "THA",
}


def country_heading_to_iso3(heading: str) -> str | None:
    """
    Map a heading like 'Canada—6.5%' or 'Brazil–5.4%' to an ISO3 code, if known.
    """
    # Normalize various dash characters and strip percentages
    base = heading.split("—")[0].split("–")[0].strip()
    if not base:
        return None
    return COUNTRY_TO_ISO3.get(base)


