select
  (select count(*) from track_identity) as track_identity,
  (select count(*) from asset_file) as asset_file,
  (select count(*) from asset_link) as asset_link,
  (select count(*) from files) as files;