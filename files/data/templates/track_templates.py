"""
Track Templates & Setup Baselines
Provides baseline setup templates for different car/track combinations.
Covers all iRacing road, oval, dirt, and rallycross venues.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TrackInfo:
    name: str
    downforce_demand: str = "medium"    # "low", "medium", "high"
    tire_stress: str = "medium"         # "low", "medium", "high"
    surface: str = "paved"              # "paved", "dirt", "mixed"
    track_type: str = "road"            # "road", "oval", "rallycross", "street"
    notes: Optional[str] = None
    # ── Enriched setup context (used by AI setup builder) ─────────────────
    setup_guidance: Optional[str] = None   # 3-5 sentences on what the setup must do at this track
    key_priorities: Optional[List[str]] = None  # ordered list of most important setup decisions


@dataclass
class SetupTemplate:
    # ── Legacy text fields (kept for backward compat) ──────────────────────
    front_wing: Optional[str] = None
    rear_wing: Optional[str] = None
    tire_pressures_psi: Optional[Dict[str, float]] = None
    camber_deg: Optional[Dict[str, float]] = None
    spring_notes: Optional[str] = None
    arb_notes: Optional[str] = None
    ride_height_notes: Optional[str] = None
    damper_notes: Optional[str] = None
    brake_bias_pct: Optional[float] = None
    key_adjustments: Optional[List[str]] = None
    priority_notes: Optional[str] = None

    # ── Numeric fields — used by get_baseline_setup_text for AI prompts ────
    # Wings (step numbers)
    wing_front_step: Optional[int] = None
    wing_rear_step: Optional[int] = None

    # Toe (mm; negative = toe-out, positive = toe-in)
    toe_front_mm: Optional[float] = None
    toe_rear_mm: Optional[float] = None

    # Spring rates (N/mm; lb/in for stock class)
    spring_lf: Optional[float] = None
    spring_rf: Optional[float] = None
    spring_lr: Optional[float] = None
    spring_rr: Optional[float] = None
    spring_unit: str = "N/mm"

    # ARBs (1–7 clicks; 1=softest)
    arb_front: Optional[int] = None
    arb_rear: Optional[int] = None

    # Ride heights (mm)
    rh_lf: Optional[float] = None
    rh_rf: Optional[float] = None
    rh_lr: Optional[float] = None
    rh_rr: Optional[float] = None

    # Slow-speed dampers (clicks; 1=softest)
    bump_slow_lf: Optional[int] = None
    bump_slow_rf: Optional[int] = None
    bump_slow_lr: Optional[int] = None
    bump_slow_rr: Optional[int] = None

    # Fast-speed dampers (clicks)
    bump_fast_lf: Optional[int] = None
    bump_fast_rf: Optional[int] = None
    bump_fast_lr: Optional[int] = None
    bump_fast_rr: Optional[int] = None

    # Slow rebound (clicks)
    rebound_slow_lf: Optional[int] = None
    rebound_slow_rf: Optional[int] = None
    rebound_slow_lr: Optional[int] = None
    rebound_slow_rr: Optional[int] = None

    # Fast rebound (clicks)
    rebound_fast_lf: Optional[int] = None
    rebound_fast_rf: Optional[int] = None
    rebound_fast_lr: Optional[int] = None
    rebound_fast_rr: Optional[int] = None

    # Differential
    diff_preload_nm: Optional[float] = None
    diff_power_deg: Optional[float] = None
    diff_coast_deg: Optional[float] = None

    # Electronics (0–9 levels)
    tc_1: Optional[int] = None
    abs_setting: Optional[int] = None
    brake_pressure_pct: Optional[float] = None


# ── Track Database ────────────────────────────────────────────────────────────
# Covers all major iRacing venues.  Fuzzy-matched by _find_track().

_TRACKS: Dict[str, TrackInfo] = {
    # ── North America — Road Courses ──────────────────────────────────────
    "Sebring International Raceway": TrackInfo(
        "Sebring International Raceway", "medium", "high",
        notes="Bumpy surface stresses tires and suspension. Softer springs help compliance.",
        setup_guidance=(
            "Sebring's concrete-and-asphalt patchwork surface is the defining challenge — the car "
            "must absorb constant sharp bumps without losing platform stability. Softer slow-bump "
            "damping is essential, especially on the rear, to keep tires planted over the worst "
            "sections between T1 and T7. The long high-speed right at T17 rewards rear stability "
            "and consistent tire temps. Tire wear is severe — keep temperatures even across the "
            "contact patch and be conservative with cold pressures to allow for longer heat build-up."
        ),
        key_priorities=[
            "Bump compliance — slow bump damping softer than normal to absorb surface",
            "Rear stability for T17 high-speed right",
            "Tire temp management — even spread to survive long stints",
            "Consistent brake performance over bumps at T1 and T10",
            "Ride height — must clear severe bump crests without bottoming",
        ],
    ),
    "Road America": TrackInfo(
        "Road America", "medium", "medium",
        notes="Long track with varied speed corners. Balanced setup needed.",
        setup_guidance=(
            "Road America demands a true compromise setup — the long, flat-out Kettle Bottoms (T5–T6) "
            "and Canada Corner (T12) need high-speed stability and rear confidence, while the "
            "tight Turn 1 hairpin and the chicane at T8/T9 need good rotation and braking stability. "
            "Wing choice is a straight-line vs cornering trade-off; medium is the correct starting "
            "point. The long straights make gearing important — ensure top gear is long enough to "
            "avoid rev-limiter contact on the back straight."
        ),
        key_priorities=[
            "High-speed stability through Kettle Bottoms and Canada Corner",
            "Braking stability into T1 hairpin and T8 chicane entry",
            "Wing balance — medium level, avoid over-winging for back straight speed",
            "Rotation at T1 and T11 hairpins — key for lap time",
            "Gearing — long enough to avoid limiter on back straight",
        ],
    ),
    "Road Atlanta": TrackInfo(
        "Road Atlanta", "medium", "high",
        notes="Fast downhill esses into heavy braking. Rear stability critical.",
        setup_guidance=(
            "Road Atlanta's defining moment is the downhill esses (T2–T4) followed by the blind "
            "flat-out T5 commitment and the massive braking into T10a. The rear must be planted and "
            "predictable through the esses — any oversteer there is very dangerous. Braking "
            "stability into T10a is critical; the car arrives very fast downhill. The long back "
            "straight from T10b to T12 means moderate wing. Tire stress comes from the repeated "
            "high-lateral-G esses — watch front-left temperature especially."
        ),
        key_priorities=[
            "Rear stability through downhill esses T2–T4",
            "Braking stability and nosedive control into T10a",
            "Front-left tire temperature management (most loaded corner)",
            "Wing level — moderate for back straight speed vs esses stability",
            "Ride height front — enough clearance for the esses dip",
        ],
    ),
    "Laguna Seca": TrackInfo(
        "Laguna Seca", "medium", "medium",
        notes="The corkscrew demands good braking stability. Medium downforce.",
        setup_guidance=(
            "Laguna Seca is dominated by two corners: the Andretti hairpin (T2) where hard braking "
            "stability is key, and the Corkscrew (T8a–T8b) which is entered blind at speed and "
            "drops sharply mid-corner. The Corkscrew punishes understeer on entry and oversteer on "
            "exit equally — the car needs excellent mid-corner balance. The final complex (T9–T11) "
            "requires strong drive out for the back straight. Front tires are highly loaded; "
            "managing front temperatures and camber is critical for the final stint."
        ),
        key_priorities=[
            "Corkscrew balance — neutral entry, stable exit over the drop",
            "Braking stability into T2 Andretti hairpin",
            "Front tire temperature management across the session",
            "Drive out of T11 for back straight — diff and rear ARB",
            "Mechanical grip in slow corners — T4 and T9",
        ],
    ),
    "Watkins Glen International": TrackInfo(
        "Watkins Glen International", "medium", "medium",
        notes="Fast flowing layout. Good aero balance critical through esses.",
        setup_guidance=(
            "Watkins Glen's long esses complex (T1–T4) taken flat or near-flat is the defining "
            "challenge — the car needs superb high-speed aero balance and predictable response to "
            "small steering inputs at 200+ km/h. The boot section (T6–T10) has a mix of medium-speed "
            "corners where mechanical grip matters more. Braking into T1 (after the long front "
            "straight) and into T6 (The Toe) are heavy braking zones where stability is key. "
            "The track is smooth and forgiving — setup can be a touch stiffer than usual."
        ),
        key_priorities=[
            "Esses aero balance — car must be stable and neutral at high speed",
            "Braking stability into T1 and T6",
            "Rear confidence through the uphill esses",
            "Mechanical grip in boot section T6–T10",
            "Spring/damper stiffness — smoother track can handle stiffer setup",
        ],
    ),
    "Virginia International Raceway": TrackInfo(
        "Virginia International Raceway", "medium", "high",
        notes="Technical with elevation changes. Tire management is key.",
        setup_guidance=(
            "VIR's North Course mixes elevation changes with a variety of corner types — from the "
            "fast, slightly blind Oak Tree Turn (T13) which is the fastest corner and demands rear "
            "stability, to the tight infield hairpins at T1 and T8 where rotation matters. "
            "Significant elevation changes through the Roller Coaster section (T4–T6) mean the "
            "suspension must manage weight transfer under combined braking and cornering. Tire "
            "degradation is significant — front tires take the most punishment through Oak Tree. "
            "Manage cold pressures conservatively for long stint consistency."
        ),
        key_priorities=[
            "Rear stability through Oak Tree Turn (T13) — fastest and most loaded",
            "Rotation at T1 and T8 hairpins — lap time comes from exit speed",
            "Suspension compliance through the Roller Coaster elevation section",
            "Front tire wear management over long runs",
            "Brake stability into T1 after long front straight",
        ],
    ),
    "Circuit of the Americas": TrackInfo(
        "Circuit of the Americas", "high", "high",
        notes="Long track with high-speed S-curves. High downforce and tire care needed.",
        setup_guidance=(
            "COTA demands high downforce — the high-speed S1 (T3–T9) complex and Turn 12 are "
            "both flat-out or near-flat and punish any nervousness. T1 is a massive braking zone "
            "followed immediately by a high-speed apex — braking stability and nose turn-in are "
            "critical together. The stadium section (T12–T16) has slow to medium hairpins where "
            "mechanical grip and traction dominate. Tire stress is very high on both axles — "
            "managing temps across 40+ laps requires balanced camber and even pressure distribution. "
            "The long back straight (T11 to T12) makes gearing relevant."
        ),
        key_priorities=[
            "High downforce — S1 and T12 are both stability critical",
            "Braking and nose turn-in at T1 — the single most important corner",
            "Traction out of stadium section hairpins T12–T16",
            "Even tire temperature distribution for long stint management",
            "Rear stability through T12 high-speed left",
        ],
    ),
    "Sonoma Raceway": TrackInfo(
        "Sonoma Raceway", "medium", "high",
        notes="Elevation changes and tight turns. Good mechanical grip required.",
        setup_guidance=(
            "Sonoma is a tight, hilly track where mechanical grip matters more than aerodynamics. "
            "The Carousel (T7) is a long, slow constant-radius right that loads the front-left "
            "heavily — camber and ARB balance through this corner defines the car's character. "
            "The hairpin at T4 (Turn 4) and the final turn need strong drive, so diff and rear "
            "setup are important for exit. The significant elevation through the esses (T2–T3) "
            "means the suspension must manage variable weight distribution. Front tires wear quickly "
            "from the constant slow-corner loading through the Carousel."
        ),
        key_priorities=[
            "Front-left load through the Carousel (T7) — camber and front ARB",
            "Traction out of T4 and final hairpin",
            "Mechanical grip through esses — aero is less critical than suspension",
            "Front tire temperature management (Carousel stress)",
            "Braking stability down the hill into T4",
        ],
    ),
    "Portland International Raceway": TrackInfo(
        "Portland International Raceway", "medium", "medium",
        notes="Technical layout with chicane. Medium downforce, smooth inputs.",
        setup_guidance=(
            "Portland is a tight, flat circuit where rotation and traction dominate. The chicane "
            "(T1–T2) must be taken smoothly — understeer at entry or oversteer at exit both cost "
            "time down the long straight. Turn 7 (the hairpin) is the primary overtaking point "
            "and needs strong braking stability and good drive. The infield section is slow and "
            "mechanical grip is everything — softer ARBs improve rotation through these corners. "
            "The surface is relatively smooth, so setup can prioritize rotation over compliance."
        ),
        key_priorities=[
            "Rotation through the infield hairpins — front ARB and diff",
            "Braking stability into T7 hairpin",
            "Smooth chicane balance — neutral entry, strong exit",
            "Rear traction out of T7 for long back straight",
            "Medium wing — long straight penalizes over-winging",
        ],
    ),
    "Lime Rock Park": TrackInfo(
        "Lime Rock Park", "medium", "high",
        notes="Short track, constant action. High tire stress from non-stop cornering.",
        setup_guidance=(
            "Lime Rock is tiny and relentless — there is almost no straight recovery time for "
            "tires. The Big Bend (T1) at the end of the front straight is a medium-speed right "
            "where entry balance defines the lap. The downhill section and sweeper through the "
            "bottom (T3–T4) loads both axles and rewards a planted rear. The uphill hairpin "
            "return (T5) is critical for lap time — strong drive here feeds the entire front "
            "straight. Tire temperatures will be consistently high — manage cold pressures low "
            "and camber aggressively for even contact patch loading."
        ),
        key_priorities=[
            "Entry balance at Big Bend T1 — most lap time here",
            "Rear stability through bottom sweeper T3–T4",
            "Drive out of T5 uphill hairpin — feeds entire straight",
            "Tire temperature management — no recovery time between corners",
            "Lower cold pressures to manage continuous heat build-up",
        ],
    ),
    "Long Beach Street Circuit": TrackInfo(
        "Long Beach Street Circuit", "high", "medium", "paved", "street",
        notes="Tight street circuit with walls. High downforce, cautious approach.",
        setup_guidance=(
            "Long Beach is all about mechanical grip and confidence near the walls. There is no "
            "margin for error — the tight hairpin at T1 and the 90° at T4 both have walls very "
            "close. High downforce helps turn-in and braking but the short straights limit top "
            "speed loss. The surface is bumpy with concrete expansion joints — softer bump damping "
            "prevents the car from getting knocked off line. Brake balance is important because "
            "several braking zones are short with immediate apex commitment. Street tire durability "
            "suffers on the abrasive concrete — manage temperatures closely."
        ),
        key_priorities=[
            "Mechanical grip — walls demand confidence, not aero",
            "Bump compliance for concrete expansion joints",
            "Brake stability into T1 and T4 with walls nearby",
            "High downforce for multiple slow-speed turns",
            "Tire wear management on abrasive concrete surface",
        ],
    ),
    "Willow Springs": TrackInfo(
        "Willow Springs", "medium", "high",
        notes="Fast and flowing with big elevation. High tire degradation.",
        setup_guidance=(
            "Willow Springs (Streets of Willow or Big Willow) is a fast, sweeping track with "
            "significant elevation change. Big Willow's long, fast Turn 9 right-hander is the "
            "defining corner — high-speed, banked, and taken near flat, it loads the front-right "
            "heavily and demands rear stability and front confidence together. The track is very "
            "abrasive and tire wear is aggressive — running conservative camber to maintain "
            "contact patch is more valuable than peak lap time. Ride height needs to clear the "
            "compression at the bottom of the elevation changes without bottoming."
        ),
        key_priorities=[
            "Rear stability through T9 fast right (biggest corner)",
            "Front-right tire temperature management (most loaded)",
            "Conservative camber for contact patch preservation over long runs",
            "Ride height to clear elevation compressions",
            "Balanced aero — multiple high-speed sections reward it equally",
        ],
    ),
    "Mexico City": TrackInfo(
        "Mexico City", "medium", "medium",
        notes="High altitude reduces aero grip. Slightly higher wing to compensate.",
        setup_guidance=(
            "Mexico City's altitude (~2,200m) reduces air density by roughly 20%, which directly "
            "cuts aerodynamic downforce by the same amount. Wings should be set 1–2 steps higher "
            "than a comparable sea-level track to compensate. The Peraltada (T17) is a long, fast "
            "banked right — without sufficient downforce, the car feels lighter and more nervous "
            "here than at sea level. Engine power is also reduced at altitude. Tire pressures will "
            "run slightly lower than usual because thinner air cools the tires more slowly — "
            "reduce cold pressures by 0.5–1 psi from normal baselines."
        ),
        key_priorities=[
            "Increase wing angles 1–2 steps above sea-level baseline (altitude aero loss)",
            "Rear stability through Peraltada T17 banked right",
            "Reduce cold tire pressures 0.5–1 psi (altitude cooling effect)",
            "Brake cooling — thinner air reduces brake cooling efficiency",
            "Engine mapping — reduced power at altitude, shift points may need adjustment",
        ],
    ),
    # ── North America — Ovals ─────────────────────────────────────────────
    "Daytona International Speedway": TrackInfo(
        "Daytona International Speedway", "low", "medium", "paved", "oval",
        notes="Long straights with banking. Low downforce setup, focus on top speed.",
        setup_guidance=(
            "Daytona is a superspeedway where aerodynamics dominate — minimize drag for maximum "
            "top speed on the 3.8km trioval. The banking (31° in the turns) provides natural "
            "downforce so wing angles can be very low. The car must be stable in traffic and "
            "through the banked turns at 300+ km/h. For the road course layout, treat it as a "
            "medium-downforce track with oval-style tire management. Draft sensitivity is extreme "
            "on the oval — setup for clean-air pace and adjust strategy for drafting."
        ),
        key_priorities=[
            "Minimize drag — low wing angles, smooth underbody",
            "Oval: high-speed stability in banking at 300+ km/h",
            "Tire stagger management for oval configuration",
            "Draft awareness — setup for both clean air and in-draft stability",
            "Brake ducting — minimal for oval (little braking), more for road course",
        ],
    ),
    "Indianapolis Motor Speedway": TrackInfo(
        "Indianapolis Motor Speedway", "low", "medium", "paved", "oval",
        notes="Oval — low drag, focus on mechanical grip and tire management.",
        setup_guidance=(
            "Indy's flat oval (9° banking) demands mechanical grip more than aerodynamics — the "
            "banking is too shallow to generate useful downforce, so the car must work on its "
            "springs, ARBs, and alignment. A slight push (understeer) is preferred to keep the "
            "car off the wall. Tire wear is predominantly on the right side — right-side pressures "
            "need careful management. For the road course, the infield section is tight and "
            "technical, requiring good rotation, while the oval straight uses much less wing."
        ),
        key_priorities=[
            "Mechanical grip — flat oval, aero is secondary",
            "Slight understeer bias to keep car off the wall",
            "Right-side tire pressure management (oval loading)",
            "Road course: low drag setting for long oval straight",
            "Brake balance — oval has minimal braking, road course has heavy zones",
        ],
    ),
    "Phoenix Raceway": TrackInfo(
        "Phoenix Raceway", "medium", "high", "paved", "oval",
        notes="Short oval with dogleg. Tire wear critical, manage stagger.",
        setup_guidance=(
            "Phoenix is a short, flat oval with variable banking (9° in turns 1–2, 11° in 3–4) "
            "and a distinct egg shape. The dogleg on the front straight creates an unusual aero "
            "challenge. Tire wear is severe on the short oval — track position and tire management "
            "over a long run are more important than qualifying pace. The car tends to get tight "
            "(understeer) as tires wear — setup with a slightly free (oversteer) initial balance "
            "so the car tightens to neutral mid-stint. Wedge adjustment is a key in-race tool."
        ),
        key_priorities=[
            "Stagger — critical for tight turns at Phoenix",
            "Initial slight oversteer bias that tightens to neutral as tires wear",
            "Tire wear management — very aggressive surface",
            "Wedge and track bar for balance adjustment during race",
            "Brake management — short oval with heavy braking into turns",
        ],
    ),
    "Pocono Raceway": TrackInfo(
        "Pocono Raceway", "low", "medium", "paved", "oval",
        notes="Three distinct turns, each unique banking. Versatile setup.",
        setup_guidance=(
            "Pocono's three totally different corners (Turn 1 — Tunnel Turn, steeply banked; "
            "Turn 2 — Long Pond, sweeping; Turn 3 — Southern, tightest) demand a true compromise "
            "oval setup. No single corner dominates, so a balanced mechanical setup is needed. "
            "The long straights between the turns allow good straight-line speed with low wing. "
            "Tire wear is uneven across the three turns — monitor all four corners independently "
            "and manage pressures accordingly."
        ),
        key_priorities=[
            "Compromise setup balancing three very different turns",
            "Low wing for long straights between turns",
            "Mechanical grip — banking varies so aero is inconsistent",
            "Monitor tire wear per corner — Tunnel Turn vs Southern are very different",
            "Brake cooling for T1 and T3 entry from long straights",
        ],
    ),
    "Lakeland Speedway": TrackInfo(
        "Lakeland Speedway", "medium", "medium", "paved", "oval",
        notes="Short oval for stock car beginners.",
        setup_guidance=(
            "Lakeland is a short, flat oval suitable for learning short-track oval technique. "
            "Mechanical grip and simple, reliable setup takes priority. Consistent brake points "
            "and corner exit traction dominate lap time. Stagger and wedge are the primary "
            "adjustment tools."
        ),
        key_priorities=[
            "Stagger for oval cornering",
            "Corner exit traction — feeds short straights",
            "Consistent braking — short braking zones into tight turns",
            "Simple, reliable setup — prioritize consistency over peak performance",
        ],
    ),
    "Southern National Motorsports Park": TrackInfo(
        "Southern National Motorsports Park", "medium", "medium", "paved", "oval",
        notes="Short track oval. Tight racing, focus on corner exit.",
        setup_guidance=(
            "Southern National is a short, flat short-track oval. The tight turns and short "
            "straights mean corner exit traction and car rotation are everything. A free (slightly "
            "oversteering) entry balance helps rotation, transitioning to understeer on exit to "
            "plant the rear for drive. Tire management on the abrasive surface is critical."
        ),
        key_priorities=[
            "Corner entry rotation — slight oversteer for tight oval",
            "Corner exit traction — diff and rear springs",
            "Tire wear on abrasive surface",
            "Stagger management",
            "Wedge and track bar for in-race balance adjustment",
        ],
    ),
    # ── Europe ────────────────────────────────────────────────────────────
    "Spa-Francorchamps": TrackInfo(
        "Spa-Francorchamps", "medium", "medium",
        notes="Mix of high-speed and technical sections. Balanced aero approach.",
        setup_guidance=(
            "Spa is the ultimate balanced circuit — Eau Rouge/Raidillon is taken flat or near-flat "
            "and demands rear stability and confidence at 250+ km/h, while the tight Bus Stop "
            "chicane and La Source hairpin need rotation and braking stability. Pouhon (T10) is a "
            "high-speed double-left where rear grip is essential. The Kemmel Straight requires "
            "enough top speed to not lose time, making over-winging costly. Rear tire temperatures "
            "build quickly through Pouhon and the Eau Rouge compression — monitor both axles."
        ),
        key_priorities=[
            "Rear stability through Eau Rouge/Raidillon flat at high speed",
            "Rear confidence at Pouhon double-left T10",
            "Rotation at La Source hairpin and Bus Stop chicane",
            "Wing balance — enough for Pouhon, not too much for Kemmel Straight",
            "Rear tire temperature management (Pouhon loading)",
        ],
    ),
    "Monza": TrackInfo(
        "Monza", "low", "medium",
        notes="Ultimate low-downforce track. Minimize drag for straight-line speed.",
        setup_guidance=(
            "Monza has the lowest wing requirement of any track — the three main chicanes (T1, "
            "T4, T8) are the only real braking zones, and the rest is full throttle. Minimize wing "
            "to absolute minimum for top speed on the Ascari straight and main straight. Brake "
            "stability into the chicanes is critical — they come at the end of 200+ km/h straights. "
            "The curbs at the chicanes are very aggressive and can destabilize the car — bump "
            "damping and ride height must allow absorbing the curbs without losing control. "
            "Tire wear is minimal — focus entirely on braking performance and straight-line speed."
        ),
        key_priorities=[
            "Absolute minimum drag — lowest legal wing angles",
            "Braking stability into all three chicanes",
            "Curb compliance — bump damping and ride height for Lesmo and chicane curbs",
            "Brake cooling — very heavy repeated braking from high speed",
            "Tire temps stay low — focus on braking, not tire management",
        ],
    ),
    "Nürburgring GP": TrackInfo(
        "Nürburgring GP", "medium", "medium",
        notes="Technical layout demanding good mechanical grip.",
        setup_guidance=(
            "The Nürburgring GP circuit is a compact technical track where mechanical grip matters "
            "more than aerodynamics. The Mercedes Arena infield (T1–T6) is a slow, tight complex "
            "where rotation and traction dominate. The main straight into T1 is the primary "
            "overtaking zone — braking stability is critical. The Ford Kurve complex later in the "
            "lap is medium-speed and requires a balanced car. Medium wing balances the short "
            "straight speed with the technical infield requirements."
        ),
        key_priorities=[
            "Rotation through the Mercedes Arena infield complex",
            "Braking stability into T1 from the long main straight",
            "Traction out of slow corners — diff setup is important",
            "Medium wing — balanced between straights and infield",
            "Mechanical grip — track rewards compliance over aero stiffness",
        ],
    ),
    "Nürburgring Nordschleife": TrackInfo(
        "Nürburgring Nordschleife", "high", "high",
        notes="20+ km of extreme challenges. High downforce and forgiving suspension.",
        setup_guidance=(
            "The Nordschleife is unique — 20.8 km of constantly changing surfaces, blind crests, "
            "compression bumps, and camber changes. The setup priority is a forgiving, planted car "
            "that the driver can trust through blind corners. Softer springs and more bump travel "
            "are essential to handle the surface changes — stiffness that works at normal tracks "
            "will destabilize the car here. High downforce for Karussell, Kesselchen, and "
            "Schwedenkreuz where the car goes fast and blind. Ride heights must be set to clear "
            "the many compressions without bottoming — very generous clearance needed."
        ),
        key_priorities=[
            "Forgiving, planted character — driver must trust the car blind",
            "Soft springs with generous travel to absorb surface changes",
            "High downforce — multiple high-speed blind sections",
            "Generous ride height clearance for compressions",
            "Rear stability — many high-speed blind corners where oversteer is fatal",
        ],
    ),
    "Nürburgring Combined": TrackInfo(
        "Nürburgring Combined", "high", "high",
        notes="Nordschleife + GP circuit. Extreme elevation, bumps, and blind corners. Max downforce.",
        setup_guidance=(
            "The Combined layout adds the GP circuit to the Nordschleife, making for an extreme "
            "endurance challenge. All Nordschleife setup priorities apply: forgiving compliance, "
            "high downforce, generous ride height clearance. The GP addition means braking "
            "performance into the GP infield corners must also be managed. Tire wear over such "
            "a long lap becomes critical — consistent temperatures and conservative initial "
            "pressures for long stints."
        ),
        key_priorities=[
            "All Nordschleife priorities apply — compliance and trust",
            "Generous ride height for severe compressions",
            "High downforce across all high-speed sections",
            "Tire management — very long lap stresses all corners",
            "Brake performance for GP section infield braking zones",
        ],
    ),
    "Silverstone Circuit": TrackInfo(
        "Silverstone Circuit", "high", "medium",
        notes="High-speed corners demand downforce. Maggots-Becketts is the key.",
        setup_guidance=(
            "Silverstone is defined by the Maggots-Becketts-Chapel complex (T5–T7) — a long, "
            "high-speed sequence taken at 200+ km/h with rapid direction changes. The car must "
            "be planted and responsive simultaneously — high downforce with a stiff chassis to "
            "resist roll through the direction changes. Copse (T1) is flat-out and needs rear "
            "confidence. Stowe and the Vale complex (T14–T15) are medium-speed heavy braking "
            "zones. The Abbey complex and Brooklands are slow-speed entry where mechanical grip "
            "and rotation matter. Rear tire wear is significant through the high-speed sections."
        ),
        key_priorities=[
            "Rear stability through Maggots-Becketts-Chapel at 200+ km/h",
            "Flat-out Copse confidence — rear must be totally planted",
            "Stiff chassis to resist direction changes through Becketts",
            "Braking stability into Stowe and Vale complex",
            "Rear tire management through continuous high-speed loading",
        ],
    ),
    "Circuit de Barcelona-Catalunya": TrackInfo(
        "Circuit de Barcelona-Catalunya", "medium", "high",
        notes="Tire degradation track. Manage rear tire stress in final sector.",
        setup_guidance=(
            "Barcelona is notorious for rear tire degradation — the long T3 right-hander (taken "
            "near flat) and T5 right continuously load the right-rear. The setup must balance "
            "peak corner speed with tire longevity. Turn 1 is a heavy braking zone and requires "
            "stable entry. T9 (the very long hairpin exit) is where most lap time is found — "
            "the car must have strong drive out of the hairpin to maximize the following sector. "
            "The final chicane T15–T16 is tight and feeds the long main straight — good rotation "
            "and exit speed here is essential."
        ),
        key_priorities=[
            "Rear tire management — T3 and T5 stress the right-rear continuously",
            "Right-rear temperature control — key to stint length",
            "Drive out of T9 hairpin — most important traction zone",
            "Braking stability into T1 and T10",
            "Balance between peak lap time and tire conservation",
        ],
    ),
    "Imola": TrackInfo(
        "Imola", "medium", "medium",
        notes="Technical old-school circuit. Kerb riding important.",
        setup_guidance=(
            "Imola is a flowing, technical circuit with limited run-off — the setup must work "
            "across different corner types. Tamburello (T1 chicane) is a heavy braking zone where "
            "stability counts. Piratella (T9) is a fast left taken at near-flat where rear "
            "confidence is essential. The Rivazza hairpins (T15–T16) feed the long main straight "
            "— exit speed here is critical. Kerb riding is important at Imola; the car must absorb "
            "kerbs without losing composure, requiring softer bump damping than might seem ideal "
            "for the corner speeds involved."
        ),
        key_priorities=[
            "Rear stability through Piratella fast left",
            "Drive out of Rivazza hairpins for main straight speed",
            "Kerb compliance — bump damping must absorb aggressive kerb use",
            "Braking stability into Tamburello chicane",
            "Balanced aero — medium wing for the mix of high and low speed",
        ],
    ),
    "Le Mans 24h Circuit": TrackInfo(
        "Le Mans 24h Circuit", "low", "medium",
        notes="Mulsanne straight demands low drag. Porsche curves need some downforce.",
        setup_guidance=(
            "Le Mans requires the ultimate drag-vs-downforce compromise. The Mulsanne straight "
            "(8km effectively) demands absolute minimum drag — every wing degree costs a large "
            "amount of top speed. However, the Porsche Curves (T16–T18) are taken at very high "
            "speed and need genuine downforce to be safe. The Ford Chicanes (T9–T11) and Mulsanne "
            "Corner need braking stability. Night sessions bring cooler track temperatures — "
            "increase cold pressures 0.5 psi for night running. The 24h context means tire "
            "conservation over 4+ hour stints is worth more than peak lap time."
        ),
        key_priorities=[
            "Absolute minimum drag for Mulsanne — most impactful single decision",
            "Rear stability through Porsche Curves at very high speed",
            "Braking stability into Ford Chicanes and Mulsanne Corner",
            "Night/temperature adjustment — higher cold pressures for night",
            "Tire conservation over long stints — more important than peak pace",
        ],
    ),
    "Zandvoort": TrackInfo(
        "Zandvoort", "high", "high",
        notes="Banking in final turns, blind crests. High downforce, compliant suspension.",
        setup_guidance=(
            "Zandvoort's banked Hugenholtz (T3) and the banked final Arie Luyendijk (T14) are "
            "both extremely high-g banked corners that demand rear stability and high downforce — "
            "the banking amplifies loads significantly. The Tarzan hairpin (T1) is a very heavy "
            "braking zone from the front straight. The rising Hugenholtzbocht into the banking "
            "has a blind crest mid-corner — the car must stay planted over the crest without "
            "getting light. Softer suspension allows the car to work with the variable banking "
            "rather than fighting it. Tire wear in both banked turns is severe on the outside edges."
        ),
        key_priorities=[
            "Rear stability through both banked sections T3 and T14",
            "High downforce — banking amplifies loads to very high G",
            "Suspension compliance for banking camber changes",
            "Braking stability into Tarzan T1 hairpin",
            "Outer tire wear management in the banked sections",
        ],
    ),
    "Oschersleben": TrackInfo(
        "Oschersleben", "medium", "medium",
        notes="German club circuit. Medium settings, focus on traction zones.",
        setup_guidance=(
            "Oschersleben is a compact, technical German club circuit. The layout features several "
            "slow to medium-speed hairpins where traction and rotation determine lap time. The "
            "main chicane and hairpin complexes need good rotation on entry and strong drive on "
            "exit. Mechanical grip from ARB and spring settings matters more than aero. Medium "
            "wing balances the short straights adequately."
        ),
        key_priorities=[
            "Traction out of slow hairpins — diff and rear springs",
            "Rotation at hairpin entries",
            "Mechanical grip over aero",
            "Medium wing for mixed-speed layout",
            "Braking stability into hairpin entries",
        ],
    ),
    "Oulton Park": TrackInfo(
        "Oulton Park", "medium", "high",
        notes="Undulating British circuit. Tire stress from constant elevation change.",
        setup_guidance=(
            "Oulton Park is a fast, undulating circuit with severe elevation changes — the Old "
            "Hall corner (T1) at the top of the hill and Druids (T4) downhill are both taken at "
            "significant speed. The car must manage weight transfer through the elevation, "
            "particularly in combined braking and cornering zones. Knickerbrook (T6) is taken "
            "flat through a compression — the car needs sufficient ride height to not bottom there. "
            "Tire stress is high from the elevation and constant medium-speed loading."
        ),
        key_priorities=[
            "Weight transfer management through combined elevation and braking",
            "Ride height clearance at Knickerbrook compression",
            "Rear stability through Old Hall at the top of the hill",
            "Tire management — constant loading from elevation changes",
            "Suspension compliance for elevation changes",
        ],
    ),
    "Ledenon": TrackInfo(
        "Ledenon", "medium", "medium",
        notes="Short French club track. Technical with elevation.",
        setup_guidance=(
            "Ledenon is a short, hilly French club circuit. The significant elevation throughout "
            "means suspension must manage variable weight distribution — softer springs than "
            "normal help with the elevation transitions. The track is tight with limited run-off "
            "so the setup must be forgiving and predictable. Medium wing works for the mixed "
            "speed layout."
        ),
        key_priorities=[
            "Suspension compliance for elevation changes",
            "Forgiving, predictable character for limited run-off",
            "Rotation through the tight hairpin sections",
            "Medium wing for mixed speed layout",
        ],
    ),
    # ── Asia / Oceania ────────────────────────────────────────────────────
    "Suzuka International Racing Course": TrackInfo(
        "Suzuka International Racing Course", "high", "high",
        notes="Fast flowing corners need high downforce. S-curves stress front tires.",
        setup_guidance=(
            "Suzuka demands high downforce — the S-Curves (T3–T9), Dunlop (T10), Degner (T11), "
            "and Spoon (T13–T14) are all medium-to-high speed corners where aero balance is "
            "critical. The S-Curves are taken flat or near-flat and stress the front tires "
            "with continuous rapid direction changes — front tire temperatures build quickly here. "
            "130R (T16) is flat-out and needs absolute rear stability. The Casio Triangle (T17–T18) "
            "is the primary overtaking zone with a tight chicane. Rear downforce must be matched "
            "to front to keep balance through 130R and the S-Curves simultaneously."
        ),
        key_priorities=[
            "Rear stability through 130R flat-out — most critical corner",
            "High downforce matching front and rear for S-Curves balance",
            "Front tire temperature management through S-Curves direction changes",
            "Braking stability into Casio Triangle T17–T18",
            "Consistent aero balance — multiple high-speed corners in both directions",
        ],
    ),
    "Okayama International Circuit": TrackInfo(
        "Okayama International Circuit", "medium", "medium",
        notes="Short technical Japanese circuit. Good for learning car control.",
        setup_guidance=(
            "Okayama is a tight, technical circuit with a mix of medium and slow-speed corners. "
            "The Hairpin and the final chicane are the key slow-speed traction zones. The fast "
            "sweeper section needs balanced aero. A mechanical-grip-focused setup with medium "
            "wing suits the varied layout."
        ),
        key_priorities=[
            "Traction at the hairpin and final chicane",
            "Balanced aero for the fast sweeper section",
            "Mechanical grip focus — technical corners benefit more than aero",
            "Braking stability into the hairpin entry",
        ],
    ),
    "Mount Panorama Circuit": TrackInfo(
        "Mount Panorama Circuit", "medium", "high",
        notes="Elevation changes and concrete walls. Setup must handle bumps and camber.",
        setup_guidance=(
            "Mount Panorama (Bathurst) has the most dramatic elevation change of any circuit — "
            "174m over 6.2km. The mountain section (T2–T10) is taken fast with blind crests and "
            "concrete walls extremely close. The Dipper (T8) is a fast compression under a bridge "
            "taken blind. The Esses (T4–T7) at the top of the mountain are complex "
            "and bumpy — the car must stay planted and composed. Conrod Straight leads to the "
            "Chase (T18–T20) which is the biggest brake zone from the highest speed. "
            "The bottom section (T22–T23) is tight and needs rotation for the long straight."
        ),
        key_priorities=[
            "Rear stability through mountain section blind high-speed corners",
            "Suspension compliance for Esses bumps and Dipper compression",
            "Ride height clearance — generous for mountain compressions",
            "Braking stability into the Chase from top speed on Conrod",
            "Rotation at Griffins Bend for the Conrod Straight drive",
        ],
    ),
    "Winton Motor Raceway": TrackInfo(
        "Winton Motor Raceway", "medium", "medium",
        notes="Australian club circuit. Heavy braking areas, manage rear stability.",
        setup_guidance=(
            "Winton is a flat, compact Australian circuit. The primary lap time corners are the "
            "heavy braking zones at Turn 2 and Turn 6 where braking stability and rotation "
            "determine performance. Traction out of the slow corners feeds the short straights. "
            "Medium setup works well — the track is not technically demanding enough to need "
            "specialised approaches."
        ),
        key_priorities=[
            "Braking stability at T2 and T6",
            "Rotation at slow-speed hairpins",
            "Exit traction for short straights",
            "Balanced medium setup",
        ],
    ),
    "Adelaide Street Circuit": TrackInfo(
        "Adelaide Street Circuit", "high", "medium", "paved", "street",
        notes="Tight street circuit. High downforce, low-speed grip focus.",
        setup_guidance=(
            "Adelaide is a classic street circuit — narrow, bumpy, and unforgiving with walls. "
            "The slow hairpins and 90° corners demand mechanical grip and rotation. High downforce "
            "helps with the multiple slow corners despite the short straights where it costs "
            "little top speed. Bump compliance is critical for the concrete surface and curbs. "
            "Tire wear is aggressive on the abrasive street surface."
        ),
        key_priorities=[
            "Mechanical grip for multiple slow-speed corners",
            "Bump compliance for street surface and curbs",
            "High downforce for slow corners with short straights",
            "Rotation and braking stability at hairpins",
            "Tire wear management on abrasive surface",
        ],
    ),
    "Oran Park Raceway": TrackInfo(
        "Oran Park Raceway", "medium", "medium",
        notes="Short Australian track. Good mechanical grip needed.",
        setup_guidance=(
            "Oran Park is a short, flat Australian club circuit. Mechanical grip and traction "
            "dominate lap time. The tight hairpins need strong rotation and exit drive. "
            "A simple, balanced setup is appropriate — the track does not demand specialised "
            "aero or extreme mechanical settings."
        ),
        key_priorities=[
            "Rotation at hairpins",
            "Exit traction for short straights",
            "Mechanical grip over aero",
            "Balanced, simple setup",
        ],
    ),
    # ── Rally Cross ───────────────────────────────────────────────────────
    "Phoenix Rallycross": TrackInfo(
        "Phoenix Rallycross", "medium", "high", "mixed", "rallycross",
        notes="Mixed surface rallycross. Compliant suspension, lower pressures for dirt sections.",
        setup_guidance=(
            "Mixed-surface rallycross demands a compromise setup. Tire pressures must be lower "
            "than pure tarmac to provide grip on the dirt sections without sacrificing too much "
            "on paved sections. Suspension should be significantly softer than a road-course "
            "setup to allow the tires to follow loose dirt and absorb the transition bumps "
            "between surfaces. Brake bias may need adjusting for the different grip levels "
            "between surfaces — dirt braking requires earlier, lighter application."
        ),
        key_priorities=[
            "Lower tire pressures for dirt section grip",
            "Softer suspension to absorb dirt and transition bumps",
            "Brake application adaptation for surface changes",
            "Balanced setup for both surface types",
            "Traction management on loose dirt exits",
        ],
    ),
    "Winton Rallycross": TrackInfo(
        "Winton Rallycross", "medium", "high", "mixed", "rallycross",
        notes="Australian rallycross with dirt/paved mix.",
        setup_guidance=(
            "Same mixed-surface priorities as Phoenix Rallycross — lower pressures, softer "
            "suspension, and braking adaptation for surface transitions. Australian rallycross "
            "tracks typically have rougher dirt sections than US venues — even more suspension "
            "travel is beneficial."
        ),
        key_priorities=[
            "Lower pressures for dirt grip",
            "Generous suspension travel for rough dirt",
            "Surface transition stability",
            "Traction on dirt exits",
        ],
    ),
    "Daytona Rallycross": TrackInfo(
        "Daytona Rallycross", "medium", "medium", "mixed", "rallycross",
        notes="Rallycross layout inside Daytona. Fast with jumps.",
        setup_guidance=(
            "The Daytona rallycross layout is faster than typical rallycross venues and includes "
            "jump sections. Suspension must handle the landing impact from jumps — bottoming on "
            "landing is dangerous. Mixed surface priorities apply. The faster nature of the "
            "circuit means aerodynamics play more of a role than typical tight rallycross."
        ),
        key_priorities=[
            "Jump landing compliance — generous bump travel",
            "Lower pressures for dirt sections",
            "Faster layout — moderate aero matters more than typical RX",
            "Surface transition stability",
        ],
    ),
    # ── Dirt Ovals ────────────────────────────────────────────────────────
    "Wheatland Raceway": TrackInfo(
        "Wheatland Raceway", "low", "high", "dirt", "oval",
        notes="Dirt oval — tire pressure and stagger dominate setup.",
        setup_guidance=(
            "Dirt ovals are a completely different discipline. Stagger (different circumference "
            "tires left vs right) is the primary setup tool — more stagger makes the car turn "
            "better on the oval. Weight distribution (left-side bias) is essential for mechanical "
            "grip in left-hand turns. Tire pressures are much lower than paved oval equivalents "
            "to maximize contact patch on loose dirt. The car should be set up to be slightly "
            "loose (oversteer) on entry and neutral on exit — drivers actively rotate dirt cars."
        ),
        key_priorities=[
            "Stagger — primary setup tool for dirt oval",
            "Left-side weight bias for mechanical grip",
            "Very low tire pressures for dirt grip",
            "Slightly loose entry balance for driver rotation",
            "Soft suspension for variable dirt surface",
        ],
    ),
    "Wild West Motorsports Park": TrackInfo(
        "Wild West Motorsports Park", "low", "high", "dirt", "oval",
        notes="Dirt oval with variable track conditions.",
        setup_guidance=(
            "All dirt oval priorities apply — stagger, weight bias, low pressures. Wild West "
            "has variable track conditions that change significantly through a race event as "
            "the dirt rubber in or dries out. The setup must be flexible and adjustable — "
            "wedge and stagger are the primary in-race adjustment tools."
        ),
        key_priorities=[
            "Stagger and wedge as primary adjustment tools",
            "Left-side weight bias",
            "Low tire pressures",
            "Setup flexibility for changing track conditions",
            "Soft suspension for variable dirt",
        ],
    ),
    # ── Additional tracks from user telemetry ────────────────────────────
    "Miami International Autodrome": TrackInfo(
        "Miami International Autodrome", "high", "high",
        notes="Street circuit around Hard Rock Stadium. High downforce, bumpy surface.",
        setup_guidance=(
            "Miami is a challenging street circuit that combines very slow hairpins with "
            "high-speed sweepers around the stadium. Turn 1 is a very heavy braking zone "
            "from the front straight. The T11–T16 stadium complex has multiple tight hairpins "
            "where rotation and traction dominate — mechanical grip is more important than "
            "aerodynamics here. The track surface is bumpy and abrasive, demanding softer "
            "bump damping to prevent the car from being knocked off line over surface "
            "imperfections. High downforce throughout to manage the slow-speed sections."
        ),
        key_priorities=[
            "Braking stability into T1 from long front straight",
            "Rotation through the slow stadium hairpins T11–T16",
            "Bump compliance for abrasive surface imperfections",
            "High downforce — many slow-speed sections require mechanical grip",
            "Tire wear on abrasive street surface",
        ],
    ),
    "Motorsport Arena Oschersleben": TrackInfo(
        "Motorsport Arena Oschersleben", "medium", "medium",
        notes="German technical circuit. Medium speed, mechanical grip focus.",
        setup_guidance=(
            "Oschersleben is a compact, technical German circuit where mechanical grip and "
            "car balance matter more than peak aerodynamics. The long front straight into the "
            "Motodrom hairpin (T1) is the primary braking and overtaking zone — braking "
            "stability is essential. The infield section has a mix of medium-speed corners "
            "where the car must be neutral and easy to rotate. The circuit is relatively "
            "smooth, allowing slightly stiffer setups. Medium wing gives enough downforce "
            "for the infield corners without costing excessive straight-line speed."
        ),
        key_priorities=[
            "Braking stability into Motodrom hairpin T1",
            "Neutral balance through technical infield section",
            "Medium downforce — balance infield grip vs. straight-line speed",
            "Rotation and traction at hairpin exits",
            "Consistent tire temperatures — relatively even loading",
        ],
    ),
    "Summit Point Raceway": TrackInfo(
        "Summit Point Raceway", "medium", "medium",
        notes="West Virginia road course. Technical layout with fast sweepers.",
        setup_guidance=(
            "Summit Point's main circuit is a traditional road course with a good mix of "
            "corner types. The fast sweeper in the back section demands rear stability and "
            "aerodynamic confidence. The tight hairpin sections require good rotation and "
            "traction on exit. The track surface is smooth enough to run slightly stiffer "
            "setups, but tire degradation is moderate. The Jefferson Circuit variant adds "
            "more infield technical sections that reward mechanical grip. Medium downforce "
            "is appropriate for both layouts."
        ),
        key_priorities=[
            "Rear stability through fast back-section sweeper",
            "Rotation at hairpin sections — key lap time areas",
            "Medium downforce — balanced layout",
            "Traction on exit of slow corners",
            "Consistent balance — track rewards predictable handling",
        ],
    ),
}


# ── Known iRacing name → DB key aliases ───────────────────────────────────
# Maps iRacing's full official track name patterns to our DB keys.
# Used when the iRacing name shares no common words with our simpler key.
_TRACK_ALIASES: Dict[str, str] = {
    # iRacing name fragment (lowercase)  →  our _TRACKS key
    "autodromo hermanos rodriguez": "Mexico City",
    "hermanos rodriguez":           "Mexico City",
    "circuit zandvoort":            "Zandvoort",
    "zandvoort":                    "Zandvoort",
    "gesamtstrecke":                "Nürburgring Combined",
    "nurburgring combined":         "Nürburgring Combined",
    "nürburgring combined":         "Nürburgring Combined",
    "jefferson circuit":            "Summit Point Raceway",
    "summit point":                 "Summit Point Raceway",
    "weathertech raceway laguna":   "Laguna Seca",
    "laguna seca":                  "Laguna Seca",
    "watkins glen":                 "Watkins Glen International",
    "silverstone circuit":          "Silverstone Circuit",
    "circuit de spa":               "Spa-Francorchamps",
    "spa-francorchamps":            "Spa-Francorchamps",
    "circuit of the americas":      "Circuit of the Americas",
    "autodromo nazionale monza":    "Monza",
    "circuit de barcelona":         "Circuit de Barcelona-Catalunya",
    "autodromo enzo e dino ferrari":"Imola",
    "circuit gilles villeneuve":    "Montreal",
    "red bull ring":                "Red Bull Ring",
}


def _find_track(track_name: str) -> Optional[TrackInfo]:
    """Fuzzy-match a track name against the database.

    Tries exact match, then alias lookup, then keyword overlap so that
    iRacing names like 'Circuit de Spa-Francorchamps - Grand Prix'
    match 'Spa-Francorchamps'.
    """
    if not track_name:
        return None

    # 1. Exact match
    if track_name in _TRACKS:
        return _TRACKS[track_name]

    # 2. Case-insensitive exact
    lower = track_name.lower()
    for key, info in _TRACKS.items():
        if key.lower() == lower:
            return info

    # 3. Alias lookup — check if any alias fragment is in the query string
    for fragment, db_key in _TRACK_ALIASES.items():
        if fragment in lower and db_key in _TRACKS:
            return _TRACKS[db_key]

    # 4. Keyword overlap — normalise to comparable tokens
    def _tokens(s: str):
        # Strip common suffix words that add noise
        noise = {'circuit', 'raceway', 'international', 'grand', 'prix',
                 'full', 'course', 'oval', 'track', 'park', 'speedway',
                 'national', 'gp', 'de', 'le', 'la', 'du'}
        tokens = set(s.lower().replace('-', ' ').replace('_', ' ').split())
        return tokens - noise if len(tokens - noise) >= 1 else tokens

    query_tokens = _tokens(track_name)
    best_match = None
    best_score = 0
    for key, info in _TRACKS.items():
        key_tokens = _tokens(key)
        overlap = len(query_tokens & key_tokens)
        if overlap > best_score:
            best_score = overlap
            best_match = info

    return best_match if best_score >= 1 else None


# ── Template Database ─────────────────────────────────────────────────────────
# Templates for every car class × downforce level.

_TEMPLATES: Dict[str, Dict[str, SetupTemplate]] = {
    # ══════════════════════════════════════════════════════════════════════════
    # GT3  —  Full numeric baselines (40+ parameters)
    # ══════════════════════════════════════════════════════════════════════════
    "gt3": {
        # Low downforce: Monza, Daytona Road, Le Mans, Spa long-run
        "low": SetupTemplate(
            front_wing="3 / 10", rear_wing="3 / 10",
            tire_pressures_psi={'LF': 27.0, 'RF': 27.0, 'LR': 26.0, 'RR': 26.0},
            camber_deg={'LF': -3.2, 'RF': -3.2, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=56.0,
            key_adjustments=["Minimize wing for top speed", "Stiffer springs for platform stability"],
            priority_notes="Top speed is king — accept some corner compromise for straight-line pace.",
            # ── Numeric ──
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=95.0, spring_rf=95.0, spring_lr=85.0, spring_rr=85.0,
            arb_front=3, arb_rear=3,
            rh_lf=58.0, rh_rf=58.0, rh_lr=74.0, rh_rr=74.0,
            bump_slow_lf=8, bump_slow_rf=8, bump_slow_lr=7, bump_slow_rr=7,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=10, rebound_slow_rf=10, rebound_slow_lr=9, rebound_slow_rr=9,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=50.0, diff_power_deg=45.0, diff_coast_deg=0.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=96.0,
        ),
        # Medium downforce: Spa, Silverstone, Road America, COTA, Sebring
        "medium": SetupTemplate(
            front_wing="5 / 10", rear_wing="5 / 10",
            tire_pressures_psi={'LF': 27.5, 'RF': 27.5, 'LR': 26.5, 'RR': 26.5},
            camber_deg={'LF': -3.0, 'RF': -3.0, 'LR': -1.8, 'RR': -1.8},
            brake_bias_pct=55.0,
            key_adjustments=["Balance front/rear downforce", "Tune ARBs for balance"],
            priority_notes="Balanced approach — equal weight on mechanical and aero grip.",
            # ── Numeric ──
            wing_front_step=5, wing_rear_step=5,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=80.0, spring_rf=80.0, spring_lr=70.0, spring_rr=70.0,
            arb_front=4, arb_rear=4,
            rh_lf=62.0, rh_rf=62.0, rh_lr=78.0, rh_rr=78.0,
            bump_slow_lf=7, bump_slow_rf=7, bump_slow_lr=6, bump_slow_rr=6,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=9, rebound_slow_rf=9, rebound_slow_lr=8, rebound_slow_rr=8,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=50.0, diff_power_deg=45.0, diff_coast_deg=0.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=95.0,
        ),
        # High downforce: Monaco, Singapore, Hungaroring, Zandvoort
        "high": SetupTemplate(
            front_wing="7 / 10", rear_wing="7 / 10",
            tire_pressures_psi={'LF': 28.0, 'RF': 28.0, 'LR': 27.0, 'RR': 27.0},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.2, 'RR': -2.2},
            brake_bias_pct=54.5,
            key_adjustments=["Maximize wing for corner speed", "Soften springs for curb compliance"],
            priority_notes="Corner speed is everything — accept straight-line deficit.",
            # ── Numeric ──
            wing_front_step=7, wing_rear_step=7,
            toe_front_mm=-0.5, toe_rear_mm=2.0,
            spring_lf=65.0, spring_rf=65.0, spring_lr=60.0, spring_rr=60.0,
            arb_front=5, arb_rear=5,
            rh_lf=65.0, rh_rf=65.0, rh_lr=82.0, rh_rr=82.0,
            bump_slow_lf=6, bump_slow_rf=6, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=8, rebound_slow_rf=8, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=50.0, diff_power_deg=45.0, diff_coast_deg=0.0,
            tc_1=3, abs_setting=3, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # GT4  —  Mechanical grip dominant; limited aero
    # ══════════════════════════════════════════════════════════════════════════
    "gt4": {
        "low": SetupTemplate(
            front_wing="1 / 5", rear_wing="1 / 5",
            tire_pressures_psi={'LF': 27.5, 'RF': 27.5, 'LR': 26.5, 'RR': 26.5},
            camber_deg={'LF': -2.8, 'RF': -2.8, 'LR': -1.5, 'RR': -1.5},
            brake_bias_pct=56.0,
            key_adjustments=["Limited aero — mechanical grip is everything", "Focus on exit traction"],
            priority_notes="GT4 has minimal aero — springs and ARBs are the primary balance tools.",
            wing_front_step=1, wing_rear_step=1,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=60.0, spring_rf=60.0, spring_lr=55.0, spring_rr=55.0,
            arb_front=3, arb_rear=3,
            rh_lf=65.0, rh_rf=65.0, rh_lr=82.0, rh_rr=82.0,
            bump_slow_lf=7, bump_slow_rf=7, bump_slow_lr=6, bump_slow_rr=6,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=9, rebound_slow_rf=9, rebound_slow_lr=8, rebound_slow_rr=8,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=50.0, diff_power_deg=45.0, diff_coast_deg=5.0,
            tc_1=5, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 28.0, 'RF': 28.0, 'LR': 27.0, 'RR': 27.0},
            camber_deg={'LF': -2.5, 'RF': -2.5, 'LR': -1.3, 'RR': -1.3},
            brake_bias_pct=55.5,
            key_adjustments=["Balance mechanical grip", "Smooth driving inputs critical"],
            priority_notes="Balanced GT4 — let the car flow, smooth inputs reward more than setup.",
            wing_front_step=2, wing_rear_step=2,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=55.0, spring_rf=55.0, spring_lr=50.0, spring_rr=50.0,
            arb_front=4, arb_rear=4,
            rh_lf=67.0, rh_rf=67.0, rh_lr=84.0, rh_rr=84.0,
            bump_slow_lf=6, bump_slow_rf=6, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=8, rebound_slow_rf=8, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=50.0, diff_power_deg=45.0, diff_coast_deg=5.0,
            tc_1=5, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 28.5, 'RF': 28.5, 'LR': 27.5, 'RR': 27.5},
            camber_deg={'LF': -3.0, 'RF': -3.0, 'LR': -1.8, 'RR': -1.8},
            brake_bias_pct=55.0,
            key_adjustments=["Soften springs for compliance at technical tracks", "Stiffen ARBs for roll control"],
            priority_notes="Technical track GT4 — softer springs help at slow corners where aero can't.",
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=-0.5, toe_rear_mm=2.0,
            spring_lf=50.0, spring_rf=50.0, spring_lr=45.0, spring_rr=45.0,
            arb_front=5, arb_rear=5,
            rh_lf=70.0, rh_rf=70.0, rh_lr=87.0, rh_rr=87.0,
            bump_slow_lf=5, bump_slow_rf=5, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=7, rebound_slow_rf=7, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=4, rebound_fast_rf=4, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=50.0, diff_power_deg=45.0, diff_coast_deg=5.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # GTP / Hypercar / LMDh  —  Very stiff; ride height critical
    # ══════════════════════════════════════════════════════════════════════════
    "gtp": {
        "low": SetupTemplate(
            front_wing="3 / 12", rear_wing="3 / 12",
            tire_pressures_psi={'LF': 22.0, 'RF': 22.0, 'LR': 21.0, 'RR': 21.0},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=58.0,
            key_adjustments=["Minimize drag for top speed", "Very low ride height for aero platform"],
            priority_notes="LMDh/Hypercar — aero platform stability is everything at Le Mans speeds.",
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=0.0, toe_rear_mm=1.0,
            spring_lf=180.0, spring_rf=180.0, spring_lr=190.0, spring_rr=190.0,
            arb_front=4, arb_rear=5,
            rh_lf=35.0, rh_rf=35.0, rh_lr=55.0, rh_rr=55.0,
            bump_slow_lf=10, bump_slow_rf=10, bump_slow_lr=10, bump_slow_rr=10,
            bump_fast_lf=6, bump_fast_rf=6, bump_fast_lr=6, bump_fast_rr=6,
            rebound_slow_lf=12, rebound_slow_rf=12, rebound_slow_lr=12, rebound_slow_rr=12,
            rebound_fast_lf=7, rebound_fast_rf=7, rebound_fast_lr=7, rebound_fast_rr=7,
            diff_preload_nm=100.0, diff_power_deg=60.0, diff_coast_deg=10.0,
            tc_1=6, abs_setting=5, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            front_wing="6 / 12", rear_wing="6 / 12",
            tire_pressures_psi={'LF': 22.5, 'RF': 22.5, 'LR': 21.5, 'RR': 21.5},
            camber_deg={'LF': -3.2, 'RF': -3.2, 'LR': -1.8, 'RR': -1.8},
            brake_bias_pct=57.0,
            key_adjustments=["Balance aero platform with ride", "Tune hybrid deployment zones"],
            priority_notes="Balanced GTP for mixed-speed circuits.",
            wing_front_step=6, wing_rear_step=6,
            toe_front_mm=0.0, toe_rear_mm=1.0,
            spring_lf=160.0, spring_rf=160.0, spring_lr=170.0, spring_rr=170.0,
            arb_front=5, arb_rear=5,
            rh_lf=38.0, rh_rf=38.0, rh_lr=58.0, rh_rr=58.0,
            bump_slow_lf=9, bump_slow_rf=9, bump_slow_lr=9, bump_slow_rr=9,
            bump_fast_lf=6, bump_fast_rf=6, bump_fast_lr=6, bump_fast_rr=6,
            rebound_slow_lf=11, rebound_slow_rf=11, rebound_slow_lr=11, rebound_slow_rr=11,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=6, rebound_fast_rr=6,
            diff_preload_nm=100.0, diff_power_deg=55.0, diff_coast_deg=10.0,
            tc_1=6, abs_setting=5, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            front_wing="9 / 12", rear_wing="9 / 12",
            tire_pressures_psi={'LF': 23.0, 'RF': 23.0, 'LR': 22.0, 'RR': 22.0},
            camber_deg={'LF': -3.8, 'RF': -3.8, 'LR': -2.3, 'RR': -2.3},
            brake_bias_pct=56.5,
            key_adjustments=["Maximum downforce", "Soften springs slightly for curb compliance"],
            priority_notes="Technical circuit GTP — maximize corner speed, manage floor scraping.",
            wing_front_step=9, wing_rear_step=9,
            toe_front_mm=-0.5, toe_rear_mm=1.5,
            spring_lf=140.0, spring_rf=140.0, spring_lr=155.0, spring_rr=155.0,
            arb_front=5, arb_rear=6,
            rh_lf=42.0, rh_rf=42.0, rh_lr=62.0, rh_rr=62.0,
            bump_slow_lf=8, bump_slow_rf=8, bump_slow_lr=8, bump_slow_rr=8,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=5, bump_fast_rr=5,
            rebound_slow_lf=10, rebound_slow_rf=10, rebound_slow_lr=10, rebound_slow_rr=10,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=6, rebound_fast_rr=6,
            diff_preload_nm=100.0, diff_power_deg=50.0, diff_coast_deg=10.0,
            tc_1=5, abs_setting=4, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # GTE  —  Similar to GTP but lower downforce class
    # ══════════════════════════════════════════════════════════════════════════
    "gte": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 22.5, 'RF': 22.5, 'LR': 21.5, 'RR': 21.5},
            camber_deg={'LF': -3.3, 'RF': -3.3, 'LR': -1.8, 'RR': -1.8},
            brake_bias_pct=57.5,
            key_adjustments=["Reduce drag", "Stiffen springs for top-speed platform"],
            priority_notes="GTE low-drag setup for long straights.",
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=0.0, toe_rear_mm=1.0,
            spring_lf=150.0, spring_rf=150.0, spring_lr=160.0, spring_rr=160.0,
            arb_front=4, arb_rear=4,
            rh_lf=40.0, rh_rf=40.0, rh_lr=60.0, rh_rr=60.0,
            bump_slow_lf=9, bump_slow_rf=9, bump_slow_lr=8, bump_slow_rr=8,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=5, bump_fast_rr=5,
            rebound_slow_lf=11, rebound_slow_rf=11, rebound_slow_lr=10, rebound_slow_rr=10,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=6, rebound_fast_rr=6,
            diff_preload_nm=80.0, diff_power_deg=50.0, diff_coast_deg=5.0,
            tc_1=5, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 23.0, 'RF': 23.0, 'LR': 22.0, 'RR': 22.0},
            camber_deg={'LF': -3.0, 'RF': -3.0, 'LR': -1.6, 'RR': -1.6},
            brake_bias_pct=57.0,
            key_adjustments=["Balance aero and mechanical grip"],
            priority_notes="Balanced GTE setup.",
            wing_front_step=5, wing_rear_step=5,
            toe_front_mm=0.0, toe_rear_mm=1.0,
            spring_lf=135.0, spring_rf=135.0, spring_lr=145.0, spring_rr=145.0,
            arb_front=4, arb_rear=5,
            rh_lf=43.0, rh_rf=43.0, rh_lr=63.0, rh_rr=63.0,
            bump_slow_lf=8, bump_slow_rf=8, bump_slow_lr=8, bump_slow_rr=8,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=5, bump_fast_rr=5,
            rebound_slow_lf=10, rebound_slow_rf=10, rebound_slow_lr=10, rebound_slow_rr=10,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=6, rebound_fast_rr=6,
            diff_preload_nm=80.0, diff_power_deg=50.0, diff_coast_deg=5.0,
            tc_1=5, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 23.5, 'RF': 23.5, 'LR': 22.5, 'RR': 22.5},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=56.5,
            key_adjustments=["Maximize downforce", "Manage temps"],
            priority_notes="GTE high-downforce for technical layouts.",
            wing_front_step=8, wing_rear_step=8,
            toe_front_mm=-0.5, toe_rear_mm=1.5,
            spring_lf=120.0, spring_rf=120.0, spring_lr=130.0, spring_rr=130.0,
            arb_front=5, arb_rear=5,
            rh_lf=47.0, rh_rf=47.0, rh_lr=67.0, rh_rr=67.0,
            bump_slow_lf=7, bump_slow_rf=7, bump_slow_lr=7, bump_slow_rr=7,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=9, rebound_slow_rf=9, rebound_slow_lr=9, rebound_slow_rr=9,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=80.0, diff_power_deg=50.0, diff_coast_deg=5.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # LMP2  —  Ground effect prototype; stiff springs, low ride height
    # ══════════════════════════════════════════════════════════════════════════
    "lmp2": {
        "low": SetupTemplate(
            front_wing="3 / 10", rear_wing="3 / 10",
            tire_pressures_psi={'LF': 22.0, 'RF': 22.0, 'LR': 21.0, 'RR': 21.0},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=57.5,
            key_adjustments=["Minimize drag", "Maintain low ride height for ground effect"],
            priority_notes="LMP2 low-drag — top speed and aero platform for endurance.",
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=0.0, toe_rear_mm=1.0,
            spring_lf=160.0, spring_rf=160.0, spring_lr=170.0, spring_rr=170.0,
            arb_front=4, arb_rear=4,
            rh_lf=33.0, rh_rf=33.0, rh_lr=50.0, rh_rr=50.0,
            bump_slow_lf=10, bump_slow_rf=10, bump_slow_lr=9, bump_slow_rr=9,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=5, bump_fast_rr=5,
            rebound_slow_lf=12, rebound_slow_rf=12, rebound_slow_lr=11, rebound_slow_rr=11,
            rebound_fast_lf=7, rebound_fast_rf=7, rebound_fast_lr=6, rebound_fast_rr=6,
            diff_preload_nm=80.0, diff_power_deg=50.0, diff_coast_deg=5.0,
            tc_1=5, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 22.5, 'RF': 22.5, 'LR': 21.5, 'RR': 21.5},
            camber_deg={'LF': -3.2, 'RF': -3.2, 'LR': -1.8, 'RR': -1.8},
            brake_bias_pct=57.0,
            key_adjustments=["Balance aero platform and ride height"],
            priority_notes="Balanced LMP2 setup for mixed-speed circuits.",
            wing_front_step=5, wing_rear_step=5,
            toe_front_mm=0.0, toe_rear_mm=1.0,
            spring_lf=145.0, spring_rf=145.0, spring_lr=155.0, spring_rr=155.0,
            arb_front=4, arb_rear=5,
            rh_lf=36.0, rh_rf=36.0, rh_lr=53.0, rh_rr=53.0,
            bump_slow_lf=9, bump_slow_rf=9, bump_slow_lr=9, bump_slow_rr=9,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=5, bump_fast_rr=5,
            rebound_slow_lf=11, rebound_slow_rf=11, rebound_slow_lr=11, rebound_slow_rr=11,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=6, rebound_fast_rr=6,
            diff_preload_nm=80.0, diff_power_deg=50.0, diff_coast_deg=5.0,
            tc_1=5, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 23.0, 'RF': 23.0, 'LR': 22.0, 'RR': 22.0},
            camber_deg={'LF': -3.8, 'RF': -3.8, 'LR': -2.3, 'RR': -2.3},
            brake_bias_pct=56.0,
            key_adjustments=["Maximize wing", "Soften springs for curb compliance"],
            priority_notes="Maximum cornering speed LMP2 for technical tracks.",
            wing_front_step=8, wing_rear_step=8,
            toe_front_mm=-0.5, toe_rear_mm=1.5,
            spring_lf=130.0, spring_rf=130.0, spring_lr=140.0, spring_rr=140.0,
            arb_front=5, arb_rear=5,
            rh_lf=40.0, rh_rf=40.0, rh_lr=57.0, rh_rr=57.0,
            bump_slow_lf=8, bump_slow_rf=8, bump_slow_lr=8, bump_slow_rr=8,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=10, rebound_slow_rf=10, rebound_slow_lr=10, rebound_slow_rr=10,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=80.0, diff_power_deg=50.0, diff_coast_deg=5.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # PROTOTYPE  —  Older DP / sport-protos (HPD ARX-01, Riley DP, etc.)
    # ══════════════════════════════════════════════════════════════════════════
    "prototype": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 23.0, 'RF': 23.0, 'LR': 22.0, 'RR': 22.0},
            camber_deg={'LF': -3.0, 'RF': -3.0, 'LR': -1.5, 'RR': -1.5},
            brake_bias_pct=57.0,
            key_adjustments=["Reduce drag", "Stable aero platform"],
            priority_notes="Older prototype low-drag setup.",
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=0.0, toe_rear_mm=1.0,
            spring_lf=140.0, spring_rf=140.0, spring_lr=150.0, spring_rr=150.0,
            arb_front=3, arb_rear=4,
            rh_lf=40.0, rh_rf=40.0, rh_lr=58.0, rh_rr=58.0,
            bump_slow_lf=9, bump_slow_rf=9, bump_slow_lr=8, bump_slow_rr=8,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=5, bump_fast_rr=5,
            rebound_slow_lf=11, rebound_slow_rf=11, rebound_slow_lr=10, rebound_slow_rr=10,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=70.0, diff_power_deg=45.0, diff_coast_deg=5.0,
            tc_1=5, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 23.5, 'RF': 23.5, 'LR': 22.5, 'RR': 22.5},
            brake_bias_pct=56.5,
            key_adjustments=["Balance grip and stability"],
            priority_notes="Balanced prototype setup.",
            wing_front_step=5, wing_rear_step=5,
            toe_front_mm=0.0, toe_rear_mm=1.0,
            spring_lf=125.0, spring_rf=125.0, spring_lr=135.0, spring_rr=135.0,
            arb_front=4, arb_rear=4,
            rh_lf=43.0, rh_rf=43.0, rh_lr=61.0, rh_rr=61.0,
            bump_slow_lf=8, bump_slow_rf=8, bump_slow_lr=8, bump_slow_rr=8,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=10, rebound_slow_rf=10, rebound_slow_lr=10, rebound_slow_rr=10,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=70.0, diff_power_deg=45.0, diff_coast_deg=5.0,
            tc_1=5, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 24.0, 'RF': 24.0, 'LR': 23.0, 'RR': 23.0},
            brake_bias_pct=56.0,
            key_adjustments=["Max wing angles", "Soften springs slightly"],
            priority_notes="Max downforce for technical tracks.",
            wing_front_step=8, wing_rear_step=8,
            toe_front_mm=-0.5, toe_rear_mm=1.5,
            spring_lf=110.0, spring_rf=110.0, spring_lr=120.0, spring_rr=120.0,
            arb_front=5, arb_rear=5,
            rh_lf=47.0, rh_rf=47.0, rh_lr=65.0, rh_rr=65.0,
            bump_slow_lf=7, bump_slow_rf=7, bump_slow_lr=7, bump_slow_rr=7,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=9, rebound_slow_rf=9, rebound_slow_lr=9, rebound_slow_rr=9,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=70.0, diff_power_deg=45.0, diff_coast_deg=5.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # FORMULA  —  Single-seater; very stiff springs, very low ride height
    # ══════════════════════════════════════════════════════════════════════════
    "formula": {
        "low": SetupTemplate(
            front_wing="4 / 20", rear_wing="4 / 20",
            tire_pressures_psi={'LF': 21.0, 'RF': 21.0, 'LR': 20.0, 'RR': 20.0},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=57.0,
            key_adjustments=["Minimize drag for top-speed circuits", "Stiff springs for aero platform"],
            priority_notes="Minimize drag — peaky engine loses power quickly off peak RPM, so top speed matters.",
            wing_front_step=4, wing_rear_step=4,
            toe_front_mm=0.0, toe_rear_mm=0.5,
            spring_lf=250.0, spring_rf=250.0, spring_lr=280.0, spring_rr=280.0,
            arb_front=3, arb_rear=3,
            rh_lf=30.0, rh_rf=30.0, rh_lr=45.0, rh_rr=45.0,
            bump_slow_lf=9, bump_slow_rf=9, bump_slow_lr=9, bump_slow_rr=9,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=5, bump_fast_rr=5,
            rebound_slow_lf=11, rebound_slow_rf=11, rebound_slow_lr=11, rebound_slow_rr=11,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=6, rebound_fast_rr=6,
            diff_preload_nm=50.0, diff_power_deg=40.0, diff_coast_deg=0.0,
            tc_1=3, abs_setting=3, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            front_wing="10 / 20", rear_wing="10 / 20",
            tire_pressures_psi={'LF': 21.5, 'RF': 21.5, 'LR': 20.5, 'RR': 20.5},
            camber_deg={'LF': -3.2, 'RF': -3.2, 'LR': -1.8, 'RR': -1.8},
            brake_bias_pct=56.0,
            key_adjustments=["Balance aero and mechanical grip", "Wing angle is primary balance tool"],
            priority_notes="General-purpose formula setup — 1 wing step = measurable balance shift.",
            wing_front_step=10, wing_rear_step=10,
            toe_front_mm=0.0, toe_rear_mm=0.5,
            spring_lf=220.0, spring_rf=220.0, spring_lr=240.0, spring_rr=240.0,
            arb_front=4, arb_rear=4,
            rh_lf=33.0, rh_rf=33.0, rh_lr=48.0, rh_rr=48.0,
            bump_slow_lf=8, bump_slow_rf=8, bump_slow_lr=8, bump_slow_rr=8,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=5, bump_fast_rr=5,
            rebound_slow_lf=10, rebound_slow_rf=10, rebound_slow_lr=10, rebound_slow_rr=10,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=6, rebound_fast_rr=6,
            diff_preload_nm=50.0, diff_power_deg=40.0, diff_coast_deg=0.0,
            tc_1=3, abs_setting=3, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            front_wing="16 / 20", rear_wing="16 / 20",
            tire_pressures_psi={'LF': 22.0, 'RF': 22.0, 'LR': 21.0, 'RR': 21.0},
            camber_deg={'LF': -3.8, 'RF': -3.8, 'LR': -2.3, 'RR': -2.3},
            brake_bias_pct=55.0,
            key_adjustments=["Maximize wing for slow technical track", "Softer springs for kerb compliance"],
            priority_notes="Maximum downforce for tight technical layouts — trail braking is key.",
            wing_front_step=16, wing_rear_step=16,
            toe_front_mm=-0.5, toe_rear_mm=1.0,
            spring_lf=190.0, spring_rf=190.0, spring_lr=210.0, spring_rr=210.0,
            arb_front=5, arb_rear=5,
            rh_lf=37.0, rh_rf=37.0, rh_lr=52.0, rh_rr=52.0,
            bump_slow_lf=7, bump_slow_rf=7, bump_slow_lr=7, bump_slow_rr=7,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=9, rebound_slow_rf=9, rebound_slow_lr=9, rebound_slow_rr=9,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=50.0, diff_power_deg=35.0, diff_coast_deg=0.0,
            tc_1=2, abs_setting=2, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # SUPER FORMULA
    # ══════════════════════════════════════════════════════════════════════════
    "super_formula": {
        "low": SetupTemplate(
            front_wing="Low setting", rear_wing="Low setting",
            tire_pressures_psi={'LF': 21.0, 'RF': 21.0, 'LR': 20.0, 'RR': 20.0},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=58.0,
            key_adjustments=["Minimize drag", "Stiff springs"],
            priority_notes="Super Formula low-drag setup.",
            wing_front_step=5, wing_rear_step=5,
            toe_front_mm=0.0, toe_rear_mm=0.5,
            spring_lf=280.0, spring_rf=280.0, spring_lr=300.0, spring_rr=300.0,
            arb_front=3, arb_rear=4,
            rh_lf=28.0, rh_rf=28.0, rh_lr=43.0, rh_rr=43.0,
            bump_slow_lf=9, bump_slow_rf=9, bump_slow_lr=9, bump_slow_rr=9,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=5, bump_fast_rr=5,
            rebound_slow_lf=11, rebound_slow_rf=11, rebound_slow_lr=11, rebound_slow_rr=11,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=6, rebound_fast_rr=6,
            diff_preload_nm=40.0, diff_power_deg=35.0, diff_coast_deg=0.0,
            tc_1=3, abs_setting=3, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 21.5, 'RF': 21.5, 'LR': 20.5, 'RR': 20.5},
            brake_bias_pct=57.0,
            key_adjustments=["Balance downforce and drag"],
            priority_notes="Balanced Super Formula setup.",
            wing_front_step=10, wing_rear_step=10,
            toe_front_mm=0.0, toe_rear_mm=0.5,
            spring_lf=250.0, spring_rf=250.0, spring_lr=270.0, spring_rr=270.0,
            arb_front=4, arb_rear=4,
            rh_lf=31.0, rh_rf=31.0, rh_lr=46.0, rh_rr=46.0,
            bump_slow_lf=8, bump_slow_rf=8, bump_slow_lr=8, bump_slow_rr=8,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=5, bump_fast_rr=5,
            rebound_slow_lf=10, rebound_slow_rf=10, rebound_slow_lr=10, rebound_slow_rr=10,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=6, rebound_fast_rr=6,
            diff_preload_nm=40.0, diff_power_deg=35.0, diff_coast_deg=0.0,
            tc_1=3, abs_setting=3, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 22.0, 'RF': 22.0, 'LR': 21.0, 'RR': 21.0},
            brake_bias_pct=56.0,
            key_adjustments=["Max wing", "Soften springs for compliance"],
            priority_notes="Max downforce Super Formula for street/technical tracks.",
            wing_front_step=16, wing_rear_step=16,
            toe_front_mm=-0.5, toe_rear_mm=1.0,
            spring_lf=220.0, spring_rf=220.0, spring_lr=240.0, spring_rr=240.0,
            arb_front=5, arb_rear=5,
            rh_lf=35.0, rh_rf=35.0, rh_lr=50.0, rh_rr=50.0,
            bump_slow_lf=7, bump_slow_rf=7, bump_slow_lr=7, bump_slow_rr=7,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=9, rebound_slow_rf=9, rebound_slow_lr=9, rebound_slow_rr=9,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=40.0, diff_power_deg=30.0, diff_coast_deg=0.0,
            tc_1=2, abs_setting=2, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # PORSCHE CUP  —  Rear-engine; lower brake bias; softer front springs
    # ══════════════════════════════════════════════════════════════════════════
    "porsche_cup": {
        "low": SetupTemplate(
            front_wing="1 / 3", rear_wing="1 / 3",
            tire_pressures_psi={'LF': 27.0, 'RF': 27.0, 'LR': 26.0, 'RR': 26.0},
            camber_deg={'LF': -3.0, 'RF': -3.0, 'LR': -2.2, 'RR': -2.2},
            brake_bias_pct=52.0,
            key_adjustments=["Rear-engine: lower brake bias", "Stiffer rear springs for rear-weight stability"],
            priority_notes="Rear-engine — rear brakes carry more load. Minimize drag on fast circuits.",
            wing_front_step=1, wing_rear_step=1,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=55.0, spring_rf=55.0, spring_lr=75.0, spring_rr=75.0,
            arb_front=3, arb_rear=4,
            rh_lf=65.0, rh_rf=65.0, rh_lr=75.0, rh_rr=75.0,
            bump_slow_lf=6, bump_slow_rf=6, bump_slow_lr=7, bump_slow_rr=7,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=8, rebound_slow_rf=8, rebound_slow_lr=9, rebound_slow_rr=9,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=75.0, diff_power_deg=40.0, diff_coast_deg=5.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 27.5, 'RF': 27.5, 'LR': 26.5, 'RR': 26.5},
            camber_deg={'LF': -2.8, 'RF': -2.8, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=51.5,
            key_adjustments=["Balance understeer/oversteer — rear engine sensitive to throttle"],
            priority_notes="Balanced Porsche Cup. Respect the rear-engine snap oversteer risk on power.",
            wing_front_step=2, wing_rear_step=2,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=50.0, spring_rf=50.0, spring_lr=70.0, spring_rr=70.0,
            arb_front=3, arb_rear=4,
            rh_lf=67.0, rh_rf=67.0, rh_lr=77.0, rh_rr=77.0,
            bump_slow_lf=6, bump_slow_rf=6, bump_slow_lr=7, bump_slow_rr=7,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=8, rebound_slow_rf=8, rebound_slow_lr=9, rebound_slow_rr=9,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=75.0, diff_power_deg=40.0, diff_coast_deg=5.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 28.0, 'RF': 28.0, 'LR': 27.0, 'RR': 27.0},
            camber_deg={'LF': -3.2, 'RF': -3.2, 'LR': -2.5, 'RR': -2.5},
            brake_bias_pct=51.0,
            key_adjustments=["Softer rear springs for compliance at technical tracks", "More rear camber for grip"],
            priority_notes="Technical track Cup — watch rear tire temps from high camber.",
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=-0.5, toe_rear_mm=2.0,
            spring_lf=45.0, spring_rf=45.0, spring_lr=65.0, spring_rr=65.0,
            arb_front=4, arb_rear=5,
            rh_lf=70.0, rh_rf=70.0, rh_lr=80.0, rh_rr=80.0,
            bump_slow_lf=5, bump_slow_rf=5, bump_slow_lr=6, bump_slow_rr=6,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=7, rebound_slow_rf=7, rebound_slow_lr=8, rebound_slow_rr=8,
            rebound_fast_lf=4, rebound_fast_rf=4, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=75.0, diff_power_deg=40.0, diff_coast_deg=5.0,
            tc_1=3, abs_setting=3, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # TCR  —  FWD; high brake bias; front tires handle braking + steering + traction
    # ══════════════════════════════════════════════════════════════════════════
    "tcr": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 28.0, 'RF': 28.0, 'LR': 27.0, 'RR': 27.0},
            camber_deg={'LF': -2.5, 'RF': -2.5, 'LR': -1.2, 'RR': -1.2},
            brake_bias_pct=58.0,
            key_adjustments=["FWD: manage front tire temps", "Soft rear ARB for rotation"],
            priority_notes="FWD — front tires do everything. High TC prevents exit wheelspin.",
            wing_front_step=1, wing_rear_step=1,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=65.0, spring_rf=65.0, spring_lr=55.0, spring_rr=55.0,
            arb_front=3, arb_rear=2,
            rh_lf=63.0, rh_rf=63.0, rh_lr=80.0, rh_rr=80.0,
            bump_slow_lf=6, bump_slow_rf=6, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=8, rebound_slow_rf=8, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=25.0, diff_power_deg=30.0, diff_coast_deg=10.0,
            tc_1=6, abs_setting=5, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 28.5, 'RF': 28.5, 'LR': 27.5, 'RR': 27.5},
            camber_deg={'LF': -2.3, 'RF': -2.3, 'LR': -1.0, 'RR': -1.0},
            brake_bias_pct=57.5,
            key_adjustments=["Balance front grip and rotation", "Trail-brake to rotate nose"],
            priority_notes="Balanced TCR — trail braking is the main technique for rotation.",
            wing_front_step=2, wing_rear_step=2,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=60.0, spring_rf=60.0, spring_lr=50.0, spring_rr=50.0,
            arb_front=4, arb_rear=3,
            rh_lf=65.0, rh_rf=65.0, rh_lr=82.0, rh_rr=82.0,
            bump_slow_lf=6, bump_slow_rf=6, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=8, rebound_slow_rf=8, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=25.0, diff_power_deg=30.0, diff_coast_deg=10.0,
            tc_1=6, abs_setting=5, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 29.0, 'RF': 29.0, 'LR': 28.0, 'RR': 28.0},
            camber_deg={'LF': -2.8, 'RF': -2.8, 'LR': -1.3, 'RR': -1.3},
            brake_bias_pct=57.0,
            key_adjustments=["Maximize front grip at technical tracks", "More front camber for cornering"],
            priority_notes="TCR at technical circuits — front tire life is the primary constraint.",
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=-0.5, toe_rear_mm=2.0,
            spring_lf=55.0, spring_rf=55.0, spring_lr=45.0, spring_rr=45.0,
            arb_front=4, arb_rear=3,
            rh_lf=68.0, rh_rf=68.0, rh_lr=85.0, rh_rr=85.0,
            bump_slow_lf=5, bump_slow_rf=5, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=7, rebound_slow_rf=7, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=4, rebound_fast_rf=4, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=25.0, diff_power_deg=30.0, diff_coast_deg=10.0,
            tc_1=5, abs_setting=4, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # V8 SUPERCAR
    # ══════════════════════════════════════════════════════════════════════════
    "v8_supercar": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 26.0, 'RF': 26.0, 'LR': 25.0, 'RR': 25.0},
            camber_deg={'LF': -2.5, 'RF': -2.5, 'LR': -1.0, 'RR': -1.0},
            brake_bias_pct=56.0,
            key_adjustments=["Reduce drag", "Stiffen rear for stability at speed"],
            priority_notes="V8 Supercar low-drag — heavy car so good braking stability critical.",
            wing_front_step=2, wing_rear_step=2,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=80.0, spring_rf=80.0, spring_lr=90.0, spring_rr=90.0,
            arb_front=4, arb_rear=5,
            rh_lf=70.0, rh_rf=70.0, rh_lr=85.0, rh_rr=85.0,
            bump_slow_lf=8, bump_slow_rf=8, bump_slow_lr=7, bump_slow_rr=7,
            bump_fast_lf=5, bump_fast_rf=5, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=10, rebound_slow_rf=10, rebound_slow_lr=9, rebound_slow_rr=9,
            rebound_fast_lf=6, rebound_fast_rf=6, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=75.0, diff_power_deg=45.0, diff_coast_deg=5.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 26.5, 'RF': 26.5, 'LR': 25.5, 'RR': 25.5},
            brake_bias_pct=55.5,
            key_adjustments=["Balance mechanical grip with limited aero"],
            priority_notes="Balanced V8 Supercar setup.",
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=75.0, spring_rf=75.0, spring_lr=85.0, spring_rr=85.0,
            arb_front=4, arb_rear=4,
            rh_lf=72.0, rh_rf=72.0, rh_lr=88.0, rh_rr=88.0,
            bump_slow_lf=7, bump_slow_rf=7, bump_slow_lr=6, bump_slow_rr=6,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=9, rebound_slow_rf=9, rebound_slow_lr=8, rebound_slow_rr=8,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            diff_preload_nm=75.0, diff_power_deg=45.0, diff_coast_deg=5.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 27.0, 'RF': 27.0, 'LR': 26.0, 'RR': 26.0},
            brake_bias_pct=55.0,
            key_adjustments=["More downforce for street circuits", "Softer springs for compliance"],
            priority_notes="V8 Supercar at street circuit — softer to absorb bumps and kerbs.",
            wing_front_step=4, wing_rear_step=4,
            toe_front_mm=-0.5, toe_rear_mm=2.0,
            spring_lf=70.0, spring_rf=70.0, spring_lr=80.0, spring_rr=80.0,
            arb_front=5, arb_rear=5,
            rh_lf=75.0, rh_rf=75.0, rh_lr=92.0, rh_rr=92.0,
            bump_slow_lf=6, bump_slow_rf=6, bump_slow_lr=6, bump_slow_rr=6,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=8, rebound_slow_rf=8, rebound_slow_lr=8, rebound_slow_rr=8,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=75.0, diff_power_deg=45.0, diff_coast_deg=5.0,
            tc_1=3, abs_setting=3, brake_pressure_pct=94.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # STOCK  —  Springs in lb/in; oval setup philosophy
    # ══════════════════════════════════════════════════════════════════════════
    "stock": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 30.0, 'RF': 30.0, 'LR': 29.0, 'RR': 29.0},
            brake_bias_pct=60.0,
            key_adjustments=["Reduce drag at superspeedway", "Manage stagger", "Tire wear over long stints"],
            priority_notes="Stock car superspeedway — manage aero push and tire degradation.",
            toe_front_mm=0.0, toe_rear_mm=0.5,
            spring_lf=800.0, spring_rf=1000.0, spring_lr=900.0, spring_rr=1100.0,
            spring_unit="lb/in",
            arb_front=3, arb_rear=4,
            rh_lf=120.0, rh_rf=125.0, rh_lr=130.0, rh_rr=135.0,
            bump_slow_lf=7, bump_slow_rf=7, bump_slow_lr=6, bump_slow_rr=6,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=9, rebound_slow_rf=9, rebound_slow_lr=8, rebound_slow_rr=8,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            tc_1=4, abs_setting=4, brake_pressure_pct=100.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 31.0, 'RF': 31.0, 'LR': 30.0, 'RR': 30.0},
            brake_bias_pct=59.0,
            key_adjustments=["Balance push vs loose", "Tune track bar and wedge"],
            priority_notes="Balanced stock car setup for short ovals.",
            spring_lf=650.0, spring_rf=850.0, spring_lr=750.0, spring_rr=950.0,
            spring_unit="lb/in",
            arb_front=4, arb_rear=4,
            rh_lf=125.0, rh_rf=130.0, rh_lr=135.0, rh_rr=140.0,
            bump_slow_lf=7, bump_slow_rf=7, bump_slow_lr=6, bump_slow_rr=6,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=9, rebound_slow_rf=9, rebound_slow_lr=8, rebound_slow_rr=8,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            tc_1=4, abs_setting=4, brake_pressure_pct=100.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 32.0, 'RF': 32.0, 'LR': 31.0, 'RR': 31.0},
            brake_bias_pct=58.0,
            key_adjustments=["Road course / short track", "Stiffer sway bars", "More balanced setup"],
            priority_notes="Stock car road course — transition to conventional road-course philosophy.",
            spring_lf=550.0, spring_rf=700.0, spring_lr=650.0, spring_rr=800.0,
            spring_unit="lb/in",
            arb_front=5, arb_rear=5,
            rh_lf=130.0, rh_rf=135.0, rh_lr=140.0, rh_rr=145.0,
            bump_slow_lf=6, bump_slow_rf=6, bump_slow_lr=6, bump_slow_rr=6,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=4, bump_fast_rr=4,
            rebound_slow_lf=8, rebound_slow_rf=8, rebound_slow_lr=8, rebound_slow_rr=8,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=5, rebound_fast_rr=5,
            tc_1=4, abs_setting=4, brake_pressure_pct=100.0,
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # RALLY CROSS / ROAD ROOKIE / SPORTS CAR  —  Simpler entries
    # ══════════════════════════════════════════════════════════════════════════
    "rally_cross": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 24.0, 'RF': 24.0, 'LR': 23.0, 'RR': 23.0},
            brake_bias_pct=55.0,
            key_adjustments=["Lower pressures for dirt grip", "Soft suspension for loose surface"],
            priority_notes="Rallycross — compromise between dirt and tarmac sections.",
            spring_lf=45.0, spring_rf=45.0, spring_lr=40.0, spring_rr=40.0,
            arb_front=2, arb_rear=2,
            rh_lf=80.0, rh_rf=80.0, rh_lr=95.0, rh_rr=95.0,
            bump_slow_lf=5, bump_slow_rf=5, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=7, rebound_slow_rf=7, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=4, rebound_fast_rf=4, rebound_fast_lr=4, rebound_fast_rr=4,
            tc_1=5, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 25.0, 'RF': 25.0, 'LR': 24.0, 'RR': 24.0},
            brake_bias_pct=54.0,
            key_adjustments=["Balance dirt and paved sections"],
            priority_notes="Balanced rallycross setup.",
            spring_lf=50.0, spring_rf=50.0, spring_lr=45.0, spring_rr=45.0,
            arb_front=3, arb_rear=3,
            rh_lf=78.0, rh_rf=78.0, rh_lr=93.0, rh_rr=93.0,
            bump_slow_lf=5, bump_slow_rf=5, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=7, rebound_slow_rf=7, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=4, rebound_fast_rf=4, rebound_fast_lr=4, rebound_fast_rr=4,
            tc_1=5, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 26.0, 'RF': 26.0, 'LR': 25.0, 'RR': 25.0},
            brake_bias_pct=53.0,
            key_adjustments=["More paved-focus", "Slightly stiffer for tarmac grip"],
            priority_notes="Rallycross setup biased toward tarmac sections.",
            spring_lf=55.0, spring_rf=55.0, spring_lr=50.0, spring_rr=50.0,
            arb_front=3, arb_rear=3,
            rh_lf=75.0, rh_rf=75.0, rh_lr=90.0, rh_rr=90.0,
            bump_slow_lf=6, bump_slow_rf=6, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=8, rebound_slow_rf=8, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=4, rebound_fast_rr=4,
            tc_1=4, abs_setting=4, brake_pressure_pct=95.0,
        ),
    },
    "dirt_oval": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 14.0, 'RF': 14.0, 'LR': 14.0, 'RR': 14.0},
            brake_bias_pct=50.0,
            key_adjustments=["Stagger is king", "Soft springs", "Left-side weight bias"],
            priority_notes="Dirt oval — stagger and weight distribution dominate setup.",
            spring_lf=150.0, spring_rf=200.0, spring_lr=175.0, spring_rr=225.0, spring_unit="lb/in",
            arb_front=2, arb_rear=2,
            rh_lf=100.0, rh_rf=105.0, rh_lr=110.0, rh_rr=115.0,
            bump_slow_lf=4, bump_slow_rf=4, bump_slow_lr=4, bump_slow_rr=4,
            bump_fast_lf=2, bump_fast_rf=2, bump_fast_lr=2, bump_fast_rr=2,
            rebound_slow_lf=6, rebound_slow_rf=6, rebound_slow_lr=6, rebound_slow_rr=6,
            rebound_fast_lf=3, rebound_fast_rf=3, rebound_fast_lr=3, rebound_fast_rr=3,
            tc_1=3, abs_setting=3, brake_pressure_pct=90.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 15.0, 'RF': 15.0, 'LR': 15.0, 'RR': 15.0},
            brake_bias_pct=50.0,
            key_adjustments=["Balance stagger with track conditions"],
            priority_notes="Medium dirt oval setup.",
            spring_lf=175.0, spring_rf=225.0, spring_lr=200.0, spring_rr=250.0, spring_unit="lb/in",
            arb_front=2, arb_rear=3,
            rh_lf=105.0, rh_rf=110.0, rh_lr=115.0, rh_rr=120.0,
            bump_slow_lf=4, bump_slow_rf=4, bump_slow_lr=4, bump_slow_rr=4,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=6, rebound_slow_rf=6, rebound_slow_lr=6, rebound_slow_rr=6,
            rebound_fast_lf=3, rebound_fast_rf=3, rebound_fast_lr=3, rebound_fast_rr=3,
            tc_1=3, abs_setting=3, brake_pressure_pct=90.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 16.0, 'RF': 16.0, 'LR': 16.0, 'RR': 16.0},
            brake_bias_pct=50.0,
            key_adjustments=["Stiffer for slick/packed track"],
            priority_notes="Packed dirt — slightly stiffer setup.",
            spring_lf=200.0, spring_rf=250.0, spring_lr=225.0, spring_rr=275.0, spring_unit="lb/in",
            arb_front=3, arb_rear=3,
            rh_lf=110.0, rh_rf=115.0, rh_lr=120.0, rh_rr=125.0,
            bump_slow_lf=5, bump_slow_rf=5, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=7, rebound_slow_rf=7, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=4, rebound_fast_rf=4, rebound_fast_lr=4, rebound_fast_rr=4,
            tc_1=3, abs_setting=3, brake_pressure_pct=90.0,
        ),
    },
    "road_rookie": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 30.0, 'RF': 30.0, 'LR': 29.0, 'RR': 29.0},
            camber_deg={'LF': -1.5, 'RF': -1.5, 'LR': -1.0, 'RR': -1.0},
            brake_bias_pct=55.0,
            key_adjustments=["Keep setup simple", "Focus on smooth inputs"],
            priority_notes="Beginner car — driver development matters more than setup tuning.",
            wing_front_step=2, wing_rear_step=2,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=35.0, spring_rf=35.0, spring_lr=30.0, spring_rr=30.0,
            arb_front=2, arb_rear=2,
            rh_lf=75.0, rh_rf=75.0, rh_lr=90.0, rh_rr=90.0,
            bump_slow_lf=5, bump_slow_rf=5, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=7, rebound_slow_rf=7, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=4, rebound_fast_rf=4, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=25.0, diff_power_deg=30.0, diff_coast_deg=5.0,
            tc_1=5, abs_setting=5, brake_pressure_pct=90.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 30.5, 'RF': 30.5, 'LR': 29.5, 'RR': 29.5},
            brake_bias_pct=54.0,
            key_adjustments=["Smooth inputs", "Consistent braking points"],
            priority_notes="Balanced entry-level setup.",
            wing_front_step=2, wing_rear_step=2,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=32.0, spring_rf=32.0, spring_lr=28.0, spring_rr=28.0,
            arb_front=3, arb_rear=3,
            rh_lf=77.0, rh_rf=77.0, rh_lr=92.0, rh_rr=92.0,
            bump_slow_lf=5, bump_slow_rf=5, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=7, rebound_slow_rf=7, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=4, rebound_fast_rf=4, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=25.0, diff_power_deg=30.0, diff_coast_deg=5.0,
            tc_1=5, abs_setting=5, brake_pressure_pct=90.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 31.0, 'RF': 31.0, 'LR': 30.0, 'RR': 30.0},
            brake_bias_pct=53.0,
            key_adjustments=["More aggressive camber", "Focus on rotation at slow corners"],
            priority_notes="Aggressive entry-level setup for technical tracks.",
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=-0.5, toe_rear_mm=2.0,
            spring_lf=28.0, spring_rf=28.0, spring_lr=25.0, spring_rr=25.0,
            arb_front=3, arb_rear=3,
            rh_lf=80.0, rh_rf=80.0, rh_lr=95.0, rh_rr=95.0,
            bump_slow_lf=4, bump_slow_rf=4, bump_slow_lr=4, bump_slow_rr=4,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=6, rebound_slow_rf=6, rebound_slow_lr=6, rebound_slow_rr=6,
            rebound_fast_lf=3, rebound_fast_rf=3, rebound_fast_lr=3, rebound_fast_rr=3,
            diff_preload_nm=25.0, diff_power_deg=30.0, diff_coast_deg=5.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=90.0,
        ),
    },
    "sports_car": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 28.0, 'RF': 28.0, 'LR': 27.0, 'RR': 27.0},
            camber_deg={'LF': -2.5, 'RF': -2.5, 'LR': -1.5, 'RR': -1.5},
            brake_bias_pct=56.0,
            key_adjustments=["Reduce drag", "Stable platform at speed"],
            priority_notes="Sports car low-drag setup for fast circuits.",
            wing_front_step=2, wing_rear_step=2,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=65.0, spring_rf=65.0, spring_lr=60.0, spring_rr=60.0,
            arb_front=3, arb_rear=3,
            rh_lf=65.0, rh_rf=65.0, rh_lr=80.0, rh_rr=80.0,
            bump_slow_lf=7, bump_slow_rf=7, bump_slow_lr=6, bump_slow_rr=6,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=9, rebound_slow_rf=9, rebound_slow_lr=8, rebound_slow_rr=8,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=40.0, diff_power_deg=40.0, diff_coast_deg=0.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 28.5, 'RF': 28.5, 'LR': 27.5, 'RR': 27.5},
            brake_bias_pct=55.0,
            key_adjustments=["Balance grip and stability"],
            priority_notes="Balanced sports car setup.",
            wing_front_step=3, wing_rear_step=3,
            toe_front_mm=0.0, toe_rear_mm=1.5,
            spring_lf=60.0, spring_rf=60.0, spring_lr=55.0, spring_rr=55.0,
            arb_front=4, arb_rear=4,
            rh_lf=67.0, rh_rf=67.0, rh_lr=83.0, rh_rr=83.0,
            bump_slow_lf=6, bump_slow_rf=6, bump_slow_lr=6, bump_slow_rr=6,
            bump_fast_lf=4, bump_fast_rf=4, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=8, rebound_slow_rf=8, rebound_slow_lr=8, rebound_slow_rr=8,
            rebound_fast_lf=5, rebound_fast_rf=5, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=40.0, diff_power_deg=40.0, diff_coast_deg=0.0,
            tc_1=4, abs_setting=4, brake_pressure_pct=95.0,
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 29.0, 'RF': 29.0, 'LR': 28.0, 'RR': 28.0},
            brake_bias_pct=54.0,
            key_adjustments=["More camber for cornering", "Softer springs for technical track"],
            priority_notes="Technical track sports car setup.",
            wing_front_step=4, wing_rear_step=4,
            toe_front_mm=-0.5, toe_rear_mm=2.0,
            spring_lf=55.0, spring_rf=55.0, spring_lr=50.0, spring_rr=50.0,
            arb_front=4, arb_rear=4,
            rh_lf=70.0, rh_rf=70.0, rh_lr=87.0, rh_rr=87.0,
            bump_slow_lf=5, bump_slow_rf=5, bump_slow_lr=5, bump_slow_rr=5,
            bump_fast_lf=3, bump_fast_rf=3, bump_fast_lr=3, bump_fast_rr=3,
            rebound_slow_lf=7, rebound_slow_rf=7, rebound_slow_lr=7, rebound_slow_rr=7,
            rebound_fast_lf=4, rebound_fast_rf=4, rebound_fast_lr=4, rebound_fast_rr=4,
            diff_preload_nm=40.0, diff_power_deg=40.0, diff_coast_deg=0.0,
            tc_1=3, abs_setting=4, brake_pressure_pct=94.0,
        ),
    },
}


def list_tracks() -> List[str]:
    """Return list of available track names."""
    return sorted(_TRACKS.keys())


def get_track_info(track_name: str) -> Optional[TrackInfo]:
    """Get track information including downforce demand and tire stress.

    Uses fuzzy matching so iRacing telemetry names (e.g. 'roadamerica full')
    resolve to the canonical entry ('Road America').
    """
    return _find_track(track_name)


def get_baseline_setup_text(car_class: str, track_name: str) -> str:
    """
    Return a concrete, human-readable block of baseline setup values for a
    car class at a track.  Used as the 'START FROM THIS BASELINE' section of
    the AI setup-builder prompt so Claude adjusts known good numbers rather
    than inventing values from scratch.
    """
    template = get_setup_template(car_class, track_name)
    track_info = get_track_info(track_name)
    downforce = track_info.downforce_demand if track_info else "medium"

    lines = [
        f"Baseline for {car_class.upper()} at {track_name} (downforce demand: {downforce}):",
    ]

    if template.front_wing:
        lines.append(f"  Front wing:      {template.front_wing}")
    if template.rear_wing:
        lines.append(f"  Rear wing:       {template.rear_wing}")

    if template.tire_pressures_psi:
        p = template.tire_pressures_psi
        lines.append(
            f"  Cold pressures:  LF {p.get('LF', '?')} psi  RF {p.get('RF', '?')} psi  "
            f"LR {p.get('LR', '?')} psi  RR {p.get('RR', '?')} psi"
        )

    if template.camber_deg:
        c = template.camber_deg
        lines.append(
            f"  Camber:          LF {c.get('LF', '?')}°  RF {c.get('RF', '?')}°  "
            f"LR {c.get('LR', '?')}°  RR {c.get('RR', '?')}°"
        )

    if template.brake_bias_pct:
        lines.append(f"  Brake bias:      {template.brake_bias_pct}% front")

    # Toe
    if template.toe_front_mm is not None or template.toe_rear_mm is not None:
        tf = f"{template.toe_front_mm:+.1f} mm" if template.toe_front_mm is not None else "?"
        tr = f"{template.toe_rear_mm:+.1f} mm" if template.toe_rear_mm is not None else "?"
        lines.append(f"  Toe:             Front {tf}  Rear {tr}")

    # Springs
    if any(v is not None for v in [template.spring_lf, template.spring_rf,
                                    template.spring_lr, template.spring_rr]):
        u = template.spring_unit or "N/mm"
        lf = f"{template.spring_lf}" if template.spring_lf is not None else "?"
        rf = f"{template.spring_rf}" if template.spring_rf is not None else "?"
        lr = f"{template.spring_lr}" if template.spring_lr is not None else "?"
        rr = f"{template.spring_rr}" if template.spring_rr is not None else "?"
        lines.append(f"  Springs ({u}):  LF {lf}  RF {rf}  LR {lr}  RR {rr}")
    elif template.spring_notes:
        lines.append(f"  Springs:         {template.spring_notes}")

    # ARBs
    if template.arb_front is not None or template.arb_rear is not None:
        af = template.arb_front if template.arb_front is not None else "?"
        ar = template.arb_rear if template.arb_rear is not None else "?"
        lines.append(f"  ARBs:            Front {af}  Rear {ar}")
    elif template.arb_notes:
        lines.append(f"  ARBs:            {template.arb_notes}")

    # Ride heights
    if any(v is not None for v in [template.rh_lf, template.rh_rf,
                                    template.rh_lr, template.rh_rr]):
        lf = f"{template.rh_lf}" if template.rh_lf is not None else "?"
        rf = f"{template.rh_rf}" if template.rh_rf is not None else "?"
        lr = f"{template.rh_lr}" if template.rh_lr is not None else "?"
        rr = f"{template.rh_rr}" if template.rh_rr is not None else "?"
        lines.append(f"  Ride heights (mm): LF {lf}  RF {rf}  LR {lr}  RR {rr}")
    elif template.ride_height_notes:
        lines.append(f"  Ride heights:    {template.ride_height_notes}")

    # Slow bump dampers
    if any(v is not None for v in [template.bump_slow_lf, template.bump_slow_rf,
                                    template.bump_slow_lr, template.bump_slow_rr]):
        lf = template.bump_slow_lf if template.bump_slow_lf is not None else "?"
        rf = template.bump_slow_rf if template.bump_slow_rf is not None else "?"
        lr = template.bump_slow_lr if template.bump_slow_lr is not None else "?"
        rr = template.bump_slow_rr if template.bump_slow_rr is not None else "?"
        lines.append(f"  Bump slow:       LF {lf}  RF {rf}  LR {lr}  RR {rr}")

    # Fast bump dampers
    if any(v is not None for v in [template.bump_fast_lf, template.bump_fast_rf,
                                    template.bump_fast_lr, template.bump_fast_rr]):
        lf = template.bump_fast_lf if template.bump_fast_lf is not None else "?"
        rf = template.bump_fast_rf if template.bump_fast_rf is not None else "?"
        lr = template.bump_fast_lr if template.bump_fast_lr is not None else "?"
        rr = template.bump_fast_rr if template.bump_fast_rr is not None else "?"
        lines.append(f"  Bump fast:       LF {lf}  RF {rf}  LR {lr}  RR {rr}")

    # Slow rebound dampers
    if any(v is not None for v in [template.rebound_slow_lf, template.rebound_slow_rf,
                                    template.rebound_slow_lr, template.rebound_slow_rr]):
        lf = template.rebound_slow_lf if template.rebound_slow_lf is not None else "?"
        rf = template.rebound_slow_rf if template.rebound_slow_rf is not None else "?"
        lr = template.rebound_slow_lr if template.rebound_slow_lr is not None else "?"
        rr = template.rebound_slow_rr if template.rebound_slow_rr is not None else "?"
        lines.append(f"  Rebound slow:    LF {lf}  RF {rf}  LR {lr}  RR {rr}")

    # Fast rebound dampers
    if any(v is not None for v in [template.rebound_fast_lf, template.rebound_fast_rf,
                                    template.rebound_fast_lr, template.rebound_fast_rr]):
        lf = template.rebound_fast_lf if template.rebound_fast_lf is not None else "?"
        rf = template.rebound_fast_rf if template.rebound_fast_rf is not None else "?"
        lr = template.rebound_fast_lr if template.rebound_fast_lr is not None else "?"
        rr = template.rebound_fast_rr if template.rebound_fast_rr is not None else "?"
        lines.append(f"  Rebound fast:    LF {lf}  RF {rf}  LR {lr}  RR {rr}")

    # Fallback text damper notes (legacy)
    if template.damper_notes and not any(v is not None for v in [
            template.bump_slow_lf, template.bump_fast_lf,
            template.rebound_slow_lf, template.rebound_fast_lf]):
        lines.append(f"  Dampers:         {template.damper_notes}")

    # Differential
    if any(v is not None for v in [template.diff_preload_nm,
                                    template.diff_power_deg, template.diff_coast_deg]):
        parts = []
        if template.diff_preload_nm is not None:
            parts.append(f"Preload {template.diff_preload_nm} Nm")
        if template.diff_power_deg is not None:
            parts.append(f"Power ramp {template.diff_power_deg}°")
        if template.diff_coast_deg is not None:
            parts.append(f"Coast ramp {template.diff_coast_deg}°")
        lines.append(f"  Differential:    {', '.join(parts)}")

    # Electronics
    elec_parts = []
    if template.tc_1 is not None:
        elec_parts.append(f"TC {template.tc_1}")
    if template.abs_setting is not None:
        elec_parts.append(f"ABS {template.abs_setting}")
    if elec_parts:
        lines.append(f"  Electronics:     {', '.join(elec_parts)}")

    # Brake pressure
    if template.brake_pressure_pct is not None:
        lines.append(f"  Brake pressure:  {template.brake_pressure_pct}%")

    if template.key_adjustments:
        lines.append("  Key adjustments:")
        for adj in template.key_adjustments:
            lines.append(f"    • {adj}")

    if template.priority_notes:
        lines.append(f"  Priority note:   {template.priority_notes}")

    if track_info and track_info.setup_guidance:
        lines.append(f"\nTrack setup guidance:")
        lines.append(f"  {track_info.setup_guidance}")

    if track_info and track_info.key_priorities:
        lines.append("Track setup priorities (in order):")
        for i, p in enumerate(track_info.key_priorities, 1):
            lines.append(f"  {i}. {p}")

    return "\n".join(lines)


def get_setup_template(car_class: str, track_name: str) -> SetupTemplate:
    """
    Get a baseline setup template for a car class at a specific track.
    car_class: e.g. 'gt3', 'gtp', 'formula', 'stock', 'rally_cross', etc.
    track_name: track name string (fuzzy-matched)
    """
    car_class = car_class.lower()
    if car_class not in _TEMPLATES:
        # Fall back to closest match or gt3
        car_class = "gt3"

    track_info = get_track_info(track_name)
    downforce = track_info.downforce_demand if track_info else "medium"

    templates = _TEMPLATES[car_class]
    return templates.get(downforce, templates["medium"])
