#!/usr/bin/env python3
"""Collect GitHub Java Web application targets for application-level DoS hunting."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "intel" / "applications" / "java_web_application_targets.json"
APPLICATION_SOURCE_ROOT = "frameworks/applications"
APPLICATION_DB_ROOT = "databases/applications"

DEFAULT_SEARCH_QUERIES = [
    "language:Java topic:self-hosted stars:>200 pushed:>2023-01-01",
    "language:Java topic:cms stars:>200 pushed:>2023-01-01",
    "language:Java topic:admin stars:>200 pushed:>2023-01-01",
    "language:Java topic:workflow stars:>200 pushed:>2023-01-01",
    "language:Java topic:identity-management stars:>200 pushed:>2023-01-01",
    "language:Java topic:monitoring stars:>200 pushed:>2023-01-01",
    "language:Java topic:iot stars:>200 pushed:>2023-01-01",
    "language:Java topic:ecommerce stars:>200 pushed:>2023-01-01",
    "language:Java topic:low-code stars:>100 pushed:>2023-01-01",
    "language:Java spring boot admin platform stars:>500 pushed:>2023-01-01",
    "language:Java spring boot management system stars:>500 pushed:>2023-01-01",
    "language:Java docker web server stars:>300 pushed:>2023-01-01 -topic:tutorial",
]

WEB_POSITIVE_TERMS = {
    "admin",
    "api",
    "cms",
    "dashboard",
    "ecommerce",
    "gateway",
    "http",
    "identity",
    "iot",
    "job",
    "low",
    "low-code",
    "mall",
    "management",
    "monitoring",
    "orchestration",
    "pdf",
    "platform",
    "rest",
    "server",
    "servlet",
    "shop",
    "sso",
    "web",
    "webapp",
    "workflow",
}

NEGATIVE_TERMS = {
    "algorithm",
    "android",
    "awesome",
    "benchmark",
    "book",
    "client",
    "course",
    "demo",
    "example",
    "examples",
    "framework",
    "interview",
    "leetcode",
    "learning",
    "library",
    "libs",
    "plugin",
    "roadmap",
    "sample",
    "samples",
    "sdk",
    "seed",
    "starter",
    "template",
    "tutorial",
}

EXCLUDED_REPOSITORIES = {
    "alibaba/spring-ai-alibaba",
    "apache/camel",
    "baomidou/dynamic-datasource",
    "dyc87112/springboot-learning",
    "dyc87112/springcloud-learning",
    "derekyr/mini-spring",
    "derekyrc/mini-spring",
    "ityouknow/spring-boot-examples",
    "lihengming/spring-boot-api-project-seed",
    "s4kibs4mi/java-developer-roadmap",
    "spring-cloud/spring-cloud-gateway",
    "spring-cloud/spring-cloud-netflix",
    "spring-projects/spring-boot",
    "springfox/springfox",
    "wuyouzhuguli/springall",
    "xuchengsheng/spring-reading",
    "yudaocode/springboot-labs",
}

HEAVY_SERVICE_TERMS = {
    "cassandra",
    "clickhouse",
    "elasticsearch",
    "flink",
    "hadoop",
    "hbase",
    "kafka",
    "kubernetes",
    "minio",
    "mongo",
    "mongodb",
    "mysql",
    "postgres",
    "postgresql",
    "pulsar",
    "rabbitmq",
    "redis",
    "spark",
    "zookeeper",
}

SIMPLE_DEPLOY_TERMS = {
    "docker",
    "dockerfile",
    "embedded",
    "h2",
    "jar",
    "quickstart",
    "standalone",
}


@dataclass(frozen=True)
class SearchRepo:
    full_name: str
    clone_url: str
    html_url: str
    description: str
    stargazers_count: int
    forks_count: int
    archived: bool
    disabled: bool
    fork: bool
    size: int
    pushed_at: str
    topics: tuple[str, ...]
    language: str | None

    @classmethod
    def from_api(cls, payload: dict) -> "SearchRepo":
        return cls(
            full_name=payload["full_name"],
            clone_url=payload["clone_url"],
            html_url=payload["html_url"],
            description=payload.get("description") or "",
            stargazers_count=int(payload.get("stargazers_count") or 0),
            forks_count=int(payload.get("forks_count") or 0),
            archived=bool(payload.get("archived")),
            disabled=bool(payload.get("disabled")),
            fork=bool(payload.get("fork")),
            size=int(payload.get("size") or 0),
            pushed_at=payload.get("pushed_at") or "",
            topics=tuple(payload.get("topics") or ()),
            language=payload.get("language"),
        )


def slug_for_full_name(full_name: str) -> str:
    return full_name.lower().replace("/", "__").replace(".", "-")


def infer_build_systems(paths: Iterable[str]) -> list[str]:
    names = {Path(path).name.lower() for path in paths}
    systems: list[str] = []
    if "pom.xml" in names or "mvnw" in names:
        systems.append("maven")
    if {"build.gradle", "build.gradle.kts", "gradlew"} & names:
        systems.append("gradle")
    return systems


def normalized_terms(repo: SearchRepo) -> set[str]:
    text = " ".join([repo.description, repo.full_name, *repo.topics]).lower()
    tokens = set()
    for raw in text.replace("/", " ").replace("-", " ").replace("_", " ").split():
        tokens.add(raw.strip(".,:;()[]{}"))
    tokens.update(topic.lower() for topic in repo.topics)
    return {token for token in tokens if token}


def noise_terms(repo: SearchRepo) -> set[str]:
    repo_name = repo.full_name.rsplit("/", 1)[-1]
    text = " ".join([repo.description, repo_name, *repo.topics]).lower()
    tokens = set()
    for raw in text.replace("-", " ").replace("_", " ").split():
        tokens.add(raw.strip(".,:;()[]{}"))
    tokens.update(topic.lower() for topic in repo.topics)
    return {token for token in tokens if token}


def is_candidate_repo(repo: SearchRepo) -> bool:
    if repo.full_name.lower() in EXCLUDED_REPOSITORIES:
        return False
    if repo.archived or repo.disabled or repo.fork:
        return False
    if (repo.language or "").lower() != "java":
        return False
    terms = normalized_terms(repo)
    if noise_terms(repo) & NEGATIVE_TERMS:
        return False
    if not (terms & WEB_POSITIVE_TERMS):
        return False
    return True


def deployment_complexity(repo: SearchRepo, top_level_paths: Iterable[str] = ()) -> tuple[str, list[str]]:
    terms = normalized_terms(repo)
    names = {Path(path).name.lower() for path in top_level_paths}
    services = sorted(term for term in terms if term in HEAVY_SERVICE_TERMS)
    simple_hint = bool((terms & SIMPLE_DEPLOY_TERMS) or {"dockerfile", "compose.yml", "docker-compose.yml"} & names)

    if len(services) <= 1 and simple_hint:
        return "simple-or-one-extra-service", services
    if len(services) <= 1:
        return "likely-simple", services
    return "multi-service-uncertain", services


def rank_repository(repo: SearchRepo) -> float:
    terms = normalized_terms(repo)
    score = math.log10(max(repo.stargazers_count, 1)) * 100.0
    score += math.log10(max(repo.forks_count, 1)) * 20.0
    score += 40.0 * len(terms & {"spring-boot", "self-hosted", "cms", "admin", "identity", "workflow"})
    score += 25.0 * len(terms & SIMPLE_DEPLOY_TERMS)
    score -= 28.0 * len(terms & HEAVY_SERVICE_TERMS)
    score -= min(repo.size / 100_000.0, 80.0)
    return score


def dedupe_repositories(repositories: Iterable[SearchRepo]) -> list[SearchRepo]:
    by_name: dict[str, SearchRepo] = {}
    for repo in repositories:
        current = by_name.get(repo.full_name)
        if current is None or repo.stargazers_count > current.stargazers_count:
            by_name[repo.full_name] = repo
    return sorted(by_name.values(), key=rank_repository, reverse=True)


def github_request(url: str, token: str | None = None) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "dos-analysis-web-application-target-collector",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def search_repositories(query: str, per_page: int, token: str | None = None) -> list[SearchRepo]:
    encoded = urllib.parse.urlencode(
        {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": str(per_page),
        }
    )
    payload = github_request(f"https://api.github.com/search/repositories?{encoded}", token)
    return [SearchRepo.from_api(item) for item in payload.get("items", [])]


def fetch_top_level_paths(repo: SearchRepo, token: str | None = None) -> list[str]:
    owner_repo = urllib.parse.quote(repo.full_name, safe="/")
    url = f"https://api.github.com/repos/{owner_repo}/contents"
    payload = github_request(url, token)
    if not isinstance(payload, list):
        return []
    return [item.get("name", "") for item in payload if item.get("name")]


def target_record(repo: SearchRepo, top_level_paths: list[str]) -> dict:
    target_id = slug_for_full_name(repo.full_name)
    build_systems = infer_build_systems(top_level_paths) or ["auto"]
    complexity, services = deployment_complexity(repo, top_level_paths)
    return {
        "id": target_id,
        "full_name": repo.full_name,
        "html_url": repo.html_url,
        "clone_url": repo.clone_url,
        "stars": repo.stargazers_count,
        "forks": repo.forks_count,
        "pushed_at": repo.pushed_at,
        "language": repo.language,
        "description": repo.description,
        "topics": list(repo.topics),
        "deployment_complexity": complexity,
        "extra_services_guess": services,
        "top_level_build_files": [path for path in top_level_paths if path in {"pom.xml", "mvnw", "build.gradle", "build.gradle.kts", "gradlew"}],
        "build_systems": build_systems,
        "source_dir": f"{APPLICATION_SOURCE_ROOT}/{target_id}",
        "database_dir": f"{APPLICATION_DB_ROOT}/{target_id}-db",
        "build_command": None,
        "selection_score": round(rank_repository(repo), 3),
    }


def collect_targets(limit: int, per_query: int, token: str | None, sleep_seconds: float) -> list[dict]:
    repositories: list[SearchRepo] = []
    for query in DEFAULT_SEARCH_QUERIES:
        print(f"[collect] GitHub search: {query}", file=sys.stderr)
        try:
            repositories.extend(search_repositories(query, per_query, token))
        except Exception as exc:  # noqa: BLE001 - CLI should keep partial results visible.
            print(f"[collect] search failed for query={query!r}: {exc}", file=sys.stderr)
        time.sleep(sleep_seconds)

    candidates = [repo for repo in dedupe_repositories(repositories) if is_candidate_repo(repo)]
    records: list[dict] = []
    for repo in candidates[:limit]:
        top_level_paths: list[str] = []
        try:
            top_level_paths = fetch_top_level_paths(repo, token)
        except Exception as exc:  # noqa: BLE001
            print(f"[collect] contents fetch failed for {repo.full_name}: {exc}", file=sys.stderr)
        records.append(target_record(repo, top_level_paths))
        time.sleep(sleep_seconds)
    return records


def filter_new_records(
    records: Iterable[dict],
    existing_full_names: set[str] | None = None,
    existing_ids: set[str] | None = None,
    limit: int | None = None,
) -> list[dict]:
    existing_full_names = {name.lower() for name in (existing_full_names or set())}
    existing_ids = set(existing_ids or set())
    selected: list[dict] = []
    for record in records:
        if record["full_name"].lower() in existing_full_names or record["id"] in existing_ids:
            continue
        selected.append(record)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def load_existing_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("targets") or [])


def write_manifest(records: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "criteria": {
            "source": "GitHub Search API",
            "limit": len(records),
            "priority": [
                "real Java repositories with HTTP/web application signals",
                "higher stars and forks",
                "simple default deployment or at most one obvious extra service",
                "Maven/Gradle build-mode CodeQL extraction feasibility",
            ],
            "excluded": [
                "archived, disabled, forked repositories",
                "libraries, SDKs, templates, tutorials, Android clients, algorithm repos",
                "repositories without Java language and HTTP/web signals",
            ],
        },
        "targets": records,
    }
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--per-query", type=int, default=40)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--exclude-manifest", type=Path, action="append", default=[])
    parser.add_argument("--append", action="store_true", help="Append newly collected targets to --output.")
    parser.add_argument("--sleep", type=float, default=1.0, help="Delay between GitHub API calls.")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    records = collect_targets(args.limit + 100 if args.exclude_manifest or args.append else args.limit, args.per_query, token, args.sleep)
    existing_records: list[dict] = []
    for manifest in args.exclude_manifest:
        existing_records.extend(load_existing_records(manifest))
    if args.append:
        existing_records.extend(load_existing_records(args.output))
    if existing_records:
        records = filter_new_records(
            records,
            existing_full_names={record["full_name"] for record in existing_records},
            existing_ids={record["id"] for record in existing_records},
            limit=args.limit,
        )
    if len(records) < args.limit:
        print(f"[collect] warning: selected only {len(records)} targets for requested limit {args.limit}", file=sys.stderr)
    if args.append:
        records = load_existing_records(args.output) + records
    write_manifest(records, args.output)
    print(f"[collect] wrote {len(records)} targets to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
