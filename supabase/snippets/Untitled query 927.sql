select table_name
from information_schema.tables
where table_schema = 'public'
order by table_name;