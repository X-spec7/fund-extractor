COUNTRY_TO_ISO3 = {
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
    "Norway": "NOR",
    "Finland": "FIN",
    "Belgium": "BEL",
    "Austria": "AUT",
    "Ireland": "IRL",
    "Portugal": "PRT",
    "Poland": "POL",
    "Czech Republic": "CZE",
    "Hungary": "HUN",
    "Singapore": "SGP",
    "South Korea": "KOR",
    "Spain": "ESP",
    "United Kingdom": "GBR",
    "United States": "USA",
    "Australia": "AUS",
    "New Zealand": "NZL",
    "Brazil": "BRA",
    "Mexico": "MEX",
    "Argentina": "ARG",
    "Chile": "CHL",
    "Colombia": "COL",
    "Peru": "PER",
    "Uruguay": "URY",
    "Peru": "PER",
    "Philippines": "PHL",
    "Indonesia": "IDN",
    "Malaysia": "MYS",
    "Thailand": "THA",
    "Vietnam": "VNM",
    "Pakistan": "PAK",
    "Bangladesh": "BGD",
    "Turkey": "TUR",
    "Israel": "ISR",
    "Romania": "ROU",
    "Saudi Arabia": "SAU",
    "United Arab Emirates": "ARE",
    "Qatar": "QAT",
    "Kuwait": "KWT",
    "Bahrain": "BHR",
    "South Africa": "ZAF",
    "Egypt": "EGY",
    "Nigeria": "NGA",
    "Kenya": "KEN",
    "Morocco": "MAR",
    "Russia": "RUS",
    "Ukraine": "UKR",
    "Egypt": "EGY",
    "Greece": "GRC",
    "Hong Kong": "HKG",
    "Slovenia": "SVN",
}


def country_heading_to_iso3(heading: str) -> str | None:
    """
    Map a heading like 'Canada—6.5%' or 'Brazil–5.4%' to an ISO3 code, if known.

    This implementation scans the full line and looks for a known country name
    immediately followed by a dash (–, — or -), which is how country headings
    typically appear in the PDF schedules.
    """
    import re

    # Normalize by also considering a version without spaces, since some PDFs
    # drop spaces in headings (e.g. 'UnitedKingdom—15.7%').
    heading_nospace = heading.replace(" ", "")

    for name, iso in COUNTRY_TO_ISO3.items():
        # Pattern with spaces (normal case)
        pattern_with_space = rf"\b{name}\b\s*[—\-–]"
        if re.search(pattern_with_space, heading):
            return iso

        # Pattern without spaces (to catch e.g. 'UnitedKingdom—')
        name_nospace = name.replace(" ", "")
        pattern_nospace = rf"{name_nospace}\s*[—\-–]"
        if re.search(pattern_nospace, heading_nospace):
            return iso
    return None


