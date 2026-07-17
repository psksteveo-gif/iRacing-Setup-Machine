"""Tests for core.car_classifier — CarClass enum and classify_car()."""
import pytest

from core.car_classifier import CarClass, classify_car, PRESSURE_TARGETS, FUEL_EFFECT_S_PER_KG


class TestClassifyCar:
    @pytest.mark.parametrize("name,expected", [
        ("ferrari_296_gt3", CarClass.GT3),
        ("Mercedes AMG GT3", CarClass.GT3),
        ("bmw_m4_gt3", CarClass.GT3),
        ("mclaren_570s_gt4", CarClass.GT4),
        ("porsche_718_gt4", CarClass.GT4),
        ("porsche_992_cup", CarClass.PORSCHE_CUP),
        ("dallara_p217", CarClass.LMP2),
        ("acuraarx06gtp", CarClass.GTP),
        ("cadillacvseriesr", CarClass.GTP),
        ("formulair04", CarClass.FORMULA),
        ("dallarasfir23", CarClass.SUPER_FORMULA),
        ("hyundaitcn", CarClass.TCR),
        ("fordmustangfrgt3ichallenge", CarClass.GT4),
        ("crosscartn11", CarClass.RALLY_CROSS),
        ("dirtlatemodel", CarClass.DIRT_OVAL),
        ("mx5", CarClass.ROAD_ROOKIE),
        ("cadillacctsvr", CarClass.SPORTS_CAR),
        ("supercarsford", CarClass.V8_SUPERCAR),
        ("corvettec8rgte", CarClass.GTE),
        ("totally_unknown_car", CarClass.DEFAULT),
        # Regression: short generic keywords must not shadow specific cars in
        # later classes (longest-keyword-wins). See classify_car().
        ("nissangtpzxt", CarClass.PROTOTYPE),   # 'gtp' must not win over 'nissangtpzxt'
        ("protrucks", CarClass.RALLY_CROSS),    # 'trucks' must not win over 'protrucks'
    ])
    def test_classification(self, name, expected):
        assert classify_car(name) == expected

    def test_case_insensitive(self):
        a = classify_car("FERRARI_296_GT3")
        b = classify_car("ferrari_296_gt3")
        assert a == b

    def test_default_fallback(self):
        assert classify_car("xyzzy_9000") == CarClass.DEFAULT


class TestLookupDicts:
    def test_pressure_targets_for_all_classes(self):
        for cls in CarClass:
            assert cls in PRESSURE_TARGETS, f"Missing PRESSURE_TARGETS for {cls}"

    def test_fuel_effect_for_all_classes(self):
        for cls in CarClass:
            assert cls in FUEL_EFFECT_S_PER_KG, f"Missing FUEL_EFFECT for {cls}"

    def test_pressure_targets_have_four_corners(self):
        for cls, targets in PRESSURE_TARGETS.items():
            assert len(targets) == 4, f"{cls} needs 4 pressure targets"
