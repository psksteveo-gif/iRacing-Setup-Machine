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
    DEFAULT = "default"


# Keywords in iRacing car path names → class
_CAR_KEYWORDS = {
    CarClass.GT3: [
        'gt3', 'mercedes_amg_gt3', 'ferrari_296_gt3', 'bmw_m4_gt3',
        'porsche_911_gt3_r', 'audi_r8_gt3', 'mclaren_720s_gt3',
        'lamborghini_huracan_gt3', 'aston_martin_vantage_gt3',
        'corvette_c8r', 'ford_gt_gt3',
    ],
    CarClass.GT4: [
        'gt4', 'bmw_m4_gt4', 'mclaren_570s_gt4', 'porsche_718_gt4',
        'mercedes_amg_gt4', 'aston_martin_gt4',
    ],
    CarClass.GTP: [
        'gtp', 'hypercar', 'lmdh', 'porsche_963', 'cadillac_vr',
        'acura_arx06', 'bmw_mhybrid', 'toyota_gr010',
    ],
    CarClass.LMP2: [
        'lmp2', 'dallara_p217', 'oreca_07',
    ],
    CarClass.FORMULA: [
        'formula', 'dallara_f3', 'dallara_ir18', 'ir18',
        'superformula', 'sf23', 'w12', 'w13',
        'skipbarber', 'usf2000', 'pm18', 'ir04',
    ],
    CarClass.PORSCHE_CUP: [
        'porsche_992', 'porsche_cup', '992_cup',
    ],
    CarClass.TCR: [
        'tcr', 'civic_tcr', 'elantra_tcr', 'veloster_tcr', 'hyundai_tcr', 'honda_civic_si',
    ],
    CarClass.STOCK: [
        'nascar', 'nextgen', 'stockcar', 'impala', 'camaro_nascar',
        'mustang_nascar', 'toyota_camry_nascar', 'truck', 'arca',
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


# Class-specific parameters for analysis modules
PRESSURE_TARGETS = {
    CarClass.GT3:         {'LF': 33.5, 'RF': 33.5, 'LR': 32.0, 'RR': 32.0},
    CarClass.GT4:         {'LF': 33.0, 'RF': 33.0, 'LR': 31.5, 'RR': 31.5},
    CarClass.GTP:         {'LF': 27.0, 'RF': 27.0, 'LR': 25.0, 'RR': 25.0},
    CarClass.LMP2:        {'LF': 27.5, 'RF': 27.5, 'LR': 25.5, 'RR': 25.5},
    CarClass.FORMULA:     {'LF': 26.5, 'RF': 26.5, 'LR': 24.0, 'RR': 24.0},
    CarClass.PORSCHE_CUP: {'LF': 33.0, 'RF': 33.0, 'LR': 31.0, 'RR': 31.0},
    CarClass.TCR:         {'LF': 34.0, 'RF': 34.0, 'LR': 32.5, 'RR': 32.5},
    CarClass.STOCK:       {'LF': 35.0, 'RF': 35.0, 'LR': 34.0, 'RR': 34.0},
    CarClass.DEFAULT:     {'LF': 32.0, 'RF': 32.0, 'LR': 30.5, 'RR': 30.5},
}

PRESSURE_RISE = {
    CarClass.GT3: 2.5, CarClass.GT4: 2.3, CarClass.GTP: 3.0,
    CarClass.LMP2: 3.0, CarClass.FORMULA: 3.5, CarClass.PORSCHE_CUP: 2.5,
    CarClass.TCR: 2.0, CarClass.STOCK: 2.0, CarClass.DEFAULT: 2.5,
}

FUEL_EFFECT_S_PER_KG = {
    CarClass.GT3: 0.035, CarClass.GT4: 0.030, CarClass.GTP: 0.040,
    CarClass.LMP2: 0.038, CarClass.FORMULA: 0.025, CarClass.PORSCHE_CUP: 0.032,
    CarClass.TCR: 0.028, CarClass.STOCK: 0.020, CarClass.DEFAULT: 0.030,
}
