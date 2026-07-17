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
        # Note: Toyota GR86 is a spec cup car → classified under ROAD_ROOKIE
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
        'fia_f4', 'fiaf4', 'fia f4', 'f4',          # FIA F4
        'ray formula', 'formula_1600', 'ray_formula', # Ray Formula 1600
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
        'porsche_911_cup', '911_cup',                # iRacing display name match
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
        # NOTE: The Cadillac CTS-V Racecar is a RWD V8 sports/touring car, NOT a
        # front-wheel-drive TCR. Its keywords live under SPORTS_CAR below. Listing
        # 'ctsvr' here caused 'cadillacctsvr' to match TCR first (substring match).
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
        'street stock', 'streetstock', 'panther',  # Street Stock Panther
        'chevrolet silverado', 'chevy silverado',   # Silverado truck
    ],
    CarClass.RALLY_CROSS: [
        'rallycross', 'rally_cross',
        'crosscartn11', 'crosscar_tn11', 'cross_car', 'fia_cross',  # FIA Cross Car
        'vwbeetlegrc', 'vw_beetle_grc', 'beetle_grc',
        'subaruwrxsti', 'subaru_wrx',
        'fordfiestarswrc', 'ford_fiesta_wrc',
        'protrucks', 'pro2lite', 'pro2truck', 'pro4truck',
        'lucas oil off-road', 'off-road racing', 'pro-2 lite', 'pro_2_lite',  # Lucas Oil Pro-2 Lite
    ],
    CarClass.ROAD_ROOKIE: [
        'mx5', 'mx_5', 'miata', 'mazda mx-5', 'mazda mx5',
        'solstice',
        'specracer', 'spec_racer',
        'formulavee', 'formula_vee',
        'toyotagr86', 'toyota gr86', 'gr86',          # Toyota GR86 (road rookie/spec)
        'streetstock',
    ],
    CarClass.SPORTS_CAR: [
        'rufrt12r', 'ruf_rt12r',
        'fr500s', 'fr_500s',
        'kiaoptima', 'kia_optima',
        'jettatdi', 'jetta_tdi',
        'cadillacctsvr', 'cadillac_cts_vr', 'cadillac_cts', 'cts_v_racecar', 'ctsvr',
        'audi90gto', 'audi_90_gto',
        'astonmartin dbr9', 'aston_martin_dbr9',
    ],
}


def classify_car(car_name: str) -> CarClass:
    """Classify a car name string into a CarClass.

    Uses longest-keyword-wins: among every keyword that appears in the
    (normalised) car name, the longest, most specific one decides the class.
    This prevents a short generic keyword in an earlier class from shadowing
    a specific car defined in a later class (e.g. the generic 'gtp' keyword
    must not swallow the historic 'nissangtpzxt' prototype, nor 'trucks'
    swallow the off-road 'protrucks'). Ties fall to definition order.
    """
    lower = car_name.lower().replace(' ', '_').replace('-', '_')
    best_cls = CarClass.DEFAULT
    best_len = 0
    for cls, keywords in _CAR_KEYWORDS.items():
        for kw in keywords:
            if kw in lower and len(kw) > best_len:
                best_cls = cls
                best_len = len(kw)
    return best_cls


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

# ── Car class personality profiles ────────────────────────────────────────────

_CAR_CLASS_PROFILES = {
    CarClass.GT3: (
        "GT3 — RWD touring car with significant aerodynamic downforce and a sophisticated "
        "balance of mechanical and aero grip. The car has adjustable front and rear wings, "
        "full damper control, and a limited-slip differential. Key tuning levers are ARB "
        "balance (front vs rear roll stiffness), ride height (aero platform), and brake bias. "
        "GT3 cars are sensitive to camber on the front axle — inner tire temperatures rising "
        "quickly is the primary indicator of too much negative camber. The LSD power ramp "
        "directly affects corner exit traction and oversteer. ABS and TC are adjustable and "
        "should be tuned to the driver's braking and throttle style. Common failure: rear "
        "ARB too stiff causing snap oversteer on power application."
    ),
    CarClass.GT4: (
        "GT4 — RWD touring car with minimal aerodynamic adjustment (often fixed or limited "
        "wing options). Mechanical grip from springs, ARBs, and alignment dominates performance. "
        "The car has less power than GT3 but similar weight — traction out of slow corners is "
        "disproportionately important. Without significant aero adjustment, ARBs and spring "
        "rates are the primary balance tools. TC should be set conservatively as the car can "
        "wheelspin easily out of hairpins. Common failure: over-stiffening the rear to control "
        "body roll, which removes rear grip and causes understeer on entry."
    ),
    CarClass.GTP: (
        "GTP/Hypercar/LMDh — hybrid prototype with very high downforce, a hybrid power unit, "
        "and advanced aerodynamics. The car is extremely sensitive to ride height and aero "
        "platform — even 1mm of ride height change can shift balance noticeably. The hybrid "
        "deployment strategy affects tire temperatures and brake performance. Very stiff springs "
        "are normal for this class to maintain the aero platform. Brake bias management is "
        "critical because the regenerative braking (MGU-K) affects rear brake feel. "
        "Common failure: ride height too low causing the floor to ground, losing downforce suddenly."
    ),
    CarClass.GTE: (
        "GTE — Balance-of-Performance (BoP) regulated prototype-derived GT. Similar tuning "
        "philosophy to GT3 but with more downforce and higher speeds. Wing angles are often "
        "constrained by BoP. The car has a stiffer, more aero-dependent setup philosophy "
        "than GT3. Brake bias is important for the longer, heavier braking zones at GTE speeds. "
        "Common failure: running too low ride height to gain downforce, causing platform "
        "instability at high speed."
    ),
    CarClass.LMP2: (
        "LMP2 — Open prototype with very high downforce and ground effect. The car's "
        "aerodynamic platform is extremely important — springs are very stiff by road-car "
        "standards to maintain the floor height. ARB adjustment is the primary balance tool "
        "rather than springs. The car is very sensitive to setup changes and rewards precise "
        "driving. Tire temperatures build very quickly. Common failure: too much rear wing "
        "for a straight-line-speed-demanding circuit, costing lap time on long straights."
    ),
    CarClass.FORMULA: (
        "Formula car — single-seater with very high downforce and a peaky power band. "
        "Setup is very sensitive to weight distribution and aero balance. The car responds "
        "dramatically to wing angle changes — even 1 step can shift balance measurably. "
        "Spring rates are very high. The car must be set up for the driver's trail braking "
        "style — a driver who doesn't trail brake needs softer front springs for self-loading. "
        "Shifting is crucial — peaky NA engine loses significant power away from peak RPM. "
        "Common failure: rear wing too low for a technical circuit, causing instability."
    ),
    CarClass.SUPER_FORMULA: (
        "Super Formula — high-powered open-wheel formula car with sophisticated aerodynamics. "
        "Extremely sensitive to balance changes. The high power requires precise diff and TC "
        "setup for exit traction. Setup philosophy similar to Formula but with even higher "
        "sensitivity to small adjustments. Driver feedback on balance is critical."
    ),
    CarClass.PORSCHE_CUP: (
        "Porsche Cup — rear-engine layout fundamentally changes setup philosophy. Weight "
        "is biased to the rear, so the car naturally oversteers under power. Brake bias "
        "is normally lower (more rear) than mid-engine cars because rear weight provides "
        "more rear braking traction. The rear engine means trail braking can cause severe "
        "snap oversteer — setup should be conservative on entry balance. Front springs can "
        "be softer than normal as the nose is light. Common failure: brake bias too far "
        "forward, causing understeer on entry as the light front locks early."
    ),
    CarClass.TCR: (
        "TCR — Front-wheel drive touring car. All traction and steering comes from the front "
        "axle — front tire management is the entire challenge. Setup must balance front grip "
        "(for traction AND steering) which is inherently in conflict. Higher front camber "
        "improves cornering but hurts traction. Soft front ARB improves rotation but reduces "
        "traction on exit. The rear is passive — rear ARB and springs exist mainly to control "
        "body roll and corner entry balance. High brake bias (front) is normal for FWD. "
        "Common failure: front tires overheating because they handle all tasks simultaneously."
    ),
    CarClass.V8_SUPERCAR: (
        "V8 Supercar — heavy, high-powered RWD touring car with limited aerodynamic "
        "adjustment. Mechanical grip from springs and ARBs is paramount. The car has a "
        "live rear axle on some models — damper settings have a different character than "
        "independent suspension. Power oversteer is a significant risk on exit. Brake "
        "performance requires proper bias as the heavy car needs strong braking. "
        "Common failure: rear ARB too stiff causing the rear to hop over bumps."
    ),
    CarClass.STOCK: (
        "Stock car/NASCAR — oval-specific setup with stagger, wedge, and track bar as "
        "primary tools. The car is set up to turn left continuously — left-side bias in "
        "weight and stagger are fundamental. On road courses, setup transitions to a "
        "conventional road-course approach but the car remains heavy and power-rich. "
        "Tire management over long oval stints is the primary strategic consideration. "
        "Common failure: setup optimized for early-lap grip that wears tires rapidly, "
        "causing major late-run balance problems."
    ),
    CarClass.RALLY_CROSS: (
        "Rallycross car — AWD with active traction systems for mixed-surface racing. "
        "Setup must compromise between dirt and tarmac sections. Lower pressures for "
        "dirt, softer suspension for compliance over loose surfaces. "
        "The AWD system reduces oversteer risk on tarmac but dirt requires very different "
        "throttle application — earlier and more progressive to avoid wheelspin."
    ),
    CarClass.ROAD_ROOKIE: (
        "Road rookie / entry-level car (MX-5, Skippy, etc.) — lightweight, limited power, "
        "narrow tires. Setup changes have an outsized effect because there is so little "
        "overall grip. The driver's inputs matter far more than the setup — small setup "
        "changes that would be barely noticeable in a GT3 are very noticeable here. "
        "Keep setup simple and predictable. Focus on balance and smooth inputs. "
        "Common failure: over-camber causing the already-narrow tires to overheat."
    ),
    CarClass.DEFAULT: (
        "General road-course car — setup priorities are balanced grip, predictable balance, "
        "and appropriate wing for the track's speed demands. Start from the class baseline "
        "and adjust from telemetry data."
    ),
}


def car_class_profile_text(car_class: CarClass) -> str:
    """
    Return a paragraph describing what makes this car class unique from a setup
    perspective. Used in AI setup builder prompts so Claude understands the car's
    character before suggesting values.
    """
    return _CAR_CLASS_PROFILES.get(car_class, _CAR_CLASS_PROFILES[CarClass.DEFAULT])
