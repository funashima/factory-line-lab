#!/usr/bin/env python3
"""Compare topology, lognormal coefficient of variation and release interval.
Run from this folder: python variance_sweep.py --out results/variance_01 --runs 50
"""
import argparse
import hashlib
from pathlib import Path
import numpy as np
import mock_line_editor as lab


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--runs',type=int,default=50)
    p.add_argument('--jobs',type=int,default=60)
    p.add_argument('--seed',type=int,default=42)
    args=p.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        p.error('Use an empty output directory')
    rows=[]
    for kind in ('serial','fork'):
        for interval in (1.,5.):
            for cv in (0.,.15,.5):
                name=f'{kind}_interval{interval:g}_cv{cv:g}'
                print(name,flush=True)
                model=lab.example_model(kind)
                for nid,node in model.nodes.items():
                    mean=4.5 if nid=='N06' else 3.
                    node.service=lab.ServiceSpec('lognormal',mean,mean*cv)
                cfg=lab.SimulationConfig(jobs=args.jobs,runs=args.runs,interval=interval,seed=args.seed)
                result=lab.run_experiment(model,cfg)
                lab.export_result(result,args.out/name,figures=False)
                gain=result.summary['nodes']['N06']['delta']
                row=dict(case=name,kind=kind,interval=interval,cv=cv,
                    makespan=result.summary['makespan']['mean'],
                    makespan_ci_low=result.summary['makespan']['ci_low'],
                    makespan_ci_high=result.summary['makespan']['ci_high'],
                    N01_queue=result.summary['nodes']['N01']['queue_mean']['mean'],
                    N06_queue=result.summary['nodes']['N06']['queue_mean']['mean'],
                    N06_gain=gain['mean'],N06_gain_ci_low=gain['ci_low'],N06_gain_ci_high=gain['ci_high'],
                    improvement_top='|'.join(result.summary['improvement_top']),
                    queue_top='|'.join(result.summary['queue_top']))
                rows.append(row)
    lab.write_csv(args.out/'variance_summary.csv',rows)
    lab.write_json(args.out/'study.json',dict(jobs=args.jobs,runs=args.runs,seed=args.seed,
        cv=[0,.15,.5],interval=[1,5],target='N06',dist='lognormal',
        note='Exploratory finite-batch comparison, not a real-factory validation or independent ground truth.',
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,2,figsize=(10,4))
    for kind in ('serial','fork'):
        for interval in (1.,5.):
            selected=[r for r in rows if r['kind']==kind and r['interval']==interval]
            for ax,key in zip(axs,('makespan','N06_gain')):
                ax.plot([r['cv'] for r in selected],[r[key] for r in selected],
                        marker='o',linestyle='-' if interval==1 else '--',label=f'{kind}, interval={interval:g}')
    for ax,label in zip(axs,('Mean batch makespan','Makespan reduction by improving N06')):
        ax.set_xlabel('Service-time coefficient of variation');ax.set_ylabel(label);ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(args.out/'variance.png',dpi=180);fig.savefig(args.out/'variance.pdf');plt.close(fig)


if __name__=='__main__':
    main()
