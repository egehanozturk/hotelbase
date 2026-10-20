import re
from typing import Dict, Any, Optional

def classify_room_tier(raw_name: str, room_text: str = "", explicit_max_adults: Optional[int] = None) -> Dict[str, Any]:
    """
    Normalizes boutique hotel room names and room details into ML-ready features.
    Extracts room tier, size in sqm, view flags, balcony, AC, entire place flag, and max occupancy.
    Supports explicit max_adults extracted directly from Booking.com DOM occupancy elements.
    """
    combined_text = f"{raw_name} {room_text}".lower()
    name_lower = raw_name.lower()
    
    # 1. Determine Room Tier
    is_entire_place = bool(re.search(r"entire\s+(?:villa|apartment|house|home|place|building)|villa|mansion|holiday home", combined_text))

    if any(k in name_lower for k in ["suite", "king", "pasha", "penthouse", "villa", "mansion", "grand"]):
        tier = "Suite"
    elif any(k in name_lower for k in ["deluxe", "superior", "premier", "luxury"]):
        tier = "Superior_Deluxe"
    elif any(k in name_lower for k in ["economy", "budget", "attic", "basement", "annex", "small"]):
        tier = "Economy"
    elif any(k in name_lower for k in ["family", "quadruple", "triple", "connecting"]):
        tier = "Family"
    else:
        tier = "Standard"

    # 2. Extract Room Size in Sqm
    room_size_sqm: Optional[int] = None
    size_match = re.search(r"(\d+)\s*(?:m²|sqm|m2|square\s+met(?:er|re)s?)", combined_text)
    if size_match:
        try:
            val = int(size_match.group(1))
            # Sensible bounds for hotel room / villa size: between 8 and 1000 sqm
            if 8 <= val <= 1000:
                room_size_sqm = val
        except ValueError:
            pass

    # Inferred default room sizes based on tier and property type if missing
    if room_size_sqm is None:
        if is_entire_place:
            room_size_sqm = 150
        else:
            default_sizes = {
                "Economy": 15,
                "Standard": 20,
                "Superior_Deluxe": 28,
                "Family": 35,
                "Suite": 45
            }
            room_size_sqm = default_sizes.get(tier, 22)

    # 3. High-Value Amenities and Flags
    has_sea_view = any(k in combined_text for k in ["sea view", "marina view", "harbor view", "mediterranean view"])
    has_balcony = any(k in combined_text for k in ["balcony", "terrace", "patio", "veranda"])
    has_ac = any(k in combined_text for k in ["air conditioning", "air conditioned", "ac", "a/c"]) or True

    # 4. Calculate Max Adults Capacity
    if explicit_max_adults is not None and explicit_max_adults > 0:
        max_adults = explicit_max_adults
    else:
        # A. Check explicit text patterns (e.g. "max adults: 2" or "2 adults")
        explicit_text_match = re.search(r"(?:max\s*adults?|sleeps)\s*:\s*(\d+)", combined_text)
        if explicit_text_match:
            max_adults = int(explicit_text_match.group(1))
        else:
            # B. Check detailed bed configuration
            double_matches = re.findall(r'(\d+)\s+(?:double|large double|extra-large double|queen|king)\s+bed', combined_text)
            double_beds = sum(int(m) for m in double_matches)
            single_matches = re.findall(r'(\d+)\s+(?:single|twin)\s+bed', combined_text)
            single_beds = sum(int(m) for m in single_matches)
            bunk_matches = re.findall(r'(\d+)\s+bunk\s+bed', combined_text)
            bunk_beds = sum(int(m) for m in bunk_matches)
            sofa_matches = re.findall(r'(\d+)\s+sofa\s+bed', combined_text)
            sofa_beds = sum(int(m) for m in sofa_matches)

            # In boutique family rooms, bunk beds or extra singles in small rooms (<22m2)
            # are designated for children only, while adults are restricted to 2.
            is_child_bed_config = (
                bunk_beds > 0 or 
                "bunk bed" in combined_text or
                "ranza" in combined_text or
                (double_beds >= 1 and single_beds >= 1 and room_size_sqm is not None and room_size_sqm <= 22 and "family" in name_lower)
            )

            if is_child_bed_config and double_beds >= 1:
                max_adults = double_beds * 2
            else:
                calculated_capacity = (double_beds * 2) + single_beds + sofa_beds + (bunk_beds * 2)
                if calculated_capacity > 0:
                    max_adults = calculated_capacity
                elif any(k in name_lower for k in ["single"]):
                    max_adults = 1
                elif any(k in name_lower for k in ["triple"]):
                    max_adults = 3
                elif any(k in name_lower for k in ["quadruple"]):
                    max_adults = 4
                elif any(k in name_lower for k in ["family"]):
                    # Small family rooms default to 2 adults (plus kids)
                    max_adults = 2 if (room_size_sqm is not None and room_size_sqm <= 22) else 4
                elif is_entire_place:
                    max_adults = 8
                else:
                    max_adults = 2

    return {
        "room_tier": tier,
        "room_size_sqm": room_size_sqm,
        "has_sea_view": has_sea_view,
        "has_balcony": has_balcony,
        "has_ac": has_ac,
        "is_entire_place": is_entire_place,
        "max_adults": max_adults
    }