#!/usr/bin/env python3
"""Package frozen FSA data and actual input bytes for public release assets."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
import pandas as pd

REPO=Path(__file__).resolve().parents[1]
TAG='fsa-research-v2-2026-09-22'

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def files(root):
    return sorted(p for p in Path(root).rglob('*') if p.is_file() and not p.is_symlink()
                  and not any(x in {'__pycache__','.pytest_cache','.DS_Store'} or x.startswith('._') for x in p.parts)
                  and p.suffix not in {'.pyc','.pyo'})

def copy(source,target,expected=None):
    if expected and digest(source)!=expected:raise ValueError(f'Changed input: {source}')
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
    if digest(source)!=digest(target):raise ValueError(f'Copy mismatch: {target}')

def stage(root,distribution):
    replication=distribution/'replication'
    release=json.loads((root/'build/research_release_manifest.json').read_text())
    selected=root/'Checks/download_qc/selected_panel_files.csv'
    for item in release['inputs']:
        source=Path(item['local_path'])
        parts=source.parts
        relative=Path(*parts[parts.index('Raw_Title_IV_Reports')+1:])
        copy(source,replication/'inputs/fsa'/relative,item['verified_sha256'])
    hd=REPO/'ResearchBuild/IPEDS/official_hd_v2'
    hd_manifest=pd.read_csv(root/'Panels/ipeds/ipeds_source_manifest.csv',keep_default_na=False)
    paths=set()
    for item in hd_manifest.to_dict('records'):
        if item['status']=='loaded':
            source=Path(item['path']);copy(source,replication/'inputs/ipeds_hd'/source.name,item['sha256']);paths.add(source)
    for source in files(hd):
        if source not in paths and (source.name.endswith('.json') or '_Dict' in source.name or
                                    source.name in {'IPEDS_2024-25_Provisional.zip','IPEDS202425Tablesdoc.xlsx'}):
            copy(source,replication/'inputs/ipeds_hd'/source.name)
    cw=REPO/'ResearchBuild/IPEDS/official_crosswalks'
    for source in files(cw):
        if (source.name.startswith('CW') and source.suffix=='.xlsx') or source.name in {'download_manifest.json','archive_listing.json'}:
            copy(source,replication/'inputs/ipeds_crosswalks'/source.name)
    for folder in ('annual_documentation','official_documentation'):
        base=REPO/'ResearchBuild/IPEDS'/folder
        for source in files(base):copy(source,replication/'inputs/ipeds_documentation'/folder/source.relative_to(base))
    snapshot=root/'build/source_snapshot'
    for item in release['code_and_metadata']:
        copy(snapshot/item['path'],replication/'source'/item['path'],item['sha256'])
    copy(root/'build/research_release_manifest.json',replication/'original_release_manifest.json')
    copy(root/'Panels/ipeds/unitid_research/manifest.json',replication/'original_unitid_manifest.json')
    copy(selected,replication/'selected_panel_files.csv')
    copy(root/'build/environment-requirements.txt',replication/'environment-requirements.txt')
    copy(REPO/'Metadata/reproduction_environment.txt',replication/'environment-lock.txt')
    runner=REPO/'Scripts/reproduce_frozen_release.py'
    if runner.exists():copy(runner,replication/runner.name)
    records=[{'path':str(p.relative_to(replication)),'bytes':p.stat().st_size,'sha256':digest(p)} for p in files(replication) if p.name!='input_manifest.json']
    (replication/'input_manifest.json').write_text(json.dumps({'schema_version':1,'release_tag':TAG,'files':records},indent=2)+'\n')
    print(f'Staged {len(records)} frozen replication files: {replication}',flush=True)
    return replication

def archive(path,members):
    if path.exists():raise ValueError(f'Archive already exists: {path}')
    names=set()
    with zipfile.ZipFile(path,'w',allowZip64=True) as z:
        for name,p in sorted(members):
            if name in names:raise ValueError(f'Duplicate archive path: {name}')
            names.add(name)
            compression=zipfile.ZIP_STORED if p.suffix in {'.zip','.gz','.xlsx','.parquet','.pdf'} else zipfile.ZIP_DEFLATED
            z.write(p,name,compress_type=compression,compresslevel=1)
    if path.stat().st_size>=2*1024**3:raise ValueError('GitHub asset size limit exceeded')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise ValueError('Archive CRC failure')
    print(f'Packaged {path.name}: {path.stat().st_size:,} bytes',flush=True)
    return {'name':path.name,'bytes':path.stat().st_size,'sha256':digest(path),'members':len(names)}

def package(root,distribution):
    replication=stage(root,distribution)
    if not (replication/'reproduce_frozen_release.py').exists():raise ValueError('Portable rebuild runner is missing')
    assets=distribution/'assets';assets.mkdir(exist_ok=True)
    exports=root/'Exports/unitid'
    export_manifest=json.loads((exports/'export_manifest.json').read_text())
    if export_manifest.get('all_checks_passed') is not True:raise ValueError('Exports not verified')
    for item in export_manifest['outputs']:
        if digest(exports/item['path'])!=item['sha256']:raise ValueError('Export changed')
    common=[('unitid/'+str(p.relative_to(exports)),p) for p in files(exports)
            if p.name not in {'fsa_unitid_panel.dta','fsa_unitid_panel.parquet','fsa_unitid_panel.csv.gz'} and 'excel' not in p.relative_to(exports).parts]
    # Supply original relative documentation targets without altering any frozen
    # export files or the hashes already recorded for them.
    for folder in ('Metadata','Analysis','Audit','Scripts','tests','Documentation'):
        common.extend(('unitid/'+folder+'/'+str(p.relative_to(REPO/folder)),p) for p in files(REPO/folder))
    evidence=REPO/'Documentation/evidence'
    common.extend(('unitid/documentation/evidence/'+str(p.relative_to(evidence)),p) for p in files(evidence))
    records=[]
    records.append(archive(assets/'fsa-research-v2-portable-data.zip',common+[(f'unitid/{name}',exports/name) for name in ('fsa_unitid_panel.parquet','fsa_unitid_panel.csv.gz')]))
    records.append(archive(assets/'fsa-research-v2-stata.zip',common+[('unitid/fsa_unitid_panel.dta',exports/'fsa_unitid_panel.dta')]))
    records.append(archive(assets/'fsa-research-v2-excel.zip',common+[('unitid/'+str(p.relative_to(exports)),p) for p in files(exports/'excel')]))
    canonical=[]
    for folder in ('Panels','Dictionary','Checks','Cross_sections','build'):
        canonical.extend(('canonical/'+str(p.relative_to(root)),p) for p in files(root/folder))
    records.append(archive(assets/'fsa-research-v2-canonical.zip',canonical))
    records.append(archive(assets/'fsa-research-v2-replication.zip',[('replication/'+str(p.relative_to(replication)),p) for p in files(replication)]))
    manifest={'schema_version':1,'release_tag':TAG,'repository':'markjayson13/FSAVolumeReports_Panel','assets':records,
              'source_release_manifest_sha256':digest(root/'build/research_release_manifest.json'),
              'export_manifest_sha256':digest(exports/'export_manifest.json'),
              'scope':'Frozen FSA research release and labeled exports, with original selected inputs and portable rebuild code.',
              'historical_paths':'Absolute paths in original evidence are retained as provenance; input_manifest.json uses portable relative paths.',
              'license_note':'No blanket project or third-party license is asserted. Original government sources and provenance are retained.',
              'native_stata_excel_execution':False}
    manifest_path=assets/'distribution_manifest.json';manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    sums=[f"{r['sha256']}  {r['name']}" for r in records]+[f'{digest(manifest_path)}  distribution_manifest.json']
    (assets/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True);p.add_argument('--distribution',required=True);p.add_argument('--stage-only',action='store_true')
    a=p.parse_args();root=Path(a.root).resolve();dist=Path(a.distribution).resolve();dist.mkdir(parents=True,exist_ok=True)
    if a.stage_only:stage(root,dist)
    else:package(root,dist)
