param(
    [string]$BePath = "..\Gangwon-Companion",
    [string]$BaseUrl = "http://localhost:8080",
    [string]$ScenarioPath = "tests\fixtures\search_scenarios.json",
    [string]$OutputPath = "performance\results\live-rdb-vs-elasticsearch.json",
    [int]$WarmUpRequests = 5,
    [int]$MeasuredRequests = 30,
    [string]$ReindexKey = "",
    [switch]$SkipReindex
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path -LiteralPath .).Path
$resolvedBePath = (Resolve-Path -LiteralPath $BePath).Path
$resolvedScenarioPath = (Resolve-Path -LiteralPath (Join-Path $repositoryRoot $ScenarioPath)).Path
$resolvedOutputPath = Join-Path $repositoryRoot $OutputPath
$outputDirectory = Split-Path -Parent $resolvedOutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

function Invoke-Docker([string[]]$Arguments) {
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $output = & docker @Arguments 2>$null }
    finally { $ErrorActionPreference = $previousErrorAction }
    if ($LASTEXITCODE -ne 0) { throw "docker $($Arguments -join ' ') failed:`n$output" }
    return $output
}

function Get-SpringEnvironment([string]$Name) {
    $line = Invoke-Docker @("inspect", "spring_gangwon", "--format", "{{range .Config.Env}}{{println .}}{{end}}") |
        Where-Object { $_ -like "$Name=*" } | Select-Object -First 1
    if ($null -eq $line) { return "" }
    return $line.Substring($Name.Length + 1)
}

function Set-SearchEngine([string]$Engine) {
    $currentEngine = Get-SpringEnvironment "SEARCH_ENGINE"
    $currentReindexKey = Get-SpringEnvironment "ELASTICSEARCH_REINDEX_KEY"
    if ($currentEngine -eq $Engine -and
            ([string]::IsNullOrWhiteSpace($ReindexKey) -or $currentReindexKey -eq $ReindexKey)) {
        Write-Host "Spring already uses SEARCH_ENGINE=$Engine."
        return
    }
    Write-Host "Starting Spring with SEARCH_ENGINE=$Engine ..."
    $previous = $env:SEARCH_ENGINE
    $previousReindexKey = $env:ELASTICSEARCH_REINDEX_KEY
    try {
        $env:SEARCH_ENGINE = $Engine
        if (-not [string]::IsNullOrWhiteSpace($ReindexKey)) {
            $env:ELASTICSEARCH_REINDEX_KEY = $ReindexKey
        }
        Push-Location $resolvedBePath
        try { Invoke-Docker @("compose", "up", "-d", "--no-deps", "--force-recreate", "spring") | Out-Host }
        finally { Pop-Location }
    } finally {
        if ($null -eq $previous) { Remove-Item Env:SEARCH_ENGINE -ErrorAction SilentlyContinue }
        else { $env:SEARCH_ENGINE = $previous }
        if ($null -eq $previousReindexKey) { Remove-Item Env:ELASTICSEARCH_REINDEX_KEY -ErrorAction SilentlyContinue }
        else { $env:ELASTICSEARCH_REINDEX_KEY = $previousReindexKey }
    }
}

function Wait-ForSearch([object]$Request) {
    $body = $Request | ConvertTo-Json -Depth 10 -Compress
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        try {
            Invoke-RestMethod -Method Post -Uri "$BaseUrl/internal/search/places" `
                -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 5 | Out-Null
            return
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "Spring search API did not become ready at $BaseUrl"
}

function Get-Percentile([double[]]$Values, [double]$Percentile) {
    if ($Values.Count -eq 0) { return $null }
    $sorted = @($Values | Sort-Object)
    $index = [Math]::Ceiling(($Percentile / 100.0) * $sorted.Count) - 1
    return [Math]::Round($sorted[[Math]::Max(0, $index)], 3)
}

function Measure-Engine([string]$Engine, [object[]]$Scenarios) {
    Set-SearchEngine $Engine
    Wait-ForSearch ($Scenarios[0].request)
    $measurements = @()

    foreach ($scenario in $Scenarios) {
        $body = $scenario.request | ConvertTo-Json -Depth 10 -Compress
        for ($i = 0; $i -lt $WarmUpRequests; $i++) {
            Invoke-RestMethod -Method Post -Uri "$BaseUrl/internal/search/places" `
                -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 10 | Out-Null
        }

        $latencies = [System.Collections.Generic.List[double]]::new()
        $errors = 0
        $resultIds = @()
        $total = [System.Diagnostics.Stopwatch]::StartNew()
        for ($i = 0; $i -lt $MeasuredRequests; $i++) {
            $watch = [System.Diagnostics.Stopwatch]::StartNew()
            try {
                $response = Invoke-RestMethod -Method Post -Uri "$BaseUrl/internal/search/places" `
                    -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 10
                if ($i -eq 0) {
                    $resultIds = @($response.results | ForEach-Object {
                        if ($null -ne $_.place_id) { $_.place_id } else { $_.placeId }
                    })
                }
            } catch {
                $errors++
            } finally {
                $watch.Stop()
                $latencies.Add($watch.Elapsed.TotalMilliseconds)
            }
        }
        $total.Stop()

        $measurements += [ordered]@{
            scenario_id = $scenario.id
            p50_ms = Get-Percentile $latencies.ToArray() 50
            p95_ms = Get-Percentile $latencies.ToArray() 95
            p99_ms = Get-Percentile $latencies.ToArray() 99
            throughput_rps = [Math]::Round($MeasuredRequests / $total.Elapsed.TotalSeconds, 2)
            error_rate = [Math]::Round($errors / [double]$MeasuredRequests, 4)
            result_count = $resultIds.Count
            result_ids = $resultIds
        }
        Write-Host "[$Engine] $($scenario.id): p95=$($measurements[-1].p95_ms)ms, results=$($resultIds.Count)"
    }
    return $measurements
}

function Compare-Results([object[]]$Rdb, [object[]]$Elasticsearch) {
    $comparisons = @()
    foreach ($rdbResult in $Rdb) {
        $esResult = $Elasticsearch | Where-Object scenario_id -eq $rdbResult.scenario_id | Select-Object -First 1
        $rdbIds = @($rdbResult.result_ids)
        $esIds = @($esResult.result_ids)
        $intersection = @($rdbIds | Where-Object { $esIds -contains $_ } | Select-Object -Unique).Count
        $union = @($rdbIds + $esIds | Select-Object -Unique).Count
        $samePositions = 0
        for ($i = 0; $i -lt [Math]::Min($rdbIds.Count, $esIds.Count); $i++) {
            if ($rdbIds[$i] -eq $esIds[$i]) { $samePositions++ }
        }
        $comparisons += [ordered]@{
            scenario_id = $rdbResult.scenario_id
            overlap_count = $intersection
            jaccard = if ($union -eq 0) { 1.0 } else { [Math]::Round($intersection / [double]$union, 4) }
            same_rank_positions = $samePositions
            exact_order_match = (($rdbIds -join '|') -eq ($esIds -join '|'))
            rdb_p95_ms = $rdbResult.p95_ms
            elasticsearch_p95_ms = $esResult.p95_ms
        }
    }
    return $comparisons
}

$parsedScenarios = Get-Content -LiteralPath $resolvedScenarioPath -Raw -Encoding UTF8 | ConvertFrom-Json
$scenarios = [object[]]$parsedScenarios
if ($scenarios.Count -eq 0) { throw "No scenarios found in $resolvedScenarioPath" }
$originalEngine = Get-SpringEnvironment "SEARCH_ENGINE"
if ([string]::IsNullOrWhiteSpace($originalEngine)) { $originalEngine = "rdb" }
if ([string]::IsNullOrWhiteSpace($ReindexKey)) { $ReindexKey = Get-SpringEnvironment "ELASTICSEARCH_REINDEX_KEY" }

try {
    Set-SearchEngine "rdb"
    Wait-ForSearch ($scenarios[0].request)

    if (-not $SkipReindex) {
        if ([string]::IsNullOrWhiteSpace($ReindexKey)) {
            throw "ELASTICSEARCH_REINDEX_KEY is empty. Set it in Gangwon-Companion/.env and recreate Spring, or pass -ReindexKey."
        }
        Write-Host "Reindexing Elasticsearch from the live RDB ..."
        $reindexReport = Invoke-RestMethod -Method Post -Uri "$BaseUrl/internal/search/index/rebuild" `
            -Headers @{ "X-Search-Reindex-Key" = $ReindexKey } -TimeoutSec 300
        if (-not $reindexReport.aliasSwitched -or $reindexReport.sourceCount -ne $reindexReport.indexedCount) {
            throw "Reindex failed: source=$($reindexReport.sourceCount), indexed=$($reindexReport.indexedCount), aliasSwitched=$($reindexReport.aliasSwitched)"
        }
    }

    $rdb = @(Measure-Engine "rdb" $scenarios)
    $elasticsearch = @(Measure-Engine "elasticsearch" $scenarios)
    $comparisons = @(Compare-Results $rdb $elasticsearch)
    $report = [ordered]@{
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        dataset = "live PostgreSQL public schema; Elasticsearch rebuilt from the same aggregates"
        warm_up_requests_per_scenario = $WarmUpRequests
        measured_requests_per_scenario = $MeasuredRequests
        rdb = $rdb
        elasticsearch = $elasticsearch
        comparisons = $comparisons
    }
    $report | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $resolvedOutputPath -Encoding UTF8
    Write-Host "Report written to $resolvedOutputPath"
} finally {
    Write-Host "Restoring SEARCH_ENGINE=$originalEngine ..."
    Set-SearchEngine $originalEngine
    Wait-ForSearch ($scenarios[0].request)
}
