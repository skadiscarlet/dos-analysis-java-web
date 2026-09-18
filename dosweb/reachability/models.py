from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal, Mapping, cast

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.errors import AnalyzerError

_MAX_TEXT = 4096


def _bad() -> None: raise AnalyzerError("LLM_RESPONSE_SCHEMA_INVALID", "Reachability artifact violates its strict schema.")
def _str(v: object, *, allow_empty: bool = False) -> str:
    if not isinstance(v, str) or (not allow_empty and not v) or "\x00" in v or len(v.encode()) > _MAX_TEXT: _bad()
    return v

def _id(v: object, prefix: str) -> str:
    v = _str(v)
    if not v.startswith(prefix): _bad()
    return v

@dataclass(frozen=True)
class EntrySecurityFact:
    entry_id: str; kind: Literal["annotation", "filter", "security_filter_chain", "servlet_constraint", "netty_gate", "mqtt_gate", "configuration", "deployment_gate", "dependency_coverage"]; location: str; line: int; value: str; coverage: Literal["complete", "partial", "unsupported"]; fact_id: str = ""
    def __post_init__(self) -> None:
        _id(self.entry_id, "entry:"); _str(self.location); _str(self.value)
        if self.kind not in {"annotation", "filter", "security_filter_chain", "servlet_constraint", "netty_gate", "mqtt_gate", "configuration", "deployment_gate", "dependency_coverage"} or self.coverage not in {"complete", "partial", "unsupported"} or not isinstance(self.line, int) or isinstance(self.line, bool) or self.line < 0: _bad()
        expected=stable_identifier("security", self.semantic_identity())
        if self.fact_id and self.fact_id != expected: _bad()
        object.__setattr__(self,"fact_id",expected)
    def semantic_identity(self)->dict[str,object]: return {"entry_id":self.entry_id,"kind":self.kind,"location":self.location,"line":self.line,"value":self.value,"coverage":self.coverage}
    def to_dict(self)->dict[str,object]: return {"fact_id":self.fact_id,**self.semantic_identity()}
    @classmethod
    def from_dict(cls,r:Mapping[str,object])->"EntrySecurityFact":
        if set(r)!={"fact_id","entry_id","kind","location","line","value","coverage"}: _bad()
        return cls(cast(str,r["entry_id"]),cast(Literal["annotation","filter","security_filter_chain","servlet_constraint","netty_gate","mqtt_gate","configuration","deployment_gate","dependency_coverage"],r["kind"]),cast(str,r["location"]),cast(int,r["line"]),cast(str,r["value"]),cast(Literal["complete","partial","unsupported"],r["coverage"]),cast(str,r["fact_id"]))

@dataclass(frozen=True)
class AuthContract:
    auth_context: Literal["unauthenticated","low_privilege","privileged","unknown"]; evidence_ids: tuple[str,...]; assumptions: tuple[str,...]; confidence: Literal["high","medium","low"]
    def __post_init__(self)->None:
        if self.auth_context not in {"unauthenticated","low_privilege","privileged","unknown"} or self.confidence not in {"high","medium","low"} or len(self.evidence_ids)>32 or len(self.assumptions)>32 or len(set(self.evidence_ids))!=len(self.evidence_ids): _bad()
        for x in self.evidence_ids: _id(x,"security:")
        for x in self.assumptions: _str(x)
    def to_dict(self)->dict[str,object]: return {"auth_context":self.auth_context,"evidence_ids":list(self.evidence_ids),"assumptions":list(self.assumptions),"confidence":self.confidence}
    @classmethod
    def from_dict(cls,r:Mapping[str,object])->"AuthContract":
        if set(r)!={"auth_context","evidence_ids","assumptions","confidence"}: _bad()
        evidence_ids, assumptions = r["evidence_ids"], r["assumptions"]
        if not isinstance(evidence_ids,list) or not isinstance(assumptions,list): _bad()
        return cls(cast(Literal["unauthenticated","low_privilege","privileged","unknown"],r["auth_context"]),tuple(cast(list[str],evidence_ids)),tuple(cast(list[str],assumptions)),cast(Literal["high","medium","low"],r["confidence"]))

@dataclass(frozen=True)
class ReachabilityDecision:
    entry_id:str; auth_contract_id:str; auth_context:Literal["unauthenticated","low_privilege","privileged","unknown"]; deployment_status:Literal["default_enabled","default_disabled","optional","unknown"]; status:Literal["ordinary_attacker_reachable","not_entry_reachable","unknown"]; evidence_ids:tuple[str,...]; reason_codes:tuple[str,...]; decision_id:str=""
    def __post_init__(self)->None:
        _id(self.entry_id,"entry:"); _id(self.auth_contract_id,"auth_contract:")
        if self.auth_context not in {"unauthenticated","low_privilege","privileged","unknown"} or self.deployment_status not in {"default_enabled","default_disabled","optional","unknown"} or self.status not in {"ordinary_attacker_reachable","not_entry_reachable","unknown"} or len(self.evidence_ids)>32 or not self.reason_codes or len(self.reason_codes)>32 or len(set(self.evidence_ids))!=len(self.evidence_ids) or len(set(self.reason_codes))!=len(self.reason_codes): _bad()
        auth_coverage_gap = "REACH_AUTH_COVERAGE_PARTIAL" in self.reason_codes
        if auth_coverage_gap and self.auth_context != "unknown": _bad()
        expected_status = "unknown" if auth_coverage_gap else "ordinary_attacker_reachable" if self.auth_context in {"unauthenticated","low_privilege"} and self.deployment_status == "default_enabled" else "not_entry_reachable" if self.auth_context == "privileged" or self.deployment_status in {"default_disabled","optional"} else "unknown"
        if self.status != expected_status: _bad()
        for x in self.evidence_ids:_id(x,"security:")
        for x in self.reason_codes:_str(x)
        expected=stable_identifier("reachability",self.semantic_identity())
        if self.decision_id and self.decision_id!=expected:_bad()
        object.__setattr__(self,"decision_id",expected)
    def semantic_identity(self)->dict[str,object]:return {"entry_id":self.entry_id,"auth_contract_id":self.auth_contract_id,"auth_context":self.auth_context,"deployment_status":self.deployment_status,"status":self.status,"evidence_ids":list(self.evidence_ids),"reason_codes":list(self.reason_codes)}
    def to_dict(self)->dict[str,object]:return {"decision_id":self.decision_id,**self.semantic_identity()}
    @classmethod
    def from_dict(cls,r:Mapping[str,object])->"ReachabilityDecision":
        if set(r)!={"decision_id","entry_id","auth_contract_id","auth_context","deployment_status","status","evidence_ids","reason_codes"}:_bad()
        return cls(cast(str,r["entry_id"]),cast(str,r["auth_contract_id"]),cast(Literal["unauthenticated","low_privilege","privileged","unknown"],r["auth_context"]),cast(Literal["default_enabled","default_disabled","optional","unknown"],r["deployment_status"]),cast(Literal["ordinary_attacker_reachable","not_entry_reachable","unknown"],r["status"]),tuple(cast(list[str],r["evidence_ids"])),tuple(cast(list[str],r["reason_codes"])),cast(str,r["decision_id"]))

@dataclass(frozen=True)
class LlmAuditRecord:
    contract_kind:Literal["growth","auth"]; request_id:str; normalized_prompt:str; response_schema:dict[str,object]; raw_response:str; parsed_response:dict[str,object]; settings:dict[str,object]; attestation:dict[str,object]; cache_hit:bool; audit_id:str=""
    def __post_init__(self)->None:
        if self.contract_kind not in {"growth","auth"} or not isinstance(self.cache_hit,bool):_bad()
        _str(self.request_id, allow_empty=True)
        if (not isinstance(self.normalized_prompt, str) or not isinstance(self.raw_response, str)
                or "\x00" in self.normalized_prompt or "\x00" in self.raw_response
                or len(self.normalized_prompt.encode()) > 131072 or len(self.raw_response.encode()) > 131072
                or not isinstance(self.response_schema,dict) or not isinstance(self.parsed_response,dict)
                or not isinstance(self.settings,dict) or not isinstance(self.attestation,dict)):_bad()
        # Audit artifacts must never become a second credential store.
        structured = {"parsed": self.parsed_response, "settings": self.settings, "attestation": self.attestation}
        def has_secret_key(value: object) -> bool:
            if isinstance(value, Mapping):
                return any(str(key).lower() in {"authorization", "api_key", "deepseek_api_key"} or has_secret_key(child) for key, child in value.items())
            if isinstance(value, (list, tuple)):
                return any(has_secret_key(child) for child in value)
            return False
        # Authorization headers are rejected structurally above; semantic text
        # may legitimately discuss bearer authentication. Only key-shaped
        # credential material is rejected in free-form prompt/response text.
        secret_pattern = re.compile(r"(?i)(?:(?<![a-z0-9_-])sk-[a-z0-9_-]{8,}|\bbearer\s+[\"']?[a-z0-9._~-]{8,})")
        if has_secret_key(structured) or secret_pattern.search(self.normalized_prompt) or secret_pattern.search(self.raw_response): _bad()
        raw=json.dumps({"contract_kind":self.contract_kind,"request_id":self.request_id,"normalized_prompt":self.normalized_prompt,"response_schema":self.response_schema,"raw_response":self.raw_response,"parsed_response":self.parsed_response,"settings":self.settings,"attestation":self.attestation,"cache_hit":self.cache_hit},sort_keys=True,separators=(",",":"),ensure_ascii=False)
        expected=stable_identifier("llm_audit",{"payload_sha256":hashlib.sha256(raw.encode()).hexdigest()})
        if self.audit_id and self.audit_id!=expected:_bad()
        object.__setattr__(self,"audit_id",expected)
    def to_dict(self)->dict[str,object]:return {"audit_id":self.audit_id,"contract_kind":self.contract_kind,"request_id":self.request_id,"normalized_prompt":self.normalized_prompt,"response_schema":self.response_schema,"raw_response":self.raw_response,"parsed_response":self.parsed_response,"settings":self.settings,"attestation":self.attestation,"cache_hit":self.cache_hit}
