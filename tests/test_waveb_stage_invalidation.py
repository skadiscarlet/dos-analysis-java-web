"""The semantic repair cannot resume an older Auth/coverage stage."""
import pytest
import dosweb.production as production
import tests.test_production as production_helpers
from dosweb.pipeline import STAGES

@pytest.mark.parametrize('stage,old', [
    ('entries', 'production-v2.8-open-world-maturation-entries-v21'),
    ('lifecycle', 'production-v2.8-open-world-maturation-lifecycle-v20'),
    ('conclude', 'production-v2.8-open-world-maturation-conclude-v9'),
])
def test_pre_repair_cache_invalidates_changed_stage_and_downstream(tmp_path, monkeypatch, stage, old):
    helper = production_helpers.ProductionFactoryTests()
    calls = []
    values = helper._values(tmp_path, allow_remote_llm=True)
    versions = {**production._IMPLEMENTATION_VERSIONS, stage: old}
    with monkeypatch.context() as context:
        context.setattr(production, '_IMPLEMENTATION_VERSIONS', versions)
        stale = production.build_production_pipeline(values, environ={'DEEPSEEK_API_KEY':'fixture-not-a-key'}, stage_executors=helper._fake_executors(calls))
        assert stale.run('analyze')['status'] == 'completed'
    calls.clear()
    current = production.build_production_pipeline({**values,'resume':True}, environ={'DEEPSEEK_API_KEY':'fixture-not-a-key'}, stage_executors=helper._fake_executors(calls))
    assert current.run('analyze')['status'] == 'completed'
    assert calls == list(STAGES)[list(STAGES).index(stage):]
