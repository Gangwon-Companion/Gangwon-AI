SET search_path TO search_benchmark;
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM restaurants WHERE region = '강릉' ORDER BY id FETCH FIRST 100 ROWS ONLY;
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM restaurants
WHERE region = '강릉' AND (lower(name) LIKE '%한식%' OR lower(menu_type) LIKE '%한식%' OR lower(address) LIKE '%한식%')
ORDER BY id FETCH FIRST 100 ROWS ONLY;
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM restaurants
WHERE region = '강릉' AND latitude BETWEEN 37.731981 AND 37.768018 AND longitude BETWEEN 128.877407 AND 128.922592
ORDER BY id FETCH FIRST 100 ROWS ONLY;
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM lodgings
WHERE region = '강릉' AND (lower(name) LIKE '%존재하지않는희소검색어%' OR lower(description) LIKE '%존재하지않는희소검색어%' OR lower(address) LIKE '%존재하지않는희소검색어%')
ORDER BY id FETCH FIRST 100 ROWS ONLY;
