import logging
import sqlite3
from typing import Iterator, List

from dedupe.storage.models import AudioFile, DuplicateGroup
from dedupe.storage.queries import _row_to_audiofile

logger = logging.getLogger("dedupe")

def find_exact_duplicates(conn: sqlite3.Connection) -> Iterator[DuplicateGroup]:
    """
    Yields groups of files that share the exact same checksum.
    Only groups with >1 file are returned.
    """
    # 1. Find checksums that appear more than once
    query_hashes = """
    SELECT checksum, COUNT(*) as cnt
    FROM files
    WHERE checksum IS NOT NULL AND checksum != 'NOT_SCANNED'
    GROUP BY checksum
    HAVING cnt > 1
    """
    
    try:
        cursor = conn.execute(query_hashes)
        duplicate_hashes = [row["checksum"] for row in cursor.fetchall()]
        
        for checksum in duplicate_hashes:
            # 2. Get all files for this checksum
            files_cursor = conn.execute(
                "SELECT * FROM files WHERE checksum = ?", 
                (checksum,)
            )
            files = [_row_to_audiofile(row) for row in files_cursor.fetchall()]
            
            if len(files) > 1:
                yield DuplicateGroup(
                    group_id=checksum,
                    files=files,
                    similarity=1.0,
                    source="checksum"
                )
                
    except sqlite3.Error as e:
        logger.error(f"Database error during matching: {e}")
