from datetime import date
from concurrent.futures import ThreadPoolExecutor

from agent.coshh_references import reserve_coshh_reference


def test_reference_registry_sequential_stable_and_concurrency_safe(tmp_path):
    db=tmp_path/"db"/"agent.db"
    root=tmp_path/"outputs"
    root.mkdir()
    dirs=[root/str(i) for i in range(20)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda x: reserve_coshh_reference(db,x), dirs))
    refs=[r[0] for r in results]
    assert set(refs)=={f"ES.COSHH.{i:03d}" for i in range(1,21)}
    assert all(d==date.today() for _,d in results)
    for folder,(reference,completed) in zip(dirs,results):
        assert reserve_coshh_reference(db,folder)==(reference,completed)


def test_same_run_keeps_reference_after_failed_retries(tmp_path):
    db=tmp_path/"registry.db"
    run=tmp_path/"outputs"/"Dihydrocodeine"/"run1"
    first=reserve_coshh_reference(db,run)
    assert first[0]=="ES.COSHH.001"
    assert reserve_coshh_reference(db,run)==first
    assert reserve_coshh_reference(db,run.parent/"run2")[0]=="ES.COSHH.002"
