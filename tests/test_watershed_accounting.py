from hydrolite.watershed_accounting import build_water_accounting_ledger, assess_accounting_completeness
def test_accounting_keeps_missing_blank():
    ledger=build_water_accounting_ledger({"surface_runoff":1})
    assert ledger.loc[ledger.component=="evapotranspiration","value"].isna().all()
    assert assess_accounting_completeness(ledger) == "partial"
