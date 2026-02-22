import sqlite3
import logging
from voice_server_api import Speaker

logger = logging.getLogger(__name__)

DB_PATH = "speakers.db"

class VoiceDataBase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS speakers (
                        id TEXT PRIMARY KEY,
                        name TEXT,
                        gender TEXT,
                        language TEXT,
                        description TEXT,
                        ref_audio_file TEXT,
                        ref_text_file TEXT,
                        ref_instruct_file TEXT
                    )
                ''')
                conn.commit()
                logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def save_speaker(self, speaker: Speaker):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO speakers 
                    (id, name, gender, language, description, ref_audio_file, ref_text_file, ref_instruct_file)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    speaker.id,
                    speaker.name,
                    speaker.gender,
                    speaker.language,
                    speaker.description,
                    speaker.ref_audio_file,
                    speaker.ref_text_file,
                    speaker.ref_instruct_file
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving speaker {speaker.name}: {e}")
            raise

    def get_speaker(self, speaker_id: str) -> Speaker | None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM speakers WHERE id = ?', (speaker_id,))
                row = cursor.fetchone()
                if row:
                    return Speaker(
                        id=row[0],
                        name=row[1],
                        gender=row[2],
                        language=row[3],
                        description=row[4],
                        ref_audio_file=row[5],
                        ref_text_file=row[6],
                        ref_instruct_file=row[7]
                    )
                return None
        except Exception as e:
            logger.error(f"Error retrieving speaker {speaker_id}: {e}")
            raise
