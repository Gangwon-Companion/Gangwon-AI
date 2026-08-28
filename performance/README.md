# RDB 검색 성능 측정

고정 query set은 `scenarios/rdb-search-scenarios.json`, PostgreSQL 실행 스크립트는
`scripts/run-rdb-postgresql-benchmark.ps1`에 있다.

Gangwon-AI 저장소 루트에서 다음과 같이 실행한다.

```powershell
.\performance\scripts\run-rdb-postgresql-benchmark.ps1
```

기본 실행은 운영 데이터와 분리된 `search_benchmark` 스키마에 도메인당 1,000행과
5,000행을 생성한다. 각 규모를 독립적으로 3회 실행하며, 매번 100회 warm-up 후
시나리오와 동시성(1, 10, 50)별 300회를 측정한다. 원본 JSON은
`performance/results/`, PostgreSQL의
`EXPLAIN (ANALYZE, BUFFERS)` 결과는 `performance/plans/`에 저장한다.
측정 당시 Gradle 테스트 JVM 힙은 512MB였으며 결과의 `max_heap_bytes`에 실제값을
기록한다. 이후 엔진 비교도 같은 힙 조건을 사용한다.

JSON에는 애플리케이션 p50/p95/p99, 처리량, 오류율, 평균 반환 건수와 Hibernate의
쿼리·prepared statement 수가 포함된다. DB 실행시간은 `EXPLAIN ANALYZE` 결과로
분리한다. Docker 자원 사용량과 Hikari pool 지표, 검색 품질 정답 세트는 별도
결과로 보완해야 한다.

## 실제 수집 데이터로 RDB와 Elasticsearch 비교

합성 benchmark 스키마가 아니라 현재 PostgreSQL `public` 스키마의 수집 데이터를
비교하려면 아래 스크립트를 사용한다. 실행 전에 `Gangwon-Companion/.env`의
`ELASTICSEARCH_REINDEX_KEY`에 비어 있지 않은 로컬 키를 설정하고 Spring 컨테이너를
다시 생성해야 한다.

```powershell
.\performance\scripts\run-live-search-comparison.ps1
```

스크립트는 다음을 자동으로 수행한다.

1. Spring을 RDB 엔진으로 실행한다.
2. 실제 RDB aggregate 전체를 새 Elasticsearch 인덱스로 재색인하고 문서 수를 검증한다.
3. `tests/fixtures/search_scenarios.json`의 동일 요청을 RDB와 Elasticsearch에 각각 실행한다.
4. 엔진별 p50/p95/p99, 처리량, 오류율과 결과 ID를 기록한다.
5. 시나리오별 결과 집합 Jaccard, 같은 순위 위치 수, 완전 순서 일치 여부를 계산한다.
6. 종료 또는 오류 시 Spring을 실행 전 검색 엔진으로 복원한다.

기본 결과는 `performance/results/live-rdb-vs-elasticsearch.json`에 저장된다. 빠른
smoke test는 다음처럼 실행할 수 있다.

```powershell
.\performance\scripts\run-live-search-comparison.ps1 -WarmUpRequests 1 -MeasuredRequests 3
```

이미 동일 데이터로 alias를 재색인한 직후라면 `-SkipReindex`를 사용할 수 있다.
