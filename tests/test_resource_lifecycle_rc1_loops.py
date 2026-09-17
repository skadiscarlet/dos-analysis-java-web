from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest

from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query
from dosweb.resource_lifecycle.adapters import adapt_codeql_rows, extracted_to_dict
from dosweb.resource_lifecycle.commands import resource_analyze, resource_replay, _java_source_snapshot
from dosweb.resource_lifecycle.io import analysis_result_to_dict
from dosweb.resource_lifecycle.invariants import check_invariants
from dosweb.resource_lifecycle.properties import publish_properties
from dosweb.resource_lifecycle.models import AbstractInstance, AnalysisBudget, CountInterval, Event, Transition
from dosweb.resource_lifecycle.solver import apply_effect, initial_state, solve, state_subsumes, widen_state
from tests.support.fixture_database import fixture_database
from tests.test_resource_lifecycle_solver import effect, instance_effect, program_for, two_instance_program
from tests.test_resource_lifecycle_async_solver import task_program

ROOT = Path(__file__).resolve().parents[1]


def loop_program(*, clean: bool):
    effects = (effect('create'), effect('retain', holder_id='holder:request'))
    if clean:
        effects += (effect('release'), effect('drop', holder_id='holder:request'))
    return replace(program_for((
        Transition('loop', 'event:entry', 'event:entry', 'true', effects, 'internal', ()),
        Transition('exit', 'event:entry', 'event:normal', 'true', (), 'normal', ()),
    )), exit_event_ids=('event:normal',))


class FiniteLoopAbstractionTests(unittest.TestCase):
    def test_retired_objects_preserve_peak_without_bounding_allocation_history(self):
        result = solve(loop_program(clean=True), budget=AnalysisBudget())
        self.assertTrue(result.terminated)
        # Worklist convergence is not a proof that the concrete loop exits.
        self.assertFalse(result.termination_guaranteed)
        self.assertLess(result.steps, 32)
        state = result.exit_states['event:normal']
        self.assertEqual(0, dict(state.obligation_counts)['family:stream'].upper)
        self.assertEqual(0, dict(state.held_counts)['family:stream'].upper)
        self.assertEqual(1, dict(state.peak_held_counts)['family:stream'])
        self.assertIsNone(dict(state.allocation_counts)['family:stream'].upper)
        self.assertFalse(state.repeated_instances)
        self.assertGreater(result.solver_metrics['widening_count'], 0)
        self.assertGreater(result.solver_metrics['subsumption_count'], 0)
        self.assertTrue(result.traces['event:normal'].abstraction_steps)

    def test_retained_loop_converges_without_claiming_finite_or_structural_growth(self):
        result = solve(loop_program(clean=False), budget=AnalysisBudget())
        self.assertTrue(result.terminated)
        # Worklist convergence is not a proof that the concrete loop exits.
        self.assertFalse(result.termination_guaranteed)
        self.assertLess(result.steps, 32)
        state = result.exit_states['event:normal']
        self.assertIsNone(dict(state.held_counts)['family:stream'].upper)
        self.assertIsNone(dict(state.peak_held_counts)['family:stream'])
        self.assertNotIn('bounded', result.lifecycle_statuses)
        self.assertFalse(any('unbounded' in item or 'accumulation' in item for item in result.lifecycle_statuses))
        dimensions = check_invariants(loop_program(clean=False), result, (), timeout_ms=1000)
        properties = publish_properties('Loop.retained', dimensions, (), input_identity='fixed-loop')
        held = [item for item in properties if item['dimension'] == 'held_instances']
        self.assertTrue(held)
        self.assertTrue(all(item['status'] == 'unknown' and item['upper_bound'] is None for item in held))
        self.assertFalse(any(item['status'] in {'unbounded', 'accumulating', 'static_vulnerable'} for item in properties))

    def test_exclusive_negative_effects_stay_separate_through_idle_loop(self):
        base = two_instance_program()
        creates = tuple(instance_effect(identity, 'create') for identity in ('instance:a', 'instance:b'))
        program = replace(base,
            events=base.events + (Event('event:join', 'method', 'Fixture.handle', 'true'),),
            transitions=(
                Transition('choose:a', 'event:entry', 'event:join', 'a', creates + (instance_effect('instance:a', 'release'),), 'internal', ()),
                Transition('choose:b', 'event:entry', 'event:join', 'b', creates + (instance_effect('instance:b', 'release'),), 'internal', ()),
                Transition('idle', 'event:join', 'event:join', 'true', (), 'internal', ()),
                Transition('exit', 'event:join', 'event:normal', 'true', (), 'normal', ()),
            ), exit_event_ids=('event:normal',))
        first = solve(program, budget=AnalysisBudget())
        second = solve(program, budget=AnalysisBudget())
        self.assertTrue(first.terminated)
        self.assertEqual(analysis_result_to_dict(first), analysis_result_to_dict(second))
        state = first.exit_states['event:normal']
        self.assertEqual(CountInterval(1, 1), dict(state.obligation_counts)['family:stream'])
        self.assertFalse(state.must_released)
        self.assertEqual(frozenset({'instance:a', 'instance:b'}), state.open_obligations)

    def test_repeated_close_or_drop_cannot_erase_old_instances(self):
        state = initial_state(loop_program(clean=False))
        for item in (effect('create'), effect('retain', holder_id='holder:request'),
                     effect('create'), effect('retain', holder_id='holder:request'),
                     effect('release'), effect('release'),
                     effect('drop', holder_id='holder:request')):
            state = apply_effect(state, item).state
        self.assertEqual(2, dict(state.obligation_counts)['family:stream'].upper)
        self.assertTrue(state.held_edges)
        self.assertTrue(state.open_obligations)

    def test_equivalent_sync_diamonds_converge_without_merging_open_objects(self):
        base = two_instance_program()
        events = list(base.events)
        events.append(Event('diamond:0', 'method', 'Fixture.handle', 'true'))
        creates = tuple(instance_effect(identity, 'create') for identity in ('instance:a', 'instance:b'))
        transitions = [
            Transition('choose:a', 'event:entry', 'diamond:0', 'a',
                       creates + (instance_effect('instance:a', 'release'),), 'internal', ()),
            Transition('choose:b', 'event:entry', 'diamond:0', 'b',
                       creates + (instance_effect('instance:b', 'release'),), 'internal', ()),
        ]
        # Eight independent diamonds produce 256 edge histories per initial
        # branch, but each join has only the two distinct open-object states.
        for index in range(8):
            target = f'diamond:{index + 1}'
            events.append(Event(target, 'method', 'Fixture.handle', 'true'))
            for branch in ('left', 'right'):
                arm = f'diamond:{index}:{branch}'
                events.append(Event(arm, 'method', 'Fixture.handle', 'true'))
                transitions.extend((
                    Transition(arm + ':enter', f'diamond:{index}', arm, branch, (), 'internal', ()),
                    Transition(arm + ':join', arm, target, 'true', (), 'internal', ()),
                ))
        transitions.append(Transition('diamonds:exit', 'diamond:8', 'event:normal', 'true', (), 'normal', ()))
        program = replace(base, events=tuple(events), transitions=tuple(transitions),
                          exit_event_ids=('event:normal',))
        result = solve(program, budget=AnalysisBudget())
        self.assertTrue(result.terminated, result.unknown_reasons)
        self.assertLessEqual(result.steps, 2 * len(transitions))
        self.assertGreater(result.solver_metrics['subsumption_count'], 0)
        state = result.exit_states['event:normal']
        self.assertEqual(CountInterval(1, 1), dict(state.obligation_counts)['family:stream'])
        self.assertEqual(frozenset({'instance:a', 'instance:b'}), state.open_obligations)
        self.assertFalse(state.must_released)
        self.assertIn('obligation_gap', result.lifecycle_statuses)
        self.assertEqual(analysis_result_to_dict(result),
                         analysis_result_to_dict(solve(program, budget=AnalysisBudget())))

    def test_finite_cut_bound_counts_identities_and_unknown_effects_block_it(self):
        for count in (1, 2):
            for unknown in (False, True):
                with self.subTest(count=count, unknown=unknown):
                    program = task_program(field=True)
                    extra = ()
                    if count == 2:
                        program = replace(program, instances=program.instances + (
                            AbstractInstance('instance:extra', 'family:stream', 'recent', 'exact'),))
                        extra = (instance_effect('instance:extra', 'create'),
                                 instance_effect('instance:extra', 'retain', holder_id='holder:field'))
                    if unknown:
                        extra += (effect('unknown_call'),)
                    program = replace(program, transitions=tuple(
                        replace(edge, effects=edge.effects + extra) if edge.transition_id == 'allocate' else edge
                        for edge in program.transitions))
                    result = solve(program, budget=AnalysisBudget())
                    dimensions = check_invariants(program, result, (), timeout_ms=1000)
                    properties = publish_properties('Finite.cut', dimensions, (), input_identity='fixed-cut')
                    held = next(item for item in properties if item['dimension'] == 'held_instances'
                                and item['scope'] == 'all_tasks_terminated_after_request')
                    self.assertEqual('unknown' if unknown else 'bounded', held['status'])
                    self.assertEqual(None if unknown else count, held['upper_bound'])
                    if not unknown:
                        self.assertIn('per_invocation_exact_allocation_population', held['assumptions'])

    def test_finite_single_invocation_does_not_prove_unsliced_holder_capacity(self):
        program = replace(program_for((Transition(
            'finite-retain', 'event:entry', 'event:normal', 'true',
            (effect('create'), effect('retain', holder_id='holder:field')), 'normal', ()),)),
            exit_event_ids=('event:normal',))
        result = solve(program, budget=AnalysisBudget())
        self.assertEqual(1, dict(result.exit_states['event:normal'].held_counts)['family:stream'].upper)
        properties = publish_properties('Finite.unsliced',
            check_invariants(program, result, (), timeout_ms=1000), (), input_identity='fixed-cut')
        held = next(item for item in properties if item['dimension'] == 'held_instances')
        self.assertEqual('all_exits', held['scope'])
        self.assertEqual('unknown', held['status'])
        self.assertIsNone(held['upper_bound'])
        self.assertIn('no_verified_count_invariant', held['unknown_reasons'])

    def test_interval_inclusion_never_merges_incompatible_release_relationships(self):
        base = initial_state(two_instance_program())
        for instance in ('instance:a', 'instance:b'):
            base = apply_effect(base, instance_effect(instance, 'create')).state
        a = apply_effect(base, instance_effect('instance:a', 'release')).state
        b = apply_effect(base, instance_effect('instance:b', 'release')).state
        self.assertFalse(state_subsumes(a, b))
        with self.assertRaises(ValueError):
            widen_state(a, b)
        widened = widen_state(base, replace(base, allocation_counts=(('family:stream', CountInterval(3, 3)),)))
        self.assertTrue(state_subsumes(widened, base))
        self.assertFalse(state_subsumes(base, widened))


@unittest.skipUnless(os.environ.get('DOSWEB_RUN_CODEQL_FIXTURES') == '1', 'requires opt-in real CodeQL extraction')
class RealSourceLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_root = ROOT / 'tests/fixtures/resource_lifecycle_rc1_loops/src/main/java'
        cls.database = fixture_database(str(cls.source_root))
        cls.temp = tempfile.TemporaryDirectory(prefix='dosweb-rc1-loops-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.output = Path(cls.temp.name)
        result = run_query(ROOT / 'codeql/dosweb/ResourceLifecycle/ResourceLifecycleFacts.ql', cls.database, cls.output / 'query')
        payload = json.loads(result.decoded_path.read_text())
        cls.rows = decode_bqrs_json('resource_lifecycle', payload, DecodeSource(cls.database.source_root, result.query_sha256))
        cls.extracted = adapt_codeql_rows(cls.rows, source_root=cls.database.source_root, query_sha256=result.query_sha256)
        cls.extracted = replace(cls.extracted, coverage={**cls.extracted.coverage,
            'source_snapshot_sha256': _java_source_snapshot(cls.database.source_root)[1]})
        cls.units = {unit.unit_id: unit for unit in cls.extracted.units}
        evidence_dir = os.environ.get('DOSWEB_RC1_LOOP_EVIDENCE')
        if evidence_dir:
            destination = Path(evidence_dir)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / 'facts.json').write_text(json.dumps(extracted_to_dict(cls.extracted), indent=2))
            (destination / 'rows.json').write_text(json.dumps(cls.rows, indent=2))

    def result(self, signature):
        unit = self.units['java-callable-v1:fixture.rc1.LoopResources.' + signature]
        result = solve(unit.program, budget=AnalysisBudget())
        self.assertTrue(result.terminated, result.unknown_reasons)
        self.assertFalse(any('iteration_limit:' in item or 'budget' in item for item in result.unknown_reasons))
        return unit, result

    def test_complete_iteration_has_zero_exit_obligation_and_peak_one(self):
        unit, result = self.result('retiredEachIteration(I)V')
        self.assertEqual(1, len(unit.program.families))
        family = unit.program.families[0].family_id
        self.assertTrue(any(effect.kind == 'drop' for edge in unit.program.transitions for effect in edge.effects))
        self.assertTrue(any(dict(state.allocation_counts)[family].upper is None for state in result.exit_states.values()))
        for state in result.exit_states.values():
            self.assertEqual(0, dict(state.obligation_counts)[family].upper)
            self.assertEqual(0, dict(state.held_counts)[family].upper)
            self.assertEqual(1, dict(state.peak_held_counts)[family])

    def test_retained_iteration_does_not_gain_finite_bound(self):
        unit, result = self.result('retainedEachIteration(I)V')
        family = next(item.family_id for item in unit.program.families if item.requires_close)
        self.assertTrue(any(dict(state.held_counts)[family].upper is None for state in result.exit_states.values()))
        self.assertGreater(result.solver_metrics['widening_count'], 0)

    def test_exclusive_close_stays_open_and_semantic_replay_is_stable(self):
        unit, result = self.result('mutuallyExclusiveCloseThenLoop(ZI)V')
        self.assertTrue(any(state.open_obligations for state in result.exit_states.values()))
        self.assertEqual(analysis_result_to_dict(result), analysis_result_to_dict(solve(unit.program, budget=AnalysisBudget())))
        facts_path = self.output / 'facts.json'
        facts_path.write_text(json.dumps(extracted_to_dict(self.extracted)))
        run = self.output / 'run'
        payload = resource_analyze({'facts': facts_path, 'out': run, 'llm': 'off'})
        replay = resource_replay({'run': run})
        self.assertTrue(replay['consistent'], replay)
        evidence = json.loads((run / 'evidence.json').read_text())
        abstract = [item for item in evidence['derivations'] if item.get('abstraction_steps')]
        self.assertTrue(abstract)
        self.assertTrue(all(item['derivation_kind'] == 'abstract_fixpoint' for item in abstract))
        closed = next(item for item in payload['units'] if item['unit_id'].endswith('retiredEachIteration(I)V'))
        obligations = [p for p in closed['properties'] if p['dimension'] == 'close_obligation']
        self.assertTrue(obligations)
        self.assertTrue(all(p['status'] == 'bounded' and p['upper_bound'] == 0 for p in obligations), obligations)
        retained = next(item for item in payload['units'] if item['unit_id'].endswith('retainedEachIteration(I)V'))
        self.assertFalse(any(p['status'] == 'bounded' for p in retained['properties'] if p['dimension'] == 'held_instances'))
        evidence_dir = os.environ.get('DOSWEB_RC1_LOOP_EVIDENCE')
        if evidence_dir:
            destination = Path(evidence_dir)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / 'facts.json').write_text(json.dumps(extracted_to_dict(self.extracted), indent=2))
            (destination / 'results.json').write_text(json.dumps(payload, indent=2))
            (destination / 'replay.json').write_text(json.dumps(replay, indent=2))
            (destination / 'database.json').write_text(json.dumps({'database': str(self.database.path), 'source_root': str(self.source_root)}, indent=2))


if __name__ == '__main__':
    unittest.main()
