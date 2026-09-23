import sys,json,collections
from pathlib import Path
sys.path.insert(0,'/Users/markjaysonfarol13/Projects/FSA/FSAVolumeReports_Panel-main/Scripts')
import fsa_build_utils as u
import pandas as pd
root=Path('/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling')
layout=u.data_layout(root); mapping=u.load_dictionary_map(layout)
entries=u.load_selected_panel_entries(layout)
summary=[]; tokens=[]; exclusions=[]; values=[]
for entry in entries:
 fam=entry['family']
 if fam not in ['grants','campus_based']:continue
 p=Path(entry['local_path']); parsed=u.parse_selected_sheet(p,fam,entry['period_type']); mapped,unmapped=u.apply_component_mapping(fam,parsed.frame,mapping)
 valid=mapped['opeid8'].apply(u.standardize_opeid8).notna()
 rebuilt,unmapped=u.prepare_component_panel_frame(fam,entry,parsed,mapping)
 saved=pd.read_parquet(u.component_cross_sections_dir(layout,fam)/f'panel_{fam}_{entry["award_year_start"]}.parquet')
 try: pd.testing.assert_frame_equal(rebuilt,saved); equal=True
 except AssertionError as ex: equal=str(ex)[:250]
 for c in mapped:
  if c in ['opeid8','school','state','zip_code','school_type']:continue
  s=mapped.loc[valid,c]; n=u.sanitize_numeric_series(s); bad=s.notna() & n.isna()
  if bad.any(): tokens.append({'file':p.name,'family':fam,'year':entry['award_year'],'column':c,'tokens':s[bad].value_counts().to_dict(),'n':int(bad.sum())})
  dec=n.notna() & n.mod(1).ne(0)
  if dec.any(): values.append({'file':p.name,'column':c,'fractional_count':int(dec.sum()),'rounding_delta':float((n.round()-n).sum()),'examples':s[dec].head(4).tolist()})
 if (~valid).any(): exclusions.append({'file':p.name,'dropped':int((~valid).sum()),'rows':mapped.loc[~valid,['opeid8','school']].fillna('').to_dict('records')})
 summary.append({'family':fam,'file':p.name,'year':entry['award_year'],'rows':len(saved),'rebuild_equal':equal,'unmapped':unmapped,'warnings':parsed.warnings})
result={'summary':summary,'coercions':tokens,'fractional':values,'excluded':exclusions}
Path('/tmp/fsa_grants_campus_audit.json').write_text(json.dumps(result,indent=2))
print('Files',len(summary),'equal',sum(x['rebuild_equal'] is True for x in summary),'unmapped',sum(len(x['unmapped']) for x in summary))
print('numeric coercions',json.dumps(tokens))
print('fractional dollar rounds',json.dumps(values))
print('excluded',json.dumps(exclusions))
