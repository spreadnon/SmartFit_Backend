import json
from db_save_training import save_training_data_to_db, get_training_data_from_db
from datetime import date as dt_date

def test_aggregation_logic():
    print("Testing Training Log Aggregation Logic...")
    user_id = 1
    test_date = dt_date.today().strftime("%Y-%m-%d")
    
    # 1. Prepare Test Data
    # Exercise 1: Bench Press (Chest)
    # Set 1: 100kg x 5, Set 2: 100kg x 5, Set 3: 80kg x 10
    # Volume should be: (100*5) + (100*5) + (80*10) = 500 + 500 + 800 = 1800
    ex1 = {
        "external_id": "AGG-TEST-001",
        "exercise_name": "Aggregation Bench Press",
        "sets": 3,
        "reps": "5, 5, 10",
        "weight": 100.0,
        "exercise_sets": [
            {"weight": 100.0, "reps": 5, "is_completed": True},
            {"weight": 100.0, "reps": 5, "is_completed": True},
            {"weight": 80.0, "reps": 10, "is_completed": True}
        ],
        "focus_area": "Chest",
        "duration": 600
    }
    
    # Exercise 2: Squat (Legs)
    # Set 1: 120kg x 3, Set 2: 120kg x 3 (Completed), Set 3: 120kg x 3 (NOT Completed)
    # Volume should be: (120*3) + (120*3) = 360 + 360 = 720
    ex2 = {
        "external_id": "AGG-TEST-002",
        "exercise_name": "Aggregation Squat",
        "sets": 3,
        "reps": "3, 3, 3",
        "weight": 120.0,
        "exercise_sets": [
            {"weight": 120.0, "reps": 3, "is_completed": True},
            {"weight": 120.0, "reps": 3, "is_completed": True},
            {"weight": 120.0, "reps": 3, "is_completed": False}
        ],
        "focus_area": "Legs",
        "duration": 900
    }
    
    save_training_data_to_db(user_id, ex1)
    save_training_data_to_db(user_id, ex2)
    
    # 2. Simulate the API's aggregation logic
    raw_results = get_training_data_from_db(user_id, test_date)
    
    summary = {"total_volume": 0.0, "total_duration": 0, "focus_areas": set()}
    test_bench = None
    test_squat = None
    
    for row in raw_results:
        if row["external_id"] not in ["AGG-TEST-001", "AGG-TEST-002"]:
            continue
            
        ex_vol = 0.0
        max_w = 0.0
        extra = row["extra_data"]
        
        for s in extra:
            w = float(s.get("weight", 0))
            r = int(s.get("reps", 0))
            if s.get("is_completed", True):
                ex_vol += w * r
                if w > max_w: max_w = w
        
        summary["total_volume"] += ex_vol
        summary["total_duration"] += (row["duration"] or 0)
        summary["focus_areas"].add(row["focus_area"])
        
        if row["external_id"] == "AGG-TEST-001": test_bench = {"vol": ex_vol, "max": max_w}
        if row["external_id"] == "AGG-TEST-002": test_squat = {"vol": ex_vol, "max": max_w}
        
    print(f"Summary: {summary}")
    
    # Assertions
    assert test_bench["vol"] == 1800.0, f"Bench Volume Expected 1800, got {test_bench['vol']}"
    assert test_squat["vol"] == 720.0, f"Squat Volume Expected 720, got {test_squat['vol']}"
    assert summary["total_volume"] == 2520.0
    assert summary["total_duration"] == 1500
    assert "Chest" in summary["focus_areas"]
    assert "Legs" in summary["focus_areas"]
    
    print("✅ Aggregation Logic Verified Successfully!")

    # Cleanup
    from db_save_training import get_db_connection
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM training WHERE external_id IN ('AGG-TEST-001', 'AGG-TEST-002')")
        conn.commit()
        print("🧹 Cleanup complete.")
    finally:
        conn.close()

if __name__ == "__main__":
    test_aggregation_logic()
