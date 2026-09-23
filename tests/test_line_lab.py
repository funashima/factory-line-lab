"""Mathematical oracles, model semantics, reproducibility, and persistence."""
import copy
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest
import mock_line_editor as lab


def model(times, edges, capacity=1):
    return lab.LineModel({k: lab.NodeSpec(k,k,lab.ServiceSpec("constant",float(t)),capacity)
                          for k,t in times.items()},
                         [lab.EdgeSpec(str(i),a,b) for i,(a,b) in enumerate(edges)])


def test_single_server_hand_calculation():
    m = model({"A":3},[])
    result = lab.Simulator(m).run(np.full((3,1),3.), 1., True)
    assert result.makespan == 9
    assert [r["start"] for r in result.traces] == [0,3,6]
    assert [r["queue_wait"] for r in result.traces] == [0,2,4]
    assert result.metrics["A"]["queue_mean"] == 2
    assert result.metrics["A"]["utilization"] == 1


def test_capacity_two_and_saturated_arrivals():
    m = model({"A":3},[],capacity=2)
    r = lab.Simulator(m).run(np.full((5,1),3.),0,True)
    assert r.makespan == 9
    assert [x["start"] for x in r.traces] == [0,0,3,3,6]
    assert r.metrics["A"]["utilization"] == pytest.approx(15/18)


def test_serial_pipeline_closed_form():
    m = model({"A":2,"B":5,"C":1},[("A","B"),("B","C")])
    r = lab.Simulator(m).run(np.tile([2.,5.,1.],(6,1)),0,True)
    assert r.makespan == 8+5*5


def test_serial_random_times_against_independent_recurrence():
    m = model({"A":1,"B":1,"C":1},[("A","B"),("B","C")])
    services = np.random.default_rng(91).uniform(.1,5,(15,3))
    expected = np.zeros((15,3))
    for j in range(15):
        for k in range(3):
            ready = j*.7 if k==0 else expected[j,k-1]
            free = 0 if j==0 else expected[j-1,k]
            expected[j,k] = max(ready, free)+services[j,k]
    result = lab.Simulator(m).run(services,.7,True)
    actual = {(r["job"],r["process"]):r["finish"] for r in result.traces}
    for j in range(15):
        for k,nid in enumerate(("A","B","C")):
            assert actual[j,nid] == pytest.approx(expected[j,k])


def test_fork_join_requires_both_branches():
    m = model({"A":2,"B":3,"C":7,"D":1},[("A","B"),("A","C"),("B","D"),("C","D")])
    r = lab.Simulator(m).run(np.array([[2.,3.,7.,1.]]),0,True)
    d = next(x for x in r.traces if x["process"]=="D")
    assert (d["ready"],d["sync_wait"],d["queue_wait"],r.makespan)==(9,4,0,10)


def test_multiple_sources_and_sinks():
    m = model({"A":2,"B":5,"C":1,"D":4},[("A","C"),("B","C"),("B","D")])
    r = lab.Simulator(m).run(np.array([[2.,5.,1.,4.]]),0,True)
    assert r.makespan == 9


def test_precedence_resources_and_product_identity():
    m = lab.example_model("fork")
    m.nodes["N06"].capacity=2
    cfg=lab.SimulationConfig(jobs=40,runs=1)
    a=lab.draw_services(m,cfg,0)
    r=lab.Simulator(m).run(a,1,True)
    assert len(r.traces)==40*12
    lookup={(x["job"],x["process"]):x for x in r.traces}
    for x in r.traces:
        assert x["start"] >= x["ready"] >= x["release"]
        assert x["queue_wait"] >= 0
        assert x["finish"] == pytest.approx(x["start"]+x["service"])
        for e in m.edges:
            if e.dst==x["process"]: assert x["ready"] >= lookup[x["job"],e.src]["finish"]
    for nid,n in m.nodes.items():
        for server in range(n.capacity):
            spans=sorted((x["start"],x["finish"]) for x in r.traces if x["process"]==nid and x["server"]==server)
            assert all(a[1] <= b[0] for a,b in zip(spans,spans[1:]))
        assert 0 <= r.metrics[nid]["utilization"] <= 1+1e-12


def test_zero_duration_events_terminate():
    m = model({"A":1,"B":1,"C":1},[("A","B"),("B","C")])
    r=lab.Simulator(m).run(np.array([[0,0,1],[0,0,1]],dtype=float),0,True)
    assert r.makespan==2


@pytest.mark.parametrize('dist,p1,p2',[("constant",3,0),("normal",3,1),("uniform",1,5),("lognormal",3,1)])
def test_service_distributions(dist,p1,p2):
    a=lab.sample_service_times(np.random.default_rng(8),lab.ServiceSpec(dist,p1,p2),50000)
    assert np.isfinite(a).all() and (a>=0).all()
    if dist=="uniform": assert ((a>=1)&(a<5)).all()
    assert abs(a.mean()-3)<.035
    if dist=="lognormal": assert abs(a.std()-1)<.025


def test_seed_independence_of_node_order_and_repeat():
    m=lab.example_model("fork"); cfg=lab.SimulationConfig(jobs=10,runs=2)
    reverse=copy.deepcopy(m); reverse.nodes=dict(reversed(list(m.nodes.items())))
    a=lab.draw_services(m,cfg,0)
    np.testing.assert_array_equal(a,lab.draw_services(reverse,cfg,0))
    assert not np.array_equal(a,lab.draw_services(m,cfg,1))
    assert lab.run_experiment(m,cfg).summary == lab.run_experiment(reverse,cfg).summary


def test_counterfactual_analytical_gain():
    m=model({"A":2,"B":5,"C":1},[("A","B"),("B","C")])
    result=lab.run_experiment(m,lab.SimulationConfig(jobs=6,runs=2,interval=0))
    assert result.summary["improvement_top"]==["B"]
    assert result.summary["nodes"]["B"]["delta"]["mean"]==pytest.approx(3)
    assert result.summary["nodes"]["A"]["delta"]["mean"]==pytest.approx(.2)


def test_json_and_csv_roundtrip(tmp_path):
    m=lab.example_model("fork"); m.nodes["N02"].name="組立て工程"
    lab.write_json(tmp_path/"m.json",m.payload())
    assert lab.load_json(tmp_path/"m.json").payload()==m.payload()
    lab.save_csv(m,tmp_path)
    loaded=lab.load_csv(tmp_path)
    assert loaded.nodes==m.nodes
    assert {(e.src,e.dst) for e in loaded.edges}=={(e.src,e.dst) for e in m.edges}


@pytest.mark.parametrize("kind",["cycle","missing","duplicate","isolate","nan","capacity"])
def test_invalid_models_rejected(kind):
    m=lab.example_model()
    if kind=="cycle": m.edges.append(lab.EdgeSpec("extra","N12","N01"))
    if kind=="missing": m.edges[0].dst="UNKNOWN"
    if kind=="duplicate": m.edges.append(lab.EdgeSpec("extra","N01","N02"))
    if kind=="isolate": m.edges=m.edges[1:]
    if kind=="nan": m.nodes["N01"].service.p1=float("nan")
    if kind=="capacity": m.nodes["N01"].capacity=1.5
    with pytest.raises(ValueError): m.require_valid()


def test_duplicate_id_in_json_rejected(tmp_path):
    p=lab.example_model().payload(); p["nodes"].append(p["nodes"][0])
    lab.write_json(tmp_path/"m.json",p)
    with pytest.raises(ValueError): lab.load_json(tmp_path/"m.json")


def test_disconnected_draft_save_load_but_cannot_run(tmp_path):
    m=model({"A":2,"B":3},[])
    lab.write_json(tmp_path/"draft.json",m.payload())
    draft=lab.load_json(tmp_path/"draft.json",allow_draft=True)
    assert len(draft.nodes)==2
    with pytest.raises(ValueError): lab.Simulator(draft)


def test_ties_and_single_replication_uncertainty():
    assert lab.top_set({"B":3.,"A":3.})==["A","B"]
    assert lab.mean_ci([2.])["ci_low"] is None
    assert lab.mean_ci([2.,2.])["ci_low"]==2


def test_exported_model_restores_experiment_and_no_overwrite(tmp_path):
    m=model({"A":3},[])
    cfg=lab.SimulationConfig(jobs=4,runs=2,interval=.5,seed=17)
    result=lab.run_experiment(m,cfg)
    lab.export_result(result,tmp_path,figures=False)
    payload=json.loads((tmp_path/"model.json").read_text())
    assert lab.SimulationConfig(**payload["simulation"])==cfg
    with pytest.raises(ValueError): lab.export_result(result,tmp_path,False)


def test_cancel_request():
    with pytest.raises(lab.Cancelled):
        lab.run_experiment(lab.example_model(),lab.SimulationConfig(),cancelled=lambda:True)


def test_gui_selection_does_not_modify_model_and_deletion_clears_specs():
    os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
    app_class, window_class=lab.build_gui_classes()
    app=app_class.instance() or app_class([])
    w=window_class(); before=w.scene.snapshot().payload()
    for nid in ("N01","N06","N09"):
        w.scene.clearSelection(); w.scene.nodes[nid].setSelected(True); app.processEvents()
    assert w.scene.snapshot().payload()==before
    w.scene.delete_selected()
    assert "N09" not in w.scene.model.nodes
    assert all(e.src!="N09" and e.dst!="N09" for e in w.scene.model.edges)
    w.saved_snapshot=w.state_payload(); w.close()
