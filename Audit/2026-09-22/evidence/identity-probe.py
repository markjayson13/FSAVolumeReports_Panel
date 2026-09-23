from pathlib import Path
import sys,json,re
import pandas as pd
sys.path.insert(0,'/Users/markjaysonfarol13/Projects/FSA/FSAVolumeReports_Panel-main/Scripts')
import fsa_build_utils as u
r=Path('/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling')
out=Path('/tmp/fsa_identity_audit');out.mkdir(exist_ok=True)
e=pd.read_csv(r/'Checks/download_qc/selected_panel_files.csv',dtype=str).fillna('')
allrows=[];summaries=[]
for i,row in e.iterrows():
 p=u.parse_selected_sheet(Path(row.local_path),row.family,row.period_type)
 c=next(c for c in p.frame if u.normalize_token(c) in {'opeid','ope_id'})
 school=next((c for c in p.frame if u.normalize_token(c)=='school'),None)
 raw=p.frame[c].astype('string').fillna('').str.strip(); digits=raw.str.replace(r'\D','',regex=True)
 old=raw.apply(u.standardize_opeid8)
 # strict full-OPEID interpretation for 1-8 digit strings, with zero/blank IDs rejected.
 good=raw.str.fullmatch(r'\d{1,8}').fillna(False)&digits.ne('')&digits.str.contains('[1-9]')
 new=raw.where(good).str.zfill(8)
 mismatch=good & old.ne(new)
 f=pd.DataFrame({'family':row.family,'award_year':row.award_year,'filename':row.filename,'source_row':p.frame.index,'raw_opeid':raw,'current_opeid8':old,'full_opeid8':new,'school':p.frame[school] if school else '', 'mismatch':mismatch})
 allrows.append(f.loc[old.notna()])
 summaries.append({'family':row.family,'award_year':row.award_year,'filename':row.filename,'valid_rows':int(old.notna().sum()),'id_mismatches':int(mismatch.sum()),'raw_id_lengths':json.dumps({int(k):int(v) for k,v in raw.loc[good].str.len().value_counts().sort_index().items()}),'non_strict_accepted':int((old.notna()&~good).sum())})
 print(i+1,len(e),row.family,row.award_year,int(mismatch.sum()),flush=True)
a=pd.concat(allrows,ignore_index=True);s=pd.DataFrame(summaries)
a.to_csv(out/'source_id_audit.csv',index=False);s.to_csv(out/'source_id_summary.csv',index=False)
print('SUMMARY',s.groupby('family')[['valid_rows','id_mismatches','non_strict_accepted']].sum().to_string())
print('TOTAL',len(a),'mismatches',a.mismatch.sum(),'files',s.id_mismatches.gt(0).sum(),'allfiles',len(s))
print('CURRENT KEY UNION',len(a[['current_opeid8','award_year']].drop_duplicates()),'FULL ID KEY UNION',len(a[['full_opeid8','award_year']].drop_duplicates()))
print('CURRENT DISTINCT ID',a.current_opeid8.nunique(),'FULL DISTINCT ID',a.full_opeid8.nunique())
print('STRICT FULL FAMILY DUPES',a.duplicated(['family','full_opeid8','award_year']).sum())
print('MISMATCH YEARS',s.loc[s.id_mismatches.gt(0)].groupby('family').award_year.agg(list).to_dict())
