"""
Shared car classification module.
Maps iRacing car names to classes for class-specific analysis parameters.
"""

from enum import Enum


class CarClass(Enum):
    GT3 = "gt3"
    GT4 = "gt4"
    GTP = "gtp"
    LMP2 = "lmp2"
    FORMULA = "formula"
    PORSCHE_CUP = "porsche_cup"
    TCR = "tcr"
    STOCK = "stock"
    GTE = "gte"
    PROTOTYPE = "prototype"      # older DP / sport-protos
    V8_SUPERCAR = "v8_supercar"
    RALLY_CROSS = "rally_cross"
    DIRT_OVAL = "dirt_oval"
    ROAD_ROOKIE = "road_rookie"  # MX-5, Vee, Solstice, Radical SR8, etc.
    SPORTS_CAR = "sports_car"    # RUF, FR500, Kia, Jetta, etc.
    SUPER_FORMULA = "super_formula"
    DEFAULT = "default"


# Keywords in iRacing car path/name strings → class
# Order matters: more specific keywords first prevents false matches.
_CAR_KEYWORDS = {
    CarClass.GTP: [
        'gtp', 'hypercar', 'lmdh',
        'porsche963', 'porsche_963',
        'cadillacvseriesr', 'cadillac_v_series', 'cadillac_vr',
        'acuraarx06', 'acura_arx06', 'acura_arx',
        'bmwlmdh', 'bmw_mhybrid', 'bmw_lmdh',
        'ferrari499p', 'ferrari_499p',
        'toyota_gr010', 'toyotagr010',
    ],
    CarClass.GTE: [
        'gte',
        'bmwm8gte', 'bmw_m8_gte',
        'ferrari488gte', 'ferrari_488_gte',
        'fordgt2017', 'ford_gt_2017', 'fordgt_gt3',
        'c8rvettegte', 'c8r_vette_gte', 'corvette_c8_gte',
        'porsche991rsr', 'porsche_991_rsr',
    ],
    CarClass.GT4: [
        'gt4',
        'gt3ichallenge', 'gt3i_challenge',
        'bmwm4gt4', 'bmwm4evogt4', 'bmw_m4_gt4',
        'mclaren570sgt4', 'mclaren_570s_gt4',
        'porsche718gt4', 'porsche_718_gt4',
        'mercedesamggt4', 'mercedes_amg_gt4',
        'amvantagegt4', 'aston_martin_gt4',
        'fordmustanggt4', 'ford_mustang_gt4',
        'toyotagr86', 'toyota_gr86',
    ],
    CarClass.GT3: [
        'gt3',
        'mercedesamggt3', 'mercedesamgevogt3', 'mercedes_amg_gt3',
        'ferrari296gt3', 'ferrari_296_gt3', 'ferrarievogt3', 'ferrari488gt3',
        'bmwm4gt3', 'bmw_m4_gt3',
        'porsche911rgt3', 'porsche_911_gt3', 'porsche992rgt3',
        'audir8gt3', 'audir8lmsevo2gt3', 'audi_r8_gt3',
        'mclaren720sgt3', 'mclaren_720s_gt3',
        'lamborghinievogt3', 'lamborghini_huracan_gt3', 'lamborghini_evo',
        'amvantageevogt3', 'aston_martin_vantage_gt3',
        'corvette_c8r', 'chevyvettez06rgt3',
        'fordmustanggt3', 'ford_mustang_gt3', 'fordgt gt3',
        'bmwz4gt3',
        'acuransxevo22gt3', 'acura_nsx_gt3',
    ],
    CarClass.LMP2: [
        'lmp2', 'dallara_p217', 'dallarap217',
        'oreca_07', 'oreca07',
        'ligierjsp320', 'ligier_jsp320',
    ],
    CarClass.PROTOTYPE: [
        'hpdarx01', 'hpd_arx_01',
        'rileydp', 'riley_dp',
        'c7vettedp', 'c7_vette_dp',
        'dallarail15', 'dallara_il15',
        'audir18', 'audi_r18',
        'porsche919', 'porsche_919',
        'nissangtpzxt', 'nissan_gtp_zxt',
        'c6r',
    ],
    CarClass.SUPER_FORMULA: [
        'superformula', 'sf23', 'sfir23', 'sfir',
        'superformulalights', 'sf_lights', 'sflight',
    ],
    CarClass.FORMULA: [
        'formulair04', 'formula_ir04', 'ir04',
        'dallaraf3', 'dallara_f3',
        'dallarair18', 'dallara_ir18', 'ir18',
        'dallarair01', 'dallara_ir01', 'ir01',
        'dalladw12', 'dallaradw12', 'dallara_dw12',
        'w12', 'w13', 'williamsfw31', 'williams_fw31',
        'mercedesw12', 'mercedesw13',
        'formulamaz', 'formula_mazda',
        'formularenault', 'formula_renault',
        'formulavee', 'formula_vee',
        'usf2000', 'usf17',
        'indypropm18', 'indy_pro', 'pm18',
        'raygr22', 'ray_gr22',
        'radical sr8', 'radicalsr10', 'radical_sr',
        'skipbarber', 'skip_barber',
        'rt2000',
        'lotus49', 'lotus_49',
        'lotus79', 'lotus_79',
        'mclarenmp4', 'mclarenmp430', 'mclaren_mp4',
    ],
    CarClass.PORSCHE_CUP: [
        'porsche9922cup', 'porsche992cup', 'porsche911cup',
        'porsche_992_cup', 'porsche_cup', '992_cup', '992cup',
        'ferrari296challenge', 'ferrari_296_challenge',
        'porschemissionr', 'porsche_mission_r',
    ],
    CarClass.TCR: [
        'tcr', 'tcn',
        'hondacivictyper', 'honda_civic', 'civic_tcr',
        'hyundaielantracn', 'hyundai_elantra', 'elantra_tcr',
        'hyundaitcn', 'hyundaivelostern', 'hyundai_veloster', 'veloster_tcr',
        'audirs3lms', 'audi_rs3', 'audirs3',
        'renaultcliocup', 'renault_clio',
        'bmwm2csr', 'bmw_m2_csr',
    ],
    CarClass.V8_SUPERCAR: [
        'v8supercar', 'v8_supercar', 'supercar',
        'fordv8sc', 'ford_v8sc',
        'fordmustanggen3', 'ford_mustang_gen3',
        'chevycamarogen3', 'chevy_camaro_gen3',
        'holden2014', 'holden2019', 'holden_commodore',
        'v8supercars', 'fordmustanggt',
    ],
    CarClass.DIRT_OVAL: [
        'dirtlatemodel', 'dirt_late_model',
        'dirtmodified', 'dirt_modified',
        'dirtsprint', 'dirt_sprint',
        'dirtmidget', 'dirt_midget',
        'dirtministock', 'dirt_mini_stock',
        'dirtmicrosprint', 'dirt_microsprint',
        'dirtstreetstock', 'dirt_street_stock',
        'dirtumpmod', 'dirt_ump_mod',
        'legends', 'legends_ford',
    ],
    CarClass.STOCK: [
        'nascar', 'nextgen', 'stockcar',
        'camarozl1', 'chevycamarozl1',
        'fordmustang2019', 'fordmustang2022',
        'toyotacamry', 'toyotacamry2022',
        'chevymontecarlo', 'chevyss',
        'pontiacgrandprix', 'fordthunderbird',
        'fordfusion', 'fordtaurus',
        'buicklesabre', 'impala',
        'camaro2019', 'camry2015', 'mustang2019', 'supra2019',
        'nwcamaro', 'nwford',
        'stockcars', 'stockcars2',
        'arca', 'arcachevy', 'arcaford', 'arcatoyota',
        'trucks', 'silverado', 'tundra', 'ram2026', 'fordf150',
        'stockcarbrasil', 'corolla', 'cruze',
        'silvercrown', 'sprint',
        'latemodel', 'superlatemodel',
        'skmodified', 'ministock',
        'srx',
    ],
    CarClass.RALLY_CROSS: [
        'rallycross', 'rally_cross',
        'crosscartn11', 'crosscar_tn11',
        'vwbeetlegrc', 'vw_beetle_grc', 'beetle_grc',
        'subaruwrxsti', 'subaru_wrx',
        'fordfiestarswrc', 'ford_fiesta_wrc',
        'protrucks', 'pro2lite', 'pro2truck', 'pro4truck',
    ],
    CarClass.ROAD_ROOKIE: [
        'mx5', 'mx_5', 'miata',
        'solstice',
        'specracer', 'spec_racer',
        'formulavee', 'formula_vee',
        'streetstock',
    ],
    CarClass.SPORTS_CAR: [
        'rufrt12r', 'ruf_rt12r',
        'fr500s', 'fr_500s',
        'kiaoptima', 'kia_optima',
        'jettatdi', 'jetta_tdi',
        'cadillacctsvr', 'cadillac_cts_vr',
        'audi90gto', 'audi_90_gto',
        'astonmartin dbr9', 'aston_martin_dbr9',
    ],
}


def classify_car(car_name: str) -> CarClass:
    """Classify a car name string into a CarClass."""
    lower = car_name.lower().replace(' ', '_').replace('-', '_')
    for cls, keywords in _CAR_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return cls
    return CarClass.DEFAULT


# ── Class-specific analysis parameters ────────────────────────────────────

PRESSURE_TARGETS = {
    CarClass.GT3:          {'LF': 33.5, 'RF': 33.5, 'LR': 32.0, 'RR': 32.0},
    CarClass.GT4:          {'LF': 33.0, 'RF': 33.0, 'LR': 31.5, 'RR': 31.5},
    CarClass.GTP:          {'LF': 27.0, 'RF': 27.0, 'LR': 25.0, 'RR': 25.0},
    CarClass.GTE:          {'LF': 27.5, 'RF': 27.5, 'LR': 25.5, 'RR': 25.5},
    CarClass.LMP2:         {'LF': 27.5, 'RF': 27.5, 'LR': 25.5, 'RR': 25.5},
    CarClass.PROTOTYPE:    {'LF': 28.0, 'RF': 28.0, 'LR': 26.0, 'RR': 26.0},
    CarClass.FORMULA:      {'LF': 26.5, 'RF': 26.5, 'LR': 24.0, 'RR': 24.0},
    CarClass.SUPER_FORMULA: {'LF': 26.0, 'RF': 26.0, 'LR': 24.0, 'RR': 24.0},
    CarClass.PORSCHE_CUP:  {'LF': 33.0, 'RF': 33.0, 'LR': 31.0, 'RR': 31.0},
    CarClass.TCR:          {'LF': 34.0, 'RF': 34.0, 'LR': 32.5, 'RR': 32.5},
    CarClass.V8_SUPERCAR:  {'LF': 32.0, 'RF': 32.0, 'LR': 30.0, 'RR': 30.0},
    CarClass.STOCK:        {'LF': 35.0, 'RF': 35.0, 'LR': 34.0, 'RR': 34.0},
    CarClass.RALLY_CROSS:  {'LF': 30.0, 'RF': 30.0, 'LR': 28.0, 'RR': 28.0},
    CarClass.DIRT_OVAL:    {'LF': 16.0, 'RF': 16.0, 'LR': 16.0, 'RR': 16.0},
    CarClass.ROAD_ROOKIE:  {'LF': 30.0, 'RF': 30.0, 'LR': 29.0, 'RR': 29.0},
    CarClass.SPORTS_CAR:   {'LF': 32.0, 'RF': 32.0, 'LR': 31.0, 'RR': 31.0},
    CarClass.DEFAULT:      {'LF': 32.0, 'RF': 32.0, 'LR': 30.5, 'RR': 30.5},
}

PRESSURE_RISE = {
    CarClass.GT3: 2.5, CarClass.GT4: 2.3, CarClass.GTP: 3.0,
    CarClass.GTE: 2.8, CarClass.LMP2: 3.0, CarClass.PROTOTYPE: 2.8,
    CarClass.FORMULA: 3.5, CarClass.SUPER_FORMULA: 3.5,
    CarClass.PORSCHE_CUP: 2.5, CarClass.TCR: 2.0,
    CarClass.V8_SUPERCAR: 2.3, CarClass.STOCK: 2.0,
    CarClass.RALLY_CROSS: 1.8, CarClass.DIRT_OVAL: 1.5,
    CarClass.ROAD_ROOKIE: 2.0, CarClass.SPORTS_CAR: 2.2,
    CarClass.DEFAULT: 2.5,
}

FUEL_EFFECT_S_PER_KG = {
    CarClass.GT3: 0.035, CarClass.GT4: 0.030, CarClass.GTP: 0.040,
    CarClass.GTE: 0.036, CarClass.LMP2: 0.038, CarClass.PROTOTYPE: 0.037,
    CarClass.FORMULA: 0.025, CarClass.SUPER_FORMULA: 0.025,
    CarClass.PORSCHE_CUP: 0.032, CarClass.TCR: 0.028,
    CarClass.V8_SUPERCAR: 0.030, CarClass.STOCK: 0.020,
    CarClass.RALLY_CROSS: 0.022, CarClass.DIRT_OVAL: 0.018,
    CarClass.ROAD_ROOKIE: 0.025, CarClass.SPORTS_CAR: 0.028,
    CarClass.DEFAULT: 0.030,
}
