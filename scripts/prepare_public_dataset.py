"""Read data only. Never imports/executes upstream code or calls a model/network.

Run with the project's venv. Outputs are versioned and existing differing files
are refused. --register adds datasets only; it never starts evaluation.
"""
import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.schemas import Sample
from app.core import model_input, input_hash
from app.email_input import TRANSFORMATION_VERSION, GMAIL_CONTRACT_REVISION

SOURCE = 'prompt_injections_so_back'
URL = 'https://github.com/compass-group-tue/prompt_injections_so_back'
NAME = 'Paired email scenarios'
DATA_FILE = 'defense_evaluation/paired_emails_dataset.json'
TECHNIQUES = {'fabricated_user_approval','fabricated_policy','fabricated_prior_agreement',
    'fabricated_manager_approval','role_authority_fabrication','system_integration_fiction',
    'deadline_with_preapproval','peer_precedent'}


def signature(text):
    words = re.findall(r"[a-z]+|#", re.sub(r'\d+', '#', text.lower()))
    return {' '.join(words[i:i+4]) for i in range(max(1,len(words)-3))}


def similarity(a, b):
    return len(a & b)/len(a | b) if a or b else 1.0


def select_pairs(records, seed, evaluation_pairs, development_pairs, similarity_threshold=.65):
    rng = random.Random(seed)
    eligible=[]; quarantined=[]; seen_ids=set(); hashes={}; duplicate_groups=[]
    for index, row in enumerate(records):
        reason=None
        try:
            a,b=row['pair']['attack'],row['pair']['benign']
            if row['id'] in seen_ids: reason='duplicate_source_id'
            elif not all(isinstance(x,str) and x.strip() for x in (a['external_content'],b['external_content'],a['user_prompt'],b['user_prompt'],row['scenario'])):
                reason='missing_content_or_context'
            elif a.get('expected_action')!='summarize_only' or b.get('expected_action')!='send_reply': reason='unexpected_source_label_semantics'
            elif a['external_content']==b['external_content']: reason='identical_attack_benign'
            elif a.get('injection_technique') not in TECHNIQUES: reason='unrecognized_generation_technique_requires_review'
            seen_ids.add(row['id'])
        except (KeyError,TypeError): reason='invalid_source_schema'
        if reason:
            quarantined.append({'source_sample_id':row.get('id'),'source_record_index':index,'reason':reason})
            continue
        eligible.append(row)
        for branch in ('attack','benign'):
            digest=input_hash(row['pair'][branch]['external_content'])
            hashes.setdefault(digest,[]).append((row['id'],branch))
    duplicate_groups=[items for items in hashes.values() if len(items)>1]
    conflicting={sid for items in duplicate_groups if len({branch for _,branch in items})>1 for sid,_ in items}
    if conflicting:
        quarantined.extend({'source_sample_id':sid,'reason':'same_body_conflicting_source_labels'} for sid in sorted(conflicting))
        eligible=[r for r in eligible if r['id'] not in conflicting]
    families=sorted({r['pair']['attack']['injection_technique'] for r in eligible})
    rng.shuffle(families)
    # Hold out entire authorization-claim families, stronger than random rows.
    dev_families=set(families[:max(1,len(families)//4)]) if development_pairs and len(families)>1 else set()
    dev_scenarios={r['scenario'] for r in eligible if r['pair']['attack']['injection_technique'] in dev_families}
    rng.shuffle(eligible)
    selected={'development':[],'evaluation':[]}; signatures=[]; scenarios=set(); skipped=[]
    for split, target in (('development',development_pairs),('evaluation',evaluation_pairs)):
        for row in eligible:
            if len(selected[split])>=target: break
            is_dev=row['pair']['attack']['injection_technique'] in dev_families
            if is_dev != (split=='development'): continue
            if split=='evaluation' and row['scenario'] in dev_scenarios: continue
            if row['scenario'] in scenarios: continue
            sigs=[signature(row['pair'][branch]['external_content']) for branch in ('attack','benign')]
            closest=max((similarity(s,t) for s in sigs for _,_,old in signatures for t in old),default=0)
            if closest>=similarity_threshold:
                skipped.append({'source_sample_id':row['id'],'reason':'near_duplicate','max_similarity':closest})
                continue
            selected[split].append(row); scenarios.add(row['scenario']); signatures.append((split,row['id'],sigs))
    cross=max((similarity(a,b) for sa,_,aa in signatures for sb,_,bb in signatures if sa!=sb for a in aa for b in bb),default=None)
    audit=dict(seed=seed,raw_pair_count=len(records),eligible_pairs=len(eligible),
        technique_counts=dict(Counter(r['pair']['attack']['injection_technique'] for r in eligible)),
        development_families=sorted(dev_families),evaluation_families=sorted(set(families)-dev_families),
        split_policy='entire derived claim family; repeated scenario excluded across splits; pair stays together',
        duplicate_body_groups=duplicate_groups,quarantined=quarantined,selection_skips=skipped,
        similarity_method='Jaccard of lowercase four-word shingles; digits normalized; no label changes',
        similarity_threshold=similarity_threshold,max_selected_cross_split_similarity=cross,
        selected={split:[r['id'] for r in rows] for split,rows in selected.items()},
        diversity_note='50 pairs are 50 paired cases, not 100 independent attacks. Similarity screening is a heuristic, not a proof of semantic independence.')
    return selected['evaluation'],selected['development'],audit


def convert_pair(row, version, file_hash, index, line=None):
    result=[]
    for branch,label in (('benign','NORMAL'),('attack','INJECTION')):
        entry=row['pair'][branch]; body=entry['external_content']
        sample=Sample.model_validate(dict(sample_id=f"so-back-{row['id']}-{branch}",subject='',body=body,label=label,
            language='en',category=row['category'],synthetic=True,created_at=None,
            template_family='claim:'+row['pair']['attack']['injection_technique'],pair_id=row['id'],
            source_dataset=SOURCE,source_dataset_name=NAME,source_url=URL,source_version=version,
            source_sample_id=f"{row['id']}/pair/{branch}",source_file=DATA_FILE,source_record_index=index,source_line=line,
            source_data_version=None,source_file_hash=file_hash,source_download_url=f'{URL}/blob/{version}/{DATA_FILE}',
            source_context={'scenario':row['scenario'],**{k:v for k,v in entry.items() if k!='external_content'}},
            transformation_version=TRANSFORMATION_VERSION,
            transformation_notes='Original external_content preserved; benign→NORMAL, attack→INJECTION from source pair, not attack success. Body-only evaluation; original user task retained outside model input. No Gmail/MIME parsing. Claim family derived from source technique for conservative split.',
            body_hash=input_hash(body),body_hash_method='SHA-256 of original external_content UTF-8; not RFC822 body bytes',
            email={'kind':'body_only','content':{'analysis_text':body,'text_plain':body,'trust':'UNTRUSTED'}})).model_dump()
        result.append(sample)
    return result


def write_preserving(path, data):
    text=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    if path.exists():
        if path.read_text(encoding='utf-8')!=text: raise RuntimeError(f'기존 생성 파일을 덮어쓰지 않습니다: {path}')
        return
    path.write_text(text,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=ROOT/'data/raw'/SOURCE)
    parser.add_argument('--output',type=Path,default=ROOT/'data/processed'/SOURCE)
    parser.add_argument('--seed',type=int,default=20261012)
    parser.add_argument('--evaluation-pairs',type=int,default=50)
    parser.add_argument('--development-pairs',type=int,default=10)
    parser.add_argument('--register',action='store_true',help='로컬 catalog에만 추가. 평가 시작 안 함')
    args=parser.parse_args()
    if args.evaluation_pairs<1 or args.development_pairs<0: parser.error('평가 쌍은 1 이상, 개발 쌍은 0 이상')
    version=subprocess.check_output(['git','-C',str(args.raw),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(args.raw),'status','--porcelain','--untracked-files=no'],text=True).strip()
    if dirty: raise RuntimeError('원본 추적 파일이 수정되어 commit만으로 재현할 수 없습니다. 원본을 보존하고 별도로 확인하세요.')
    source=args.raw/DATA_FILE; raw=source.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
    records=json.loads(raw); readme=(args.raw/'README.md').read_text(encoding='utf-8')
    if '| Paired email scenarios |' not in readme: raise RuntimeError('README 데이터셋 표시 이름이 변경되었습니다. 재확인 필요')
    evaluation,development,audit=select_pairs(records,args.seed,args.evaluation_pairs,args.development_pairs)
    locations={r['id']:(i,None) for i,r in enumerate(records)}
    for number,line in enumerate(raw.decode('utf-8').splitlines(),1):
        match=re.fullmatch(r'    "id": "([^"]+)",',line)
        if match and match[1] in locations: locations[match[1]]=(locations[match[1]][0],number)
    manifest=dict(source_dataset=SOURCE,source_dataset_name=NAME,source_url=URL,source_version=version,
        source_data_file=DATA_FILE,source_data_version=None,source_file_sha256=digest,source_download_url=f'{URL}/blob/{version}/{DATA_FILE}',
        license=None,license_note='No license file or README license grant found at inspected revision. Public availability does not establish reuse/redistribution permission.',
        synthetic=True,synthetic_evidence='README: Generate paired email scenarios with an LLM; generate_data/generate_dataset.py and generation_prompt.txt read, not executed.',
        label_evidence='classifier_eval/eval_classifier.py maps pair.benign to 0 and pair.attack to 1; no attack outcome used.',
        label_scope='Contextual fabricated-authorization social engineering as defined by source. Generation prompt also contrasts this with traditional prompt injection. Body-only classification does not establish action authorization or agent defense success.',
        transformation_version=TRANSFORMATION_VERSION,gmail_contract_revision=GMAIL_CONTRACT_REVISION,
        single_source=True,assessment_scope='body_text_only',seed=args.seed,
        limitations=['Single English synthetic source; no Gmail/EML/MIME/header/attachment verification.','Source user task omitted from detector input by design; preserved in evaluation metadata.','Semantic label and family judgments have not been independently human-adjudicated.'],
        selection_audit=audit)
    out=args.output/f'{version[:12]}-seed{args.seed}'
    out.mkdir(parents=True,exist_ok=True)
    datasets=[]
    for split,rows,target in (('evaluation',evaluation,args.evaluation_pairs),('development',development,args.development_pairs)):
        samples=[s for row in rows for s in convert_pair(row,version,digest,*locations[row['id']])]
        checks=[dict(sample_id=s['sample_id'],input_hash=input_hash(model_input(s)),input_bytes=len(model_input(s).encode('utf-8')),original_body_hash=s['body_hash']) for s in samples]
        dataset=dict(name=f'공개 paired emails · {"최종 평가" if split=="evaluation" else "개발"} · seed {args.seed}',split=split,
            manifest={**manifest,'requested_pairs':target,'selected_pairs':len(rows),'input_checks':checks},samples=samples)
        write_preserving(out/f'{split}.json',dataset)
        if samples: datasets.append(dataset)
        print(f'{split}: NORMAL {len(rows)}, INJECTION {len(rows)} (목표 {target}쌍)')
    write_preserving(out/'selection_manifest.json',manifest)
    write_preserving(out/'review_required.json',audit['quarantined'])
    print(f'output: {out}\nrevision: {version}\nsource sha256: {digest}')
    if args.register:
        from app.store import Store
        store=Store(ROOT/'runtime')
        for data in datasets:
            existing=next((d for d in store.list_datasets() if d['name']==data['name'] and (d.get('manifest') or {}).get('source_file_sha256')==digest),None)
            saved=existing or store.save_dataset(data)
            print(f"catalog: {saved['id']} ({data['split']}); 평가 시작 안 함")


if __name__=='__main__': main()
