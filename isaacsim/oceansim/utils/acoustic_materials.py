"""Acoustic material properties for sonar simulation.

Reflection coefficients derived from acoustic impedance mismatch with seawater.
R = (Z_material - Z_water) / (Z_material + Z_water)
where Z = density * sound_speed (MRayl)
Seawater Z ~ 1.54 MRayl
"""

ACOUSTIC_MATERIALS = {
    "steel": {"reflectivity": 0.93, "impedance_mrayl": 46.0, "description": "Steel structures, pipelines, ship hulls"},
    "aluminum": {"reflectivity": 0.84, "impedance_mrayl": 17.0, "description": "Aluminum frames, housings"},
    "concrete": {"reflectivity": 0.66, "impedance_mrayl": 7.4, "description": "Quay walls, bridge pilings, breakwaters"},
    "rock": {"reflectivity": 0.81, "impedance_mrayl": 14.9, "description": "Natural rock, granite, boulders"},
    "sand": {"reflectivity": 0.39, "impedance_mrayl": 3.5, "description": "Sandy seabed, saturated sand"},
    "mud": {"reflectivity": 0.19, "impedance_mrayl": 2.25, "description": "Muddy/silty seabed"},
    "wood": {"reflectivity": 0.15, "impedance_mrayl": 2.1, "description": "Wooden pilings, structures"},
    "rubber": {"reflectivity": 0.04, "impedance_mrayl": 1.6, "description": "Rubber, neoprene, cable insulation"},
    "default": {"reflectivity": 1.0, "impedance_mrayl": None, "description": "Default (maximum reflectivity)"},
}


def get_reflectivity(material_name: str) -> float:
    """Look up acoustic reflectivity for a material name. Case-insensitive with fallback to default."""
    key = material_name.lower().strip()
    if key in ACOUSTIC_MATERIALS:
        return ACOUSTIC_MATERIALS[key]["reflectivity"]
    return ACOUSTIC_MATERIALS["default"]["reflectivity"]


def list_materials() -> list:
    """Return list of available material names (excluding default)."""
    return [k for k in ACOUSTIC_MATERIALS.keys() if k != "default"]
