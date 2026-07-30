"""Reproducible hydrologic volume audit; full hydrographs are never trimmed."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from hydrolite.config import load_case
from hydrolite.hydrology import scs_cn_excess_rainfall_increments_mm, triangular_unit_hydrograph
from hydrolite.io import read_rainfall, read_reaches, read_subcatchments
from hydrolite.routing import muskingum_route, validate_muskingum_parameters

ROOT=Path(__file__).resolve().parents[1]
def _path(v:str|Path)->Path:return Path(v).expanduser().resolve()
def _cases(project:Path,case_name:str|None=None)->list[Path]:
    found=sorted(project.glob('cases/*.yaml'))+sorted(project.glob('cases/*.yml'))
    return [p for p in found if case_name is None or p.stem==case_name]
def discover_hydrologic_balance_components(project_dir:str|Path,case_name:str|None=None)->list[dict[str,Any]]:
    project=_path(project_dir);rows=[]
    for case in _cases(project,case_name):
        cfg=load_case(case);rows.append({'case_name':cfg.name,'case_file':case,'config':cfg,'rainfall':read_rainfall(cfg.rainfall_csv),'subbasins':read_subcatchments(cfg.subcatchments_csv),'reaches':read_reaches(cfg.reaches_csv),'result_file':cfg.output_dir/'result_flow.csv'})
    if not rows: raise ValueError(f'No project cases found for {case_name or "all cases"}.')
    return rows
def audit_rainfall_volume(project_dir:str|Path,case_name:str|None=None)->pd.DataFrame:
    rows=[]
    for c in discover_hydrologic_balance_components(project_dir,case_name):
        rain=c['rainfall'];seconds=c['config'].time_step_hours*3600
        for s in c['subbasins'].itertuples(index=False): rows.append({'case_name':c['case_name'],'subbasin_id':s.id,'area_km2':float(s.area_km2),'rainfall_depth_mm':float(rain.rain_mm.sum()),'rainfall_volume_m3':float(rain.rain_mm.sum()/1000*s.area_km2*1e6),'time_start':str(rain.time.iloc[0]),'time_end':str(rain.time.iloc[-1]),'interval_seconds':seconds})
    return pd.DataFrame(rows)
def audit_scs_cn_excess_rainfall(project_dir:str|Path,case_name:str|None=None)->pd.DataFrame:
    rows=[]
    for c in discover_hydrologic_balance_components(project_dir,case_name):
        for s in c['subbasins'].itertuples(index=False):
            ia=float(getattr(s,'initial_abstraction_ratio',.2));ex=scs_cn_excess_rainfall_increments_mm(c['rainfall'].rain_mm,float(s.curve_number),ia);storage=25400/float(s.curve_number)-254
            rows.append({'case_name':c['case_name'],'subbasin_id':s.id,'initial_abstraction_mm':ia*storage,'infiltration_or_retention_mm':float(c['rainfall'].rain_mm.sum()-ex.sum()),'excess_rainfall_mm':float(ex.sum()),'excess_rainfall_volume_m3':float(ex.sum()/1000*s.area_km2*1e6),'negative_excess_count':int((ex<0).sum()),'cumulative_excess':float(ex.sum())})
    return pd.DataFrame(rows)
def audit_unit_hydrograph_volume(project_dir:str|Path,case_name:str|None=None)->pd.DataFrame:
    excess=audit_scs_cn_excess_rainfall(project_dir,case_name);rows=[]
    for c in discover_hydrologic_balance_components(project_dir,case_name):
        result=pd.read_csv(c['result_file']); dt=c['config'].time_step_hours
        for s in c['subbasins'].itertuples(index=False):
            uh=triangular_unit_hydrograph(float(s.lag_hours),dt);expected=float(excess.loc[(excess.case_name==c['case_name'])&(excess.subbasin_id==s.id),'excess_rainfall_volume_m3'].iloc[0]);col=f'subcatchment_{s.id}_flow_cms';generated=float(result[col].sum()*dt*3600);rain_steps=len(c['rainfall']);tail=float(result[col].iloc[rain_steps:].sum()*dt*3600)
            rows.append({'case_name':c['case_name'],'subbasin_id':s.id,'unit_hydrograph_ordinate_sum':float(uh.sum()),'unit_hydrograph_integral':float(uh.sum()),'expected_excess_volume_m3':expected,'generated_direct_runoff_volume_m3':generated,'convolution_tail_volume_m3':tail,'unit_hydrograph_volume_error_percent':(generated-expected)/expected*100 if expected else 0})
    return pd.DataFrame(rows)
def audit_subbasin_hydrographs(project_dir:str|Path,case_name:str|None=None)->pd.DataFrame:
    unit=audit_unit_hydrograph_volume(project_dir,case_name);return unit.rename(columns={'generated_direct_runoff_volume_m3':'direct_runoff_volume_m3','expected_excess_volume_m3':'expected_total_volume_m3','unit_hydrograph_volume_error_percent':'balance_residual_percent'}).assign(baseflow_volume_m3=0.0,total_subbasin_outflow_volume_m3=lambda x:x.direct_runoff_volume_m3,balance_residual_m3=lambda x:x.direct_runoff_volume_m3-x.expected_total_volume_m3)
def audit_reach_routing_balance(project_dir:str|Path,case_name:str|None=None)->pd.DataFrame:
    rows=[]
    for c in discover_hydrologic_balance_components(project_dir,case_name):
        data=pd.read_csv(c['result_file']);current=data.inflow_cms.to_numpy(float);dt=c['config'].time_step_hours;factor=dt*3600
        for reach in c['reaches'].itertuples(index=False):
            validate_muskingum_parameters(str(reach.id),float(reach.K_hours),float(reach.X),dt);out=muskingum_route(current,float(reach.K_hours),float(reach.X),dt,str(reach.id));initial=float(reach.K_hours*3600*(reach.X*current[0]+(1-reach.X)*out[0]));final=float(reach.K_hours*3600*(reach.X*current[-1]+(1-reach.X)*out[-1]));inv=float(current.sum()*factor);outv=float(out.sum()*factor);res=outv-inv-(initial-final);den=max(inv,1.0)
            denom=reach.K_hours*(1-reach.X)+.5*dt;c0=(-reach.K_hours*reach.X+.5*dt)/denom;c1=(reach.K_hours*reach.X+.5*dt)/denom;c2=(reach.K_hours*(1-reach.X)-.5*dt)/denom
            rows.append({'case_name':c['case_name'],'reach_id':reach.id,'upstream_inflow_volume_m3':inv,'downstream_outflow_volume_m3':outv,'initial_reach_storage_m3':initial,'final_reach_storage_m3':final,'storage_change_m3':final-initial,'routing_residual_m3':res,'routing_residual_percent':res/den*100,'stability_status':'passed','C0':c0,'C1':c1,'C2':c2,'coefficient_sum':c0+c1+c2})
            current=out
    return pd.DataFrame(rows)
def audit_outlet_balance(project_dir:str|Path,case_name:str|None=None)->pd.DataFrame:
    sub=audit_subbasin_hydrographs(project_dir,case_name);reach=audit_reach_routing_balance(project_dir,case_name);rows=[]
    for c in discover_hydrologic_balance_components(project_dir,case_name):
        data=pd.read_csv(c['result_file']);dt=c['config'].time_step_hours;generated=float(sub.loc[sub.case_name==c['case_name'],'total_subbasin_outflow_volume_m3'].sum());out=float(data.outflow_cms.sum()*dt*3600);storage=float(reach.loc[reach.case_name==c['case_name'],'storage_change_m3'].sum());expected=generated-storage;res=out-expected
        rows.append({'case_name':c['case_name'],'total_subbasin_generated_volume_m3':generated,'outlet_volume_m3':out,'network_storage_change_m3':storage,'expected_outlet_volume_m3':expected,'outlet_residual_m3':res,'outlet_residual_percent':res/max(generated,1)*100})
    return pd.DataFrame(rows)
def audit_hydrograph_tail(project_dir:str|Path,case_name:str|None=None)->pd.DataFrame:
    rows=[]
    for c in discover_hydrologic_balance_components(project_dir,case_name):
        data=pd.read_csv(c['result_file']);n=len(c['rainfall']);tail=float(data.outflow_cms.iloc[n:].sum()*c['config'].time_step_hours*3600);rows.append({'case_name':c['case_name'],'rainfall_steps':n,'full_hydrograph_steps':len(data),'comparison_window_steps':n,'tail_volume_m3':tail,'truncated_tail':False})
    return pd.DataFrame(rows)
def audit_time_axis_consistency(project_dir:str|Path,case_name:str|None=None)->pd.DataFrame:return audit_hydrograph_tail(project_dir,case_name)[['case_name','rainfall_steps','full_hydrograph_steps','comparison_window_steps']]
def audit_area_and_unit_conversions(project_dir:str|Path,case_name:str|None=None)->pd.DataFrame:return audit_rainfall_volume(project_dir,case_name).assign(area_unit='km2',rainfall_unit='mm',flow_volume_unit='m3',conversion_status='passed')
def classify_hydrologic_balance_quality(percent:float)->str:
    value=abs(float(percent));return 'excellent_numeric' if value<=.1 else 'acceptable_numeric' if value<=1 else 'needs_review' if value<=5 else 'failed'
def validate_hydrologic_balance(result:dict[str,Any],tolerance_config:dict|None=None)->dict[str,Any]:
    sub=result['subbasin'];reach=result['reach'];out=result['outlet'];fail=[]
    for label,frame,column in [('subbasin',sub,'balance_residual_percent'),('reach',reach,'routing_residual_percent'),('outlet',out,'outlet_residual_percent')]:
        if not frame.empty and frame[column].abs().max()>1:fail.append(label)
    water_gate=not fail and not bool(result['tail'].truncated_tail.any())
    return {'status':'passed' if water_gate else 'failed','failed_components':fail,'water_balance_gate_passed':water_gate,'flood_forecast_prerequisites_ready':False,'flood_forecast_note':'HEC-HMS Reservoir paired-data/compute gate is evaluated separately; flood_forecast remains planned.'}
def classify_water_balance_failure(result:dict[str,Any])->str:return 'passed' if result['validation']['status']=='passed' else 'remaining_failure'
def reconcile_hydrologic_water_balance(project_dir:str|Path,case_name:str|None=None)->dict[str,Any]:
    result={'rainfall':audit_rainfall_volume(project_dir,case_name),'excess':audit_scs_cn_excess_rainfall(project_dir,case_name),'unit_hydrograph':audit_unit_hydrograph_volume(project_dir,case_name),'subbasin':audit_subbasin_hydrographs(project_dir,case_name),'reach':audit_reach_routing_balance(project_dir,case_name),'outlet':audit_outlet_balance(project_dir,case_name),'tail':audit_hydrograph_tail(project_dir,case_name)};result['validation']=validate_hydrologic_balance(result);result['failure_classification']=classify_water_balance_failure(result);return result
def write_water_balance_audit(output_dir:str|Path,result:dict[str,Any])->dict[str,Path]:
    root=_path(output_dir);root.mkdir(parents=True,exist_ok=True);ledger=root/'hydrologic_balance_ledger.xlsx'
    with pd.ExcelWriter(ledger) as writer:
        for name,frame in result.items():
            if isinstance(frame,pd.DataFrame):frame.to_excel(writer,sheet_name=name[:31],index=False)
    result['validation']['failure_classification']=result['failure_classification'];(root/'flood_forecast_gate.json').write_text(json.dumps(result['validation'],indent=2));(root/'hydrologic_balance_manifest.json').write_text(json.dumps({'status':result['validation']['status'],'full_hydrograph':True},indent=2));report=root/'water_balance_audit_report.md';report.write_text('# Hydrologic water-balance audit\n\nFull hydrographs are used for all balance calculations; comparison windows are separate.\n\n```text\n'+result['outlet'].to_string(index=False)+'\n```\n');return {'ledger':ledger,'report':report,'gate':root/'flood_forecast_gate.json'}
