from scripts.collect_application_targets import (
    SearchRepo,
    dedupe_repositories,
    filter_new_records,
    infer_build_systems,
    is_candidate_repo,
    rank_repository,
    slug_for_full_name,
)


def repo(**kwargs):
    defaults = {
        "full_name": "example/app",
        "clone_url": "https://github.com/example/app.git",
        "html_url": "https://github.com/example/app",
        "description": "Spring Boot web application",
        "stargazers_count": 1000,
        "forks_count": 100,
        "archived": False,
        "disabled": False,
        "fork": False,
        "size": 10000,
        "pushed_at": "2026-01-01T00:00:00Z",
        "topics": ["spring-boot"],
        "language": "Java",
    }
    defaults.update(kwargs)
    return SearchRepo.from_api(defaults)


def test_slug_for_full_name_is_filesystem_safe():
    assert slug_for_full_name("spring-projects/spring-petclinic") == "spring-projects__spring-petclinic"


def test_infer_build_systems_prefers_declared_files():
    assert infer_build_systems(["pom.xml", "src/main/java/App.java"]) == ["maven"]
    assert infer_build_systems(["build.gradle", "settings.gradle"]) == ["gradle"]
    assert infer_build_systems(["pom.xml", "build.gradle.kts"]) == ["maven", "gradle"]


def test_candidate_filter_rejects_archives_forks_libraries_and_non_web_projects():
    assert is_candidate_repo(repo())
    assert not is_candidate_repo(repo(archived=True))
    assert not is_candidate_repo(repo(fork=True))
    assert not is_candidate_repo(repo(description="Java algorithm library", topics=["algorithm"]))
    assert not is_candidate_repo(repo(description="Android client application", topics=["android"]))


def test_dedupe_keeps_highest_star_duplicate():
    low = repo(stargazers_count=10)
    high = repo(stargazers_count=50)

    deduped = dedupe_repositories([low, high])

    assert deduped == [high]


def test_rank_repository_rewards_simple_default_deploy_and_stars():
    simple = repo(
        full_name="example/simple",
        stargazers_count=5000,
        topics=["spring-boot", "docker"],
        description="Self-hosted Spring Boot web application",
    )
    heavy = repo(
        full_name="example/heavy",
        stargazers_count=5000,
        topics=["kubernetes", "big-data"],
        description="Distributed platform requiring kafka elasticsearch postgres redis",
    )

    assert rank_repository(simple) > rank_repository(heavy)


def test_filter_new_records_skips_existing_full_names_and_ids():
    records = [
        {"id": "example__new", "full_name": "example/new"},
        {"id": "example__old", "full_name": "example/old"},
        {"id": "another__old", "full_name": "another/old"},
    ]

    filtered = filter_new_records(records, existing_full_names={"example/old"}, existing_ids={"another__old"}, limit=2)

    assert filtered == [{"id": "example__new", "full_name": "example/new"}]
