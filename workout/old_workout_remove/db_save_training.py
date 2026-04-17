from training_dao import get_db_connection, save_training_record, fetch_training_records_by_date


def save_training_data_to_db(user_id: int, training_data: dict):
    data = dict(training_data)
    weight = data.get("weight")
    extra_data = data.get("exercise_sets")
    if (not weight or float(weight) == 0) and isinstance(extra_data, list):
        for s in extra_data:
            s_weight = s.get("weight") if isinstance(s, dict) else getattr(s, "weight", None)
            if s_weight is not None:
                try:
                    s_weight = float(s_weight)
                except (TypeError, ValueError):
                    continue
                if s_weight > 0:
                    data["weight"] = s_weight
                    break
    return save_training_record(user_id, data)


def get_training_data_from_db(user_id: int, date_str: str):
    return fetch_training_records_by_date(user_id, date_str)



