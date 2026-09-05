#!/usr/bin/env sh
# Bounded Java compilation helper for CodeQL extractor coverage.
set -eu

work_dir=${CODEQL_BOUNDED_JAVAC_WORK_DIR:?CODEQL_BOUNDED_JAVAC_WORK_DIR must be an isolated per-attempt directory}
out_dir=${CODEQL_BOUNDED_JAVAC_OUT:-"$work_dir/classes"}
sources_file=${CODEQL_BOUNDED_JAVAC_SOURCES:-"$work_dir/sources.txt"}
allow_failure=${CODEQL_BOUNDED_JAVAC_ALLOW_COMPILATION_FAILURE:-0}

case "$allow_failure" in
  0|1) ;;
  *) echo "CODEQL_BOUNDED_JAVAC_ALLOW_COMPILATION_FAILURE must be 0 or 1" >&2; exit 2 ;;
esac

cleanup() {
  rm -rf "$work_dir"
}
trap cleanup EXIT HUP INT TERM

rm -rf "$work_dir"
mkdir -p "$out_dir"

if [ "$#" -eq 0 ]; then
  set -- .
fi

find "$@" \
  -type d \( -name .git -o -name .gradle -o -name build -o -name node_modules -o -name out -o -name target \) -prune \
  -o -type f -name '*.java' -print > "$sources_file"

java_file_count=$(wc -l < "$sources_file" | tr -d ' ')
printf 'CODEQL_BOUNDED_JAVAC_JAVA_FILE_COUNT=%s\n' "$java_file_count"
if [ "$java_file_count" -eq 0 ]; then
  echo "No Java sources found in: $*" >&2
  exit 1
fi

# Missing third-party classpaths are normal for archived/plugin-heavy projects.
# Suppression is opt-in from the validated override, never implicit.
if javac -encoding UTF-8 -proc:none -d "$out_dir" @"$sources_file"; then
  exit 0
fi
if [ "$allow_failure" -eq 1 ]; then
  echo "javac failed; continuing because allow_compilation_failure=true" >&2
  exit 0
fi
echo "javac failed; set allow_compilation_failure=true only for bounded extractor coverage" >&2
exit 1
