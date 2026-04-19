import json
from db_save_training import get_training_data_from_db
from datetime import date as dt_date

def simulate_get_training_response():
    user_id = 1
    date = dt_date.today().strftime("%Y-%m-%d")
    raw_results = get_training_data_from_db(user_id, date)
    
    # Logic copied from training_log_api.py
    summary = {
        "total_volume": 0.0,
        "total_duration": 0,
        "focus_areas": set()
    }
    formatted_exercises = []
    
    for row in raw_results:
        exercise_name = row["exercise_name"]
        sets_count = row["sets"]
        weight_summary = float(row["weight"]) if row["weight"] else 0.0
        duration = row["duration"] or 0
        focus_area = row["focus_area"]
        extra_data = row["extra_data"]
        
        exercise_volume = 0.0
        max_weight = 0.0
        
        if isinstance(extra_data, list):
            for s in extra_data:
                s_weight = float(s.get("weight") or 0)
                s_reps = int(s.get("reps") or 0)
                is_comp = s.get("is_completed") 
                if is_comp is None:
                    is_comp = s.get("isCompleted", True)
                
                if is_comp:
                    exercise_volume += s_weight * s_reps
                    if s_weight > max_weight:
                        max_weight = s_weight
        else:
            exercise_volume = weight_summary * sets_count * 10
            max_weight = weight_summary
            
        summary["total_volume"] += exercise_volume
        summary["total_duration"] += duration
        if focus_area:
            summary["focus_areas"].add(focus_area)
            
        formatted_exercises.append({
            "id": row["external_id"],
            "backendId": row["id"],
            "exerciseName": exercise_name,
            "focusArea": focus_area,
            "sets": sets_count,
            "reps": row["reps"],
            "max_weight": max_weight,
            "exercise_volume": exercise_volume,
            "duration": duration,
            "exerciseSets": extra_data,
            "log_time": row["log_date"]
        })

        
    summary["focus_areas"] = list(summary["focus_areas"])
    
    response = {
        "code": 200,
        "msg": "success",
        "data": [
            {
                "date": date,
                "summary": summary,
                "exercises": formatted_exercises
            }
        ]
    }

    
    print(json.dumps(response, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    simulate_get_training_response()
