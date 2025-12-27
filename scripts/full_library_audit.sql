SELECT
    path,
    size_bytes,
    duration,
    bit_rate,
    bit_depth,
    sample_rate,
    channels,

    CASE
        WHEN size_bytes = 0 THEN 'CORRUPT'
        WHEN duration IS NULL THEN 'CORRUPT'
        WHEN bit_rate IS NULL THEN 'CORRUPT'
        WHEN bit_depth IS NULL THEN 'CORRUPT'
        WHEN size_bytes < 1000000 THEN 'CORRUPT'
        WHEN duration < 5 THEN 'CORRUPT'
        WHEN bit_rate < 400000 THEN 'SUSPICIOUS'
        WHEN bit_depth < 16 THEN 'SUSPICIOUS'
        WHEN sample_rate < 44100 THEN 'SUSPICIOUS'
        ELSE 'HEALTHY'
    END AS health_class,

    CASE
        WHEN size_bytes = 0 THEN 'zero-byte'
        WHEN duration IS NULL THEN 'missing duration'
        WHEN bit_rate IS NULL THEN 'missing bitrate'
        WHEN bit_depth IS NULL THEN 'missing bit depth'
        WHEN size_bytes < 1000000 THEN 'tiny file (<1MB)'
        WHEN duration < 5 THEN 'very short (<5 sec)'
        WHEN bit_rate < 400000 THEN 'low bitrate (<400kbps)'
        WHEN bit_depth < 16 THEN 'low bit depth (<16bit)'
        WHEN sample_rate < 44100 THEN 'low samplerate (<44.1k)'
        ELSE 'ok'
    END AS reason

FROM library_files
ORDER BY health_class DESC, reason, path;