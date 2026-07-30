from hydrolite.water_balance_audit import reconcile_hydrologic_water_balance, write_water_balance_audit
def test_full_hydrologic_balance_gate(tmp_path):
    r=reconcile_hydrologic_water_balance('projects/qgis_workflow_project');assert r['validation']['status']=='passed';assert not r['tail'].truncated_tail.any();assert write_water_balance_audit(tmp_path,r)['ledger'].exists()
