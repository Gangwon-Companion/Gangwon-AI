param(
    [string]$BePath = "..\Gangwon-Companion",
    [int[]]$RowsPerDomain = @(1000, 5000),
    [int]$Runs = 3,
    [int]$WarmUpRequests = 100,
    [int]$MeasuredRequests = 300,
    [string]$DatabaseContainer = "postgres_gangwon",
    [string]$Database = "gangwon",
    [string]$DatabaseUser = "gangwon_user",
    [string]$DatabasePassword = $env:PERFORMANCE_DB_PASSWORD
)

if ([string]::IsNullOrWhiteSpace($DatabasePassword)) {
    throw "Set PERFORMANCE_DB_PASSWORD or pass -DatabasePassword."
}

$resolvedBePath = (Resolve-Path -LiteralPath $BePath).Path
$repositoryRoot = (Resolve-Path -LiteralPath .).Path
$resultDirectory = Join-Path $repositoryRoot "performance\results"
$planDirectory = Join-Path $repositoryRoot "performance\plans"
New-Item -ItemType Directory -Force -Path $resultDirectory, $planDirectory | Out-Null
$resourceOutput = Join-Path $resultDirectory "docker-resources-before.txt"
docker stats --no-stream $DatabaseContainer | Set-Content -LiteralPath $resourceOutput -Encoding UTF8

docker exec $DatabaseContainer psql -U $DatabaseUser -d $Database `
    -v ON_ERROR_STOP=1 -c 'CREATE SCHEMA IF NOT EXISTS search_benchmark'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

foreach ($rowCount in $RowsPerDomain) {
    foreach ($run in 1..$Runs) {
        $output = Join-Path $resultDirectory "rdb-postgresql-$rowCount-run$run.json"
        $env:PERFORMANCE_OUTPUT = $output
        $env:PERFORMANCE_JDBC_URL = "jdbc:postgresql://localhost:5432/$Database`?currentSchema=search_benchmark"
        $env:PERFORMANCE_DB_USER = $DatabaseUser
        $env:PERFORMANCE_DB_PASSWORD = $DatabasePassword
        $env:PERFORMANCE_ROWS_PER_DOMAIN = $rowCount
        $env:PERFORMANCE_WARM_UP_REQUESTS = $WarmUpRequests
        $env:PERFORMANCE_MEASURED_REQUESTS = $MeasuredRequests
        & (Join-Path $resolvedBePath "gradlew.bat") -p $resolvedBePath test --rerun-tasks `
            --tests com.gangwon.companion.domain.search.service.RdbSearchBenchmarkTest
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    $planOutput = Join-Path $planDirectory "rdb-postgresql-$rowCount-explain.txt"
    $explainSource = Join-Path $repositoryRoot "performance\scenarios\rdb-explain.sql"
    docker cp $explainSource "${DatabaseContainer}:/tmp/rdb-explain.sql"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    docker exec $DatabaseContainer psql -U $DatabaseUser -d $Database -X `
        -f /tmp/rdb-explain.sql | `
        Set-Content -LiteralPath $planOutput -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

docker stats --no-stream $DatabaseContainer | `
    Set-Content -LiteralPath (Join-Path $resultDirectory "docker-resources-after.txt") -Encoding UTF8

Remove-Item Env:PERFORMANCE_OUTPUT, Env:PERFORMANCE_JDBC_URL, Env:PERFORMANCE_DB_USER, `
    Env:PERFORMANCE_DB_PASSWORD, Env:PERFORMANCE_ROWS_PER_DOMAIN, `
    Env:PERFORMANCE_WARM_UP_REQUESTS, Env:PERFORMANCE_MEASURED_REQUESTS -ErrorAction SilentlyContinue
