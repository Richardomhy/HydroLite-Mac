import pandas as pd
from hydrolite.continuous_balance_audit import reconcile_reported_and_internal_fluxes

def test_complete_fluxes_reconcile():
    row={"interception_evaporation_mm":0,"actual_et_mm":1,"surface_runoff_mm":0,"interflow_mm":0,"baseflow_mm":0,"deep_loss_mm":0,"storage_change_mm":0,"water_balance_residual_mm":0}
    assert reconcile_reported_and_internal_fluxes(pd.DataFrame([row]))["status"]=="passed"
