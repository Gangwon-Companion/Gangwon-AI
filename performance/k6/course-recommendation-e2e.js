import http from 'k6/http';
import { check, sleep } from 'k6';

const baseUrl = __ENV.BASE_URL || 'http://host.docker.internal:8000';
const runId = __ENV.TEST_RUN_ID || 'course-e2e';
const vus = Number(__ENV.VUS || 10);
const duration = __ENV.DURATION || '30s';

export const options = {
  vus,
  duration,
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<2000'],
    checks: ['rate>0.99'],
  },
  tags: { test_run_id: runId, test_type: 'course-recommendation-e2e' },
};

const requests = [
  { message: 'Gangneung day trip', region: 'GANGNEUNG', travel_days: 1, nights: 0,
    pet_allowed: false, wheelchair_accessible: false, preferences: [] },
  { message: 'Sokcho two day trip', region: 'SOKCHO', travel_days: 2, nights: 1,
    pet_allowed: false, wheelchair_accessible: false, preferences: [] },
  { message: 'Chuncheon day trip', region: 'CHUNCHEON', travel_days: 1, nights: 0,
    pet_allowed: false, wheelchair_accessible: false, preferences: [] },
];

export default function () {
  const payload = requests[Math.floor(Math.random() * requests.length)];
  const response = http.post(`${baseUrl}/internal/travel/plan`, JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
    tags: { endpoint: 'travel-plan' },
    timeout: '30s',
  });

  check(response, {
    'HTTP 200': (r) => r.status === 200,
    'course is completed': (r) => {
      try {
        const body = r.json();
        return body.status === 'completed'
          && body.itinerary_status === 'READY'
          && body.hard_validation?.status === 'VALID'
          && body.quality_validation?.status === 'PASS'
          && body.final_response?.response_status === 'READY';
      } catch (_) {
        return false;
      }
    },
  });
  sleep(0.1);
}

function value(data, metric, key) {
  return data.metrics[metric]?.values[key] ?? null;
}

export function handleSummary(data) {
  const result = {
    runId,
    generatedAt: new Date().toISOString(),
    p50Ms: value(data, 'http_req_duration', 'med'),
    p95Ms: value(data, 'http_req_duration', 'p(95)'),
    p99Ms: value(data, 'http_req_duration', 'p(99)'),
    requests: value(data, 'http_reqs', 'count'),
    throughputRps: value(data, 'http_reqs', 'rate'),
    errorRate: value(data, 'http_req_failed', 'rate'),
    checkRate: value(data, 'checks', 'rate'),
    durationMs: data.state.testRunDurationMs,
  };
  return {
    stdout: JSON.stringify(result),
    [`/results/${runId}.json`]: JSON.stringify(result, null, 2),
  };
}
