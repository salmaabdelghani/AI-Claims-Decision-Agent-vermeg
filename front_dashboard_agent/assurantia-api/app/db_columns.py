"""
Mapping entre les cles Pydantic (snake_case) et les colonnes reelles des
tables `garanties` / `exclusion`, dont certains noms sont en CamelCase et
un seul contient un tiret ("vol-plafond") — d'ou la necessite de guillemets
doubles et d'un mapping explicite plutot que de generer les noms a la volee.
"""

GARANTIE_COLS = {
    "dommages_collision_active": '"Dommages_Collision_Active"',
    "dommages_collision_franchise": '"Dommages_Collision_franchise"',
    "dommages_collision_plafond": '"Dommages_Collision_plafond"',
    "dommages_collision_couverture": '"Dommages_Collision_Couverture"',
    "rc_active": '"RC_Active"',
    "rc_franchise": '"RC_franchise"',
    "rc_plafond": '"RC_plafond"',
    "rc_couverture": '"RC_Couverture"',
    "vol_active": '"Vol_Active"',
    "vol_franchise": '"Vol_franchise"',
    "vol_plafond": '"vol-plafond"',
    "vol_couverture": '"Vol_Couverture"',
    "incendie_active": '"Incendie_Active"',
    "incendie_franchise": '"Incendie_franchise"',
    "incendie_plafond": '"Incendie_plafond"',
    "incendie_couverture": '"Incendie_Couverture"',
    "bris_glace_active": '"Bris_de_Glace_Active"',
    "bris_glace_franchise": '"Bris_de_Glace_franchise"',
    "bris_glace_plafond": '"Bris_de_Glace_plafond"',
    "bris_glace_couverture": '"Bris_de_Glace_Couverture"',
}

EXCLUSION_COLS = {
    "conduite_sous_alcool": '"Exclusions_Conduite_sous_alcool"',
    "conducteur_non_autorise": '"Exclusions_Conducteur_non_autorise"',
}


def select_list(col_map: dict) -> str:
    """'"Db_Col" AS py_key, ...' pour un SELECT."""
    return ", ".join(f"{dbcol} AS {pykey}" for pykey, dbcol in col_map.items())


def insert_clause(col_map: dict) -> tuple[str, str]:
    """('"Db_Col1", "Db_Col2"', '%(py_key1)s, %(py_key2)s') pour un INSERT."""
    cols = ", ".join(col_map.values())
    placeholders = ", ".join(f"%({pykey})s" for pykey in col_map)
    return cols, placeholders


def set_clause(col_map: dict) -> str:
    """'"Db_Col1" = %(py_key1)s, ...' pour un UPDATE."""
    return ", ".join(f"{dbcol} = %({pykey})s" for pykey, dbcol in col_map.items())
