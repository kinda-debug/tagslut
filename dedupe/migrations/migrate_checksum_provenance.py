"""Database migration: Checksum provenance."""

from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class ChecksumProvenanceMigration:
    """Migrate legacy rows to have explicit checksum_type."""
    
    @staticmethod
    def get_pending_migrations(db_connection) -> int:
        """Check how many rows need checksum_type."""
        try:
            cursor = db_connection.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM files WHERE checksum_type IS NULL"
            )
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to check pending migrations: {e}")
            return 0
    
    @staticmethod
    def infer_checksum_type(file_record: Dict) -> str:
        """Infer checksum_type from available data."""
        # If streaminfo_md5 exists, use that
        if file_record.get('streaminfo_md5'):
            return 'STREAMINFO'
        # If sha256 exists, use that
        elif file_record.get('sha256'):
            return 'SHA256'
        # Default to STREAMINFO if MD5 present
        elif file_record.get('md5'):
            return 'STREAMINFO'
        else:
            return 'UNKNOWN'
    
    @staticmethod
    def migrate_rows(db_connection) -> int:
        """Migrate all rows without checksum_type."""
        count = 0
        try:
            cursor = db_connection.cursor()
            
            # Get all rows without checksum_type
            cursor.execute(
                "SELECT id, streaminfo_md5, sha256, md5 FROM files WHERE checksum_type IS NULL"
            )
            rows = cursor.fetchall()
            
            for row in rows:
                file_id = row[0]
                file_record = {
                    'streaminfo_md5': row[1],
                    'sha256': row[2],
                    'md5': row[3],
                }
                checksum_type = ChecksumProvenanceMigration.infer_checksum_type(file_record)
                
                # Update row
                cursor.execute(
                    "UPDATE files SET checksum_type = ? WHERE id = ?",
                    (checksum_type, file_id)
                )
                count += 1
            
            db_connection.commit()
            logger.info(f"Migrated {count} rows")
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            db_connection.rollback()
        
        return count
