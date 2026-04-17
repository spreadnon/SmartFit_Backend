import json
from db_save_training import save_training_data_to_db, get_db_connection
import pymysql

def test_full_upgrade():
    print("Testing upgraded schema and logic...")
    user_id = 1

    
    # Data as it would look after pydantic.model_dump()
    ios_payload = {
        "external_id": "TEST-RECORD-UUID-001",
        "exercise_name": "Upgraded Squat",
        "sets": 3,
        "reps": "12",
        "weight": 0,
        "exercise_sets": [
            {"weight": 60.0, "reps": 12, "is_completed": True},
            {"weight": 65.0, "reps": 10, "is_completed": True}
        ],
        "focus_area": "Legs",
        "duration": 300
    }

    
    # 1. Test Insert
    print("--- Testing Insert ---")
    save_training_data_to_db(user_id, ios_payload)
    
    # 2. Verify Data
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM training WHERE external_id = 'TEST-RECORD-UUID-001'")
            row = cursor.fetchone()
            
            assert row is not None
            assert row["exercise_name"] == "Upgraded Squat"
            assert float(row["weight"]) == 60.0
            assert row["focus_area"] == "Legs"
            assert row["duration"] == 300
            print("✅ Insert and Data Integrity Verified")
        conn.close() # Close first verification connection

        # 3. Test Update (Same ID)
        print("--- Testing Update ---")
        ios_payload["sets"] = 4
        ios_payload["exercise_name"] = "Upgraded Squat V2"
        save_training_data_to_db(user_id, ios_payload)
        
        # Open a fresh connection for the second verification
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM training WHERE external_id = 'TEST-RECORD-UUID-001'")
            row = cursor.fetchone()
            print(f"DB Row after second update: {row}")
            assert row["sets"] == 4
            assert row["exercise_name"] == "Upgraded Squat V2"
            print("✅ UPSERT via external_id Verified")

    finally:
        if conn:
            try:
                # Use a fresh connection for cleanup just in case
                cleanup_conn = get_db_connection()
                with cleanup_conn.cursor() as cursor:
                    cursor.execute("DELETE FROM training WHERE external_id = 'TEST-RECORD-UUID-001'")
                cleanup_conn.commit()
                cleanup_conn.close()
            except:
                pass
            if not conn._closed:
                conn.close()



if __name__ == "__main__":
    test_full_upgrade()
